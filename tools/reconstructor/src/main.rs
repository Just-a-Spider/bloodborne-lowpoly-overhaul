//! apply_patch - High-performance standalone reconstructor for Bloodborne: Low-Poly Overhaul.
//! Reconstructs modular mod pillars from legal retail Bloodborne (CUSA03173) and .patch containers.

use clap::Parser;
use memmap2::Mmap;
use rayon::prelude::*;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};
use std::process::exit;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::Instant;

const MAGIC: &[u8; 8] = b"BBLPO01\0";

#[derive(Debug, Deserialize, Clone)]
pub struct PatchFileEntry {
    pub path: String,
    #[serde(rename = "type")]
    pub entry_type: String,
    pub offset: u64,
    pub length: u64,
    pub vanilla_size: Option<u64>,
    pub vanilla_sha256: Option<String>,
    pub target_size: Option<u64>,
    pub target_sha256: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
pub struct PatchManifest {
    pub format: Option<String>,
    pub version: Option<String>,
    pub created_at: Option<String>,
    pub game_version: Option<String>,
    pub vanilla_title: Option<String>,
    pub mod_name: Option<String>,
    pub total_files: Option<usize>,
    pub files: Vec<PatchFileEntry>,
}

#[derive(Parser, Debug)]
#[command(
    name = "apply_patch",
    about = "Standalone high-performance reconstructor for Bloodborne: Low-Poly Overhaul",
    version = "1.2.0"
)]
pub struct Args {
    /// Path to retail Bloodborne directory (e.g. /path/to/CUSA03173)
    #[arg(short = 'g', long = "game")]
    pub game: Option<PathBuf>,

    /// Path to .patch container file
    #[arg(short = 'p', long = "patch")]
    pub patch: Option<PathBuf>,

    /// Destination directory for reconstructed mod (or base directory for --all-patches)
    #[arg(short = 'o', long = "out")]
    pub out: Option<PathBuf>,

    /// Alias for --out (base directory for mod reconstruction)
    #[arg(short = 'm', long = "mods-dir")]
    pub mods_dir: Option<PathBuf>,

    /// Batch reconstruct all .patch files found in patch directory into dedicated subfolders
    #[arg(short = 'a', long = "all-patches")]
    pub all_patches: bool,

    /// Directory to search for patch files (default: dist/ or current directory)
    #[arg(long = "patch-dir")]
    pub patch_dir: Option<PathBuf>,

    /// Parallel worker threads (default: CPU core count)
    #[arg(short = 'w', long = "workers")]
    pub workers: Option<usize>,

    /// Skip SHA256 integrity verification
    #[arg(long = "no-verify")]
    pub no_verify: bool,
}

pub fn infer_mod_dir_name(patch_file: &Path, meta: Option<&PatchManifest>) -> String {
    if let Some(m) = meta {
        if let Some(ref name) = m.mod_name {
            if !name.trim().is_empty() {
                return name.clone();
            }
        }
    }

    let file_name = patch_file
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();

    match file_name.as_str() {
        "bloodborne_retro_hud.patch" => "Bloodborne Retro HUD and UI".to_string(),
        "bloodborne_retro_maps.patch" => "Bloodborne Retro Maps".to_string(),
        "bloodborne_retro_props.patch" => "Bloodborne Retro Props and Objects".to_string(),
        "bloodborne_retro_armors_cloth.patch" => {
            "Bloodborne Retro Armors and Weapons - Cloth Physics".to_string()
        }
        "bloodborne_retro_armors_stiff.patch" => {
            "Bloodborne Retro Armors and Weapons - Flat Stiff".to_string()
        }
        "bloodborne_retro_characters.patch" => "Bloodborne Retro Characters".to_string(),
        "bloodborne_lowpoly_overhaul_cloth.patch" => {
            "Bloodborne Low-Poly Overhaul (Cloth Physics)".to_string()
        }
        "bloodborne_lowpoly_overhaul_stiff.patch" => {
            "Bloodborne Low-Poly Overhaul (Flat Stiff)".to_string()
        }
        "bloodborne_lowpoly_overhaul.patch" => "Bloodborne Low-Poly Overhaul".to_string(),
        _ => {
            if file_name.contains("hud") {
                "Bloodborne Retro HUD and UI".to_string()
            } else if file_name.contains("props") || file_name.contains("obj") {
                "Bloodborne Retro Props and Objects".to_string()
            } else if file_name.contains("maps") || file_name.contains("map") {
                "Bloodborne Retro Maps".to_string()
            } else if file_name.contains("armors_cloth") {
                "Bloodborne Retro Armors and Weapons - Cloth Physics".to_string()
            } else if file_name.contains("armors_stiff") {
                "Bloodborne Retro Armors and Weapons - Flat Stiff".to_string()
            } else if file_name.contains("characters") || file_name.contains("chr") {
                "Bloodborne Retro Characters".to_string()
            } else if file_name.contains("overhaul_cloth") {
                "Bloodborne Low-Poly Overhaul (Cloth Physics)".to_string()
            } else if file_name.contains("overhaul_stiff") {
                "Bloodborne Low-Poly Overhaul (Flat Stiff)".to_string()
            } else {
                "Bloodborne Low-Poly Overhaul".to_string()
            }
        }
    }
}

#[inline]
pub fn xor_bytes(delta: &[u8], base: &[u8]) -> Vec<u8> {
    let min_len = delta.len().min(base.len());
    let mut out = vec![0u8; delta.len()];

    let mut i = 0;
    while i + 8 <= min_len {
        let d = u64::from_le_bytes(delta[i..i + 8].try_into().unwrap());
        let b = u64::from_le_bytes(base[i..i + 8].try_into().unwrap());
        out[i..i + 8].copy_from_slice(&(d ^ b).to_le_bytes());
        i += 8;
    }
    while i < min_len {
        out[i] = delta[i] ^ base[i];
        i += 1;
    }
    if delta.len() > min_len {
        out[min_len..].copy_from_slice(&delta[min_len..]);
    }
    out
}

pub fn sha256_hex(data: &[u8]) -> String {
    let hash = Sha256::digest(data);
    let mut hex_str = String::with_capacity(64);
    for byte in hash {
        use std::fmt::Write;
        let _ = write!(&mut hex_str, "{:02x}", byte);
    }
    hex_str
}

pub fn read_patch_metadata(mmap: &Mmap) -> Result<(PatchManifest, usize), String> {
    if mmap.len() < 12 {
        return Err("File is too small to be a valid .patch container".to_string());
    }
    if &mmap[0..8] != MAGIC {
        return Err(format!(
            "Invalid patch magic bytes: expected {:?}, got {:?}",
            MAGIC,
            &mmap[0..8]
        ));
    }
    let meta_len = u32::from_le_bytes(mmap[8..12].try_into().unwrap()) as usize;
    if mmap.len() < 12 + meta_len {
        return Err(format!(
            "Corrupt patch file: header specifies {} metadata bytes, but file only has {}",
            meta_len,
            mmap.len() - 12
        ));
    }
    let meta_json_slice = &mmap[12..12 + meta_len];
    let meta: PatchManifest = serde_json::from_slice(meta_json_slice)
        .map_err(|e| format!("Failed to parse patch metadata JSON: {}", e))?;
    let payload_start = 12 + meta_len;
    Ok((meta, payload_start))
}

pub fn check_disk_space(dest_dir: &Path, required_bytes: u64) -> Result<(), String> {
    let check_dir = if dest_dir.exists() {
        dest_dir.to_path_buf()
    } else {
        dest_dir
            .parent()
            .map(|p| p.to_path_buf())
            .unwrap_or_else(|| PathBuf::from("."))
    };

    if let Ok(free_bytes) = fs2::available_space(&check_dir) {
        let buffer_bytes = 50 * 1024 * 1024; // 50 MB safety margin
        if free_bytes < (required_bytes + buffer_bytes) {
            let req_mb = required_bytes as f64 / (1024.0 * 1024.0);
            let free_mb = free_bytes as f64 / (1024.0 * 1024.0);
            return Err(format!(
                "Insufficient disk space on target volume ({}). Required: {:.1} MB, Available: {:.1} MB.",
                check_dir.display(),
                req_mb,
                free_mb
            ));
        }
    }
    Ok(())
}

fn patch_single_file(
    entry: &PatchFileEntry,
    mmap: &Mmap,
    payload_start: usize,
    game_dir: &Path,
    out_dir: &Path,
    verify_sha: bool,
) -> Result<(), String> {
    let rel_path = Path::new(&entry.path);
    let dest_path = out_dir.join(rel_path);

    let start_idx = payload_start + entry.offset as usize;
    let end_idx = start_idx + entry.length as usize;
    if end_idx > mmap.len() {
        return Err(format!(
            "Patch payload truncated for {}: offset {} + len {} exceeds total file size {}",
            entry.path, entry.offset, entry.length, mmap.len()
        ));
    }
    let delta_data = &mmap[start_idx..end_idx];

    let reconstructed = if entry.entry_type == "xor_delta" {
        let src_path = game_dir.join(rel_path);
        if !src_path.is_file() {
            return Err(format!("Missing base game file: {}", src_path.display()));
        }
        let v_bytes = fs::read(&src_path)
            .map_err(|e| format!("Failed to read {}: {}", src_path.display(), e))?;

        if verify_sha {
            if let Some(ref expected_v_sha) = entry.vanilla_sha256 {
                if !expected_v_sha.is_empty() {
                    let actual_v_sha = sha256_hex(&v_bytes);
                    if &actual_v_sha != expected_v_sha {
                        return Err(format!(
                            "Base game hash mismatch on {} (Expected {}, got {})",
                            entry.path, expected_v_sha, actual_v_sha
                        ));
                    }
                }
            }
        }

        xor_bytes(delta_data, &v_bytes)
    } else {
        delta_data.to_vec()
    };

    if verify_sha {
        if let Some(ref expected_t_sha) = entry.target_sha256 {
            if !expected_t_sha.is_empty() {
                let actual_t_sha = sha256_hex(&reconstructed);
                if &actual_t_sha != expected_t_sha {
                    return Err(format!(
                        "Reconstructed hash mismatch on {} (Expected {}, got {})",
                        entry.path, expected_t_sha, actual_t_sha
                    ));
                }
            }
        }
    }

    if let Some(parent) = dest_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create directory {}: {}", parent.display(), e))?;
    }

    fs::write(&dest_path, &reconstructed)
        .map_err(|e| format!("Failed to write {}: {}", dest_path.display(), e))?;

    Ok(())
}

pub fn apply_single_patch(
    patch_file: &Path,
    game_dir: &Path,
    out_dir: &Path,
    workers: usize,
    verify_sha: bool,
) -> bool {
    println!("{}", "=".repeat(65));
    println!("Bloodborne: Low-Poly Overhaul - Standalone Mod Reconstructor");
    println!("{}", "=".repeat(65));
    println!("Base Game:         {} (read-only)", game_dir.display());
    println!("Patch File:        {}", patch_file.display());
    println!("Destination:       {}", out_dir.display());
    println!("Parallel Workers:  {}", workers);
    println!("Engine:            Native Rust XOR Streaming (Memory-Mapped)");
    println!("{}", "-".repeat(65));

    let start_time = Instant::now();

    println!("Reading patch manifest...");
    let file = match File::open(patch_file) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("Error opening patch file {}: {}", patch_file.display(), e);
            return false;
        }
    };

    let mmap = match unsafe { Mmap::map(&file) } {
        Ok(m) => m,
        Err(e) => {
            eprintln!("Error memory-mapping patch file: {}", e);
            return false;
        }
    };

    let (meta, payload_start) = match read_patch_metadata(&mmap) {
        Ok(res) => res,
        Err(e) => {
            eprintln!("Error reading patch file header: {}", e);
            return false;
        }
    };

    let total_files = meta.files.len();
    let mod_name = meta
        .mod_name
        .clone()
        .unwrap_or_else(|| out_dir.file_name().unwrap().to_string_lossy().to_string());
    println!("Mod name:          {}", mod_name);
    println!(
        "Mod version:       {}",
        meta.version.as_deref().unwrap_or("1.0.0")
    );
    println!(
        "Vanilla title:     {}",
        meta.vanilla_title.as_deref().unwrap_or("Bloodborne")
    );
    println!("Total delta files: {}", total_files);

    let total_target_bytes: u64 = meta
        .files
        .iter()
        .map(|f| f.target_size.unwrap_or(f.length))
        .sum();

    if let Err(e) = check_disk_space(out_dir, total_target_bytes) {
        eprintln!("Error: {}", e);
        return false;
    }

    println!("{}", "-".repeat(65));
    println!("Reconstructing {} mod assets...", total_files);

    let pool = match rayon::ThreadPoolBuilder::new()
        .num_threads(workers)
        .build()
    {
        Ok(p) => p,
        Err(e) => {
            eprintln!("Error initializing thread pool: {}", e);
            return false;
        }
    };

    let completed = AtomicUsize::new(0);
    let errors: Mutex<Vec<(String, String)>> = Mutex::new(Vec::new());

    pool.install(|| {
        meta.files.par_iter().for_each(|entry| {
            let res = patch_single_file(
                entry,
                &mmap,
                payload_start,
                game_dir,
                out_dir,
                verify_sha,
            );

            let done = completed.fetch_add(1, Ordering::Relaxed) + 1;

            if let Err(err_msg) = res {
                let mut errs = errors.lock().unwrap();
                errs.push((entry.path.clone(), err_msg));
            }

            if done % 500 == 0 || done == total_files {
                let pct = (done as f64 * 100.0) / total_files as f64;
                println!(
                    "  Progress: {}/{} files reconstructed ({:.1}%)...",
                    done, total_files, pct
                );
            }
        });
    });

    let elapsed = start_time.elapsed().as_secs_f64();
    println!("{}", "-".repeat(65));

    let errs = errors.into_inner().unwrap();
    if !errs.is_empty() {
        eprintln!("ERROR: {} files failed reconstruction:", errs.len());
        for (path_str, err_msg) in errs.iter().take(10) {
            eprintln!("  - {}: {}", path_str, err_msg);
        }
        if errs.len() > 10 {
            eprintln!("  ... and {} more errors.", errs.len() - 10);
        }
        return false;
    }

    println!(
        "SUCCESS: 100% of {} assets successfully reconstructed in {:.2}s.",
        total_files, elapsed
    );
    println!("Reconstructed mod output: {}", out_dir.display());
    println!("{}", "=".repeat(65));
    true
}

pub fn discover_patches(search_dir: &Path) -> Vec<PathBuf> {
    if !search_dir.is_dir() {
        return Vec::new();
    }
    let mut patches = Vec::new();
    if let Ok(entries) = fs::read_dir(search_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                if let Some(ext) = path.extension() {
                    if ext == "patch" {
                        patches.push(path);
                    }
                }
            }
        }
    }
    patches.sort();
    patches
}

fn find_default_patch() -> Option<PathBuf> {
    let candidates = [
        PathBuf::from("bloodborne_lowpoly_overhaul.patch"),
        PathBuf::from("dist/bloodborne_lowpoly_overhaul.patch"),
    ];
    for c in &candidates {
        if c.is_file() {
            return Some(c.clone());
        }
    }
    None
}

fn auto_detect_game_dir() -> Option<PathBuf> {
    let candidates = [
        PathBuf::from("CUSA03173"),
        PathBuf::from("../CUSA03173"),
        PathBuf::from("../../CUSA03173"),
    ];
    for c in &candidates {
        if c.is_dir() && c.join("dvdroot_ps4").is_dir() {
            return Some(c.clone());
        }
    }
    None
}

fn prompt_input(prompt: &str) -> String {
    print!("{}", prompt);
    let _ = io::stdout().flush();
    let mut buffer = String::new();
    let stdin = io::stdin();
    let _ = stdin.lock().read_line(&mut buffer);
    buffer.trim().to_string()
}

fn pick_game_directory() -> Option<PathBuf> {
    println!("Opening folder picker: Please select your Bloodborne CUSA03173 directory...");
    rfd::FileDialog::new()
        .set_title("Select Bloodborne (CUSA03173) Game Folder")
        .pick_folder()
}

fn pick_output_directory() -> Option<PathBuf> {
    println!("Opening folder picker: Please select destination mods directory...");
    rfd::FileDialog::new()
        .set_title("Select Destination Mods Folder")
        .pick_folder()
}

fn main() {
    let mut args = Args::parse();
    let is_interactive = std::env::args().len() <= 1;

    // Interactive fallback for Regular Joe
    if args.game.is_none() {
        println!("=================================================================");
        println!("Bloodborne: Low-Poly Overhaul - Interactive Reconstructor v1.2.0");
        println!("=================================================================");

        let mut chosen_game = None;
        if let Some(detected) = auto_detect_game_dir() {
            println!("Auto-detected Bloodborne game directory: {}", detected.display());
            let ans = prompt_input("Use this directory? [Y/n / b to browse]: ");
            if ans.is_empty() || ans.eq_ignore_ascii_case("y") {
                chosen_game = Some(detected);
            } else if ans.eq_ignore_ascii_case("b") {
                chosen_game = pick_game_directory();
            }
        }

        while chosen_game.is_none() {
            println!("\nPlease select your Bloodborne CUSA03173 directory:");
            println!("  [1] Open GUI Folder Browser (Recommended)");
            println!("  [2] Enter folder path manually");
            let choice = prompt_input("Choice [1]: ");

            if choice == "2" {
                let manual = prompt_input("Enter path to CUSA03173: ");
                if !manual.is_empty() {
                    chosen_game = Some(PathBuf::from(manual));
                }
            } else {
                chosen_game = pick_game_directory();
            }

            if let Some(ref p) = chosen_game {
                if !p.join("dvdroot_ps4").is_dir() {
                    println!("\nWarning: 'dvdroot_ps4' not found inside {}.", p.display());
                    println!("Make sure you select the root CUSA03173 folder that contains dvdroot_ps4.");
                    let retry = prompt_input("Try again? [Y/n]: ");
                    if !retry.is_empty() && !retry.eq_ignore_ascii_case("y") {
                        break;
                    }
                    chosen_game = None;
                }
            }
        }

        args.game = chosen_game;
    }

    let game_path = match args.game {
        Some(ref p) => p.clone(),
        None => {
            eprintln!("Error: Bloodborne game directory (--game) is required.");
            if is_interactive {
                prompt_input("\nPress Enter to exit...");
            }
            exit(1);
        }
    };

    let game_dir = match fs::canonicalize(&game_path) {
        Ok(p) => p,
        Err(_) => game_path,
    };

    if !game_dir.is_dir() {
        eprintln!("Error: Game directory not found: {}", game_dir.display());
        if is_interactive {
            prompt_input("\nPress Enter to exit...");
        }
        exit(1);
    }

    if !game_dir.join("dvdroot_ps4").is_dir() {
        eprintln!(
            "Error: Invalid game directory. 'dvdroot_ps4' not found inside {}",
            game_dir.display()
        );
        if is_interactive {
            prompt_input("\nPress Enter to exit...");
        }
        exit(1);
    }

    let workers = args.workers.unwrap_or_else(|| {
        std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(4)
    });
    let verify_sha = !args.no_verify;

    // Check patch search dirs
    let search_dirs = if let Some(ref pd) = args.patch_dir {
        vec![pd.clone()]
    } else {
        vec![PathBuf::from("dist"), PathBuf::from(".")]
    };

    let mut patches_found = Vec::new();
    for s_dir in &search_dirs {
        for p in discover_patches(s_dir) {
            if !patches_found.contains(&p) {
                patches_found.push(p);
            }
        }
    }

    // Interactive destination folder selection
    if is_interactive && args.out.is_none() && args.mods_dir.is_none() {
        println!("\nOutput destination for reconstructed mods [default: ./mods]:");
        println!("  [1] Use default (./mods)");
        println!("  [2] Open GUI Folder Browser to select custom mods folder");
        println!("  [3] Enter custom folder path manually");
        let out_choice = prompt_input("Choice [1]: ");
        if out_choice == "2" {
            if let Some(picked) = pick_output_directory() {
                args.out = Some(picked);
            }
        } else if out_choice == "3" {
            let manual_out = prompt_input("Enter destination mods folder path: ");
            if !manual_out.is_empty() {
                args.out = Some(PathBuf::from(manual_out));
            }
        }
    }

    // Auto batch mode if no specific patch passed and multiple patches found
    if !args.all_patches && args.patch.is_none() && patches_found.len() > 1 && is_interactive {
        println!(
            "\nFound {} patch containers in {:?}.",
            patches_found.len(),
            search_dirs
        );
        let ans = prompt_input("Reconstruct all modular pillars into mods directory? [Y/n]: ");
        if ans.is_empty() || ans.eq_ignore_ascii_case("y") {
            args.all_patches = true;
        }
    }

    if args.all_patches {
        if patches_found.is_empty() {
            eprintln!("Error: No .patch files found to batch reconstruct.");
            if is_interactive {
                prompt_input("\nPress Enter to exit...");
            }
            exit(1);
        }

        let base_out = args
            .out
            .or(args.mods_dir)
            .unwrap_or_else(|| PathBuf::from("mods"));
        if let Err(e) = fs::create_dir_all(&base_out) {
            eprintln!("Error creating output directory {}: {}", base_out.display(), e);
            exit(1);
        }

        println!(
            "Batch reconstructing {} patch containers into {}...",
            patches_found.len(),
            base_out.display()
        );

        let mut all_passed = true;
        for p in &patches_found {
            let meta_opt = File::open(p)
                .ok()
                .and_then(|f| unsafe { Mmap::map(&f) }.ok())
                .and_then(|m| read_patch_metadata(&m).ok())
                .map(|(m, _)| m);

            let subfolder = infer_mod_dir_name(p, meta_opt.as_ref());
            let target_out = base_out.join(subfolder);

            let ok = apply_single_patch(p, &game_dir, &target_out, workers, verify_sha);
            if !ok {
                all_passed = false;
            }
        }

        if !all_passed {
            eprintln!("Batch reconstruction encountered errors.");
            if is_interactive {
                prompt_input("\nPress Enter to exit...");
            }
            exit(1);
        }

        println!("\nAll batch patches successfully reconstructed!");
        if is_interactive {
            prompt_input("\nPress Enter to exit...");
        }
        exit(0);
    }

    // Single patch mode
    let patch_path = match args.patch.or_else(find_default_patch) {
        Some(p) => p,
        None => {
            if let Some(first_p) = patches_found.first() {
                first_p.clone()
            } else {
                eprintln!("Error: No .patch file specified and no default patch found.");
                if is_interactive {
                    prompt_input("\nPress Enter to exit...");
                }
                exit(1);
            }
        }
    };

    if !patch_path.is_file() {
        eprintln!("Error: Patch file not found: {}", patch_path.display());
        if is_interactive {
            prompt_input("\nPress Enter to exit...");
        }
        exit(1);
    }

    let meta_opt = File::open(&patch_path)
        .ok()
        .and_then(|f| unsafe { Mmap::map(&f) }.ok())
        .and_then(|m| read_patch_metadata(&m).ok())
        .map(|(m, _)| m);

    let out_dir = args
        .out
        .or(args.mods_dir)
        .unwrap_or_else(|| PathBuf::from(infer_mod_dir_name(&patch_path, meta_opt.as_ref())));

    let ok = apply_single_patch(&patch_path, &game_dir, &out_dir, workers, verify_sha);
    if is_interactive {
        prompt_input("\nPress Enter to exit...");
    }
    exit(if ok { 0 } else { 1 });
}
