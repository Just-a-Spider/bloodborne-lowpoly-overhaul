//! Native Rust 3D Model Diagnostic Visualizer for Bloodborne PSX Demake.
//! Features FromSoftware PBR lighting, Filmic tone mapping, and interactive egui HUD.

use std::env;
use std::path::Path;
use three_d::*;
use three_d_asset::io::load;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ShadingMode {
    Textured,
    Normals,
    Clay,
}

struct ModelStats {
    name: String,
    total_tris: usize,
    total_verts: usize,
    submesh_names: Vec<String>,
    submesh_tris: Vec<usize>,
    bbox_min: Vector3<f32>,
    bbox_max: Vector3<f32>,
}

fn analyze_cpu_model(cpu: &CpuModel, fallback_name: &str) -> ModelStats {
    let mut total_tris = 0;
    let mut total_verts = 0;
    let mut submesh_names = Vec::new();
    let mut submesh_tris = Vec::new();

    let mut bmin = vec3(1e9f32, 1e9f32, 1e9f32);
    let mut bmax = vec3(-1e9f32, -1e9f32, -1e9f32);

    for (i, p) in cpu.geometries.iter().enumerate() {
        if let CpuGeometry::Triangles(mesh) = &p.geometry {
            let verts = mesh.positions.len();
            total_verts += verts;

            let tris = match &mesh.indices {
                Indices::U32(v) => v.len() / 3,
                Indices::U16(v) => v.len() / 3,
                Indices::U8(v) => v.len() / 3,
                Indices::None => verts / 3,
            };
            total_tris += tris;

            // Bounding box
            match &mesh.positions {
                Positions::F32(v_list) => {
                    for v in v_list {
                        bmin.x = bmin.x.min(v.x);
                        bmin.y = bmin.y.min(v.y);
                        bmin.z = bmin.z.min(v.z);
                        bmax.x = bmax.x.max(v.x);
                        bmax.y = bmax.y.max(v.y);
                        bmax.z = bmax.z.max(v.z);
                    }
                }
                Positions::F64(v_list) => {
                    for v in v_list {
                        bmin.x = bmin.x.min(v.x as f32);
                        bmin.y = bmin.y.min(v.y as f32);
                        bmin.z = bmin.z.min(v.z as f32);
                        bmax.x = bmax.x.max(v.x as f32);
                        bmax.y = bmax.y.max(v.y as f32);
                        bmax.z = bmax.z.max(v.z as f32);
                    }
                }
            }

            let name = if p.name.is_empty() { format!("Submesh_{}", i) } else { p.name.clone() };
            submesh_names.push(name);
            submesh_tris.push(tris);
        }
    }

    ModelStats {
        name: fallback_name.to_string(),
        total_tris,
        total_verts,
        submesh_names,
        submesh_tris,
        bbox_min: bmin,
        bbox_max: bmax,
    }
}

fn print_hud(
    showing_demake: bool,
    shading: ShadingMode,
    demake_stats: &ModelStats,
    vanilla_stats: Option<&ModelStats>,
    visible: &[bool],
) {
    println!("\n==================================================================");
    let active_name = if showing_demake { "PSX DEMAKE" } else { "VANILLA CLEAN" };
    println!(">>> ACTIVE MODEL: [{}] <<<", active_name);

    let stats = if showing_demake {
        demake_stats
    } else {
        vanilla_stats.unwrap_or(demake_stats)
    };

    println!("Model: {}", stats.name);
    println!("Total Triangles: {} | Total Vertices: {}", stats.total_tris, stats.total_verts);

    if let Some(vanilla) = vanilla_stats {
        if showing_demake {
            let diff = stats.total_tris as f32 - vanilla.total_tris as f32;
            let pct = (diff / vanilla.total_tris.max(1) as f32) * 100.0;
            println!("Decimation Ratio vs Vanilla: {:+.1}% ({} -> {} tris)", pct, vanilla.total_tris, stats.total_tris);
        }
    }

    println!("Shading Mode: {:?}", shading);
    println!("Submeshes ({} total):", stats.submesh_names.len());
    for (i, name) in stats.submesh_names.iter().enumerate() {
        let vis_str = if visible.get(i).copied().unwrap_or(true) { "[X]" } else { "[ ]" };
        let is_cloth = name.to_lowercase().contains("cloth");
        let tag = if is_cloth { " [CLOTH PRESERVED]" } else { "" };
        println!("  {} [{}] {} ({} tris){}", vis_str, i + 1, name, stats.submesh_tris.get(i).unwrap_or(&0), tag);
    }
    println!("------------------------------------------------------------------");
    println!("Controls:");
    println!("  [Spacebar]  : Toggle between PSX Demake & Vanilla Clean");
    println!("  [F]         : Cycle Shading Mode (Textured -> Normals -> Clay)");
    println!("  [1..9]      : Toggle Submesh Visibility 1..9");
    println!("  [A]         : Show All Submeshes");
    println!("  [R]         : Reset Camera Framing");
    println!("  [H]         : Toggle On-Screen HUD Overlay");
    println!("  [Esc]       : Quit");
    println!("==================================================================\n");
}

fn main() -> anyhow::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: bb-viewer <primary_demake.glb> [--vanilla <vanilla.glb>]");
        std::process::exit(1);
    }

    let primary_path = &args[1];
    let mut vanilla_path: Option<&str> = None;

    let mut i = 2;
    while i < args.len() {
        if args[i] == "--vanilla" && i + 1 < args.len() {
            vanilla_path = Some(&args[i + 1]);
            i += 2;
        } else {
            i += 1;
        }
    }

    println!("Initializing 3D Desktop Window (1280x720 windowed)...");
    let window = Window::new(WindowSettings {
        title: format!("Bloodborne PSX Diagnostic Viewer — {}", Path::new(primary_path).file_name().and_then(|s| s.to_str()).unwrap_or("Model")),
        min_size: (800, 600),
        max_size: Some((1280, 720)),
        ..Default::default()
    })?;

    let context = window.gl();
    let mut gui = GUI::new(&context);

    // 1. Load Primary (Demake) Model
    println!("Loading primary model: {}", primary_path);
    let mut loaded_demake = load(&[primary_path])?;
    let cpu_demake: CpuModel = loaded_demake.deserialize(primary_path)?;
    let demake_stats = analyze_cpu_model(&cpu_demake, primary_path);

    let demake_pbr = Model::<PhysicalMaterial>::new(&context, &cpu_demake)?;
    let demake_normals = Model::<NormalMaterial>::new(&context, &cpu_demake)?;
    let demake_clay = Model::<ColorMaterial>::new(&context, &cpu_demake)?;

    // 2. Load Vanilla Model (if provided)
    let (vanilla_pbr, vanilla_normals, vanilla_clay, vanilla_stats) = if let Some(v_path) = vanilla_path {
        println!("Loading vanilla reference model: {}", v_path);
        let mut loaded_vanilla = load(&[v_path])?;
        let cpu_vanilla: CpuModel = loaded_vanilla.deserialize(v_path)?;
        let v_stats = analyze_cpu_model(&cpu_vanilla, v_path);

        let pbr = Model::<PhysicalMaterial>::new(&context, &cpu_vanilla)?;
        let norm = Model::<NormalMaterial>::new(&context, &cpu_vanilla)?;
        let clay = Model::<ColorMaterial>::new(&context, &cpu_vanilla)?;
        (Some(pbr), Some(norm), Some(clay), Some(v_stats))
    } else {
        (None, None, None, None)
    };

    // Calculate Framing Center and Distance
    let center = (demake_stats.bbox_min + demake_stats.bbox_max) * 0.5;
    let size = (demake_stats.bbox_max - demake_stats.bbox_min).magnitude();
    let initial_cam_pos = center + vec3(0.0, size * 0.15, size * 1.6);

    let mut camera = Camera::new_perspective(
        window.viewport(),
        initial_cam_pos,
        center,
        vec3(0.0, 1.0, 0.0),
        degrees(45.0),
        0.05,
        150.0,
    );
    // Bloodborne ACES Filmic Tone Mapping
    camera.tone_mapping = ToneMapping::Filmic;

    let mut control = OrbitControl::new(camera.target(), 0.1, 150.0);

    // FromSoftware Gothic Studio Lighting Pipeline
    // 1. Cold Gothic Shadow Ambient
    let ambient = AmbientLight::new(&context, 0.45, Srgba::new(45, 52, 68, 255));
    // 2. Hunter's Dream Lunar Keylight (pale cool blue-white)
    let dir1 = DirectionalLight::new(&context, 2.8, Srgba::new(230, 240, 255, 255), vec3(3.5, 6.0, 4.5));
    // 3. Tombstone Candlelight Bounce (warm lantern amber)
    let dir2 = DirectionalLight::new(&context, 1.2, Srgba::new(245, 190, 130, 255), vec3(-4.0, 1.2, -2.5));
    // 4. Gothic Silhouette Rim Light (cold rim)
    let dir3 = DirectionalLight::new(&context, 1.9, Srgba::new(165, 185, 225, 255), vec3(0.0, 4.5, -5.5));

    // State
    let mut showing_demake = true;
    let mut shading = ShadingMode::Textured;
    let mut show_hud = true;
    let mut submesh_visibility = vec![true; demake_stats.submesh_names.len().max(20)];

    print_hud(showing_demake, shading, &demake_stats, vanilla_stats.as_ref(), &submesh_visibility);

    // Main 60 FPS Render Loop
    window.render_loop(move |mut frame_input| {
        camera.set_viewport(frame_input.viewport);

        // GUI Update
        if show_hud {
            let stats_name = if showing_demake { "PSX DEMAKE" } else { "VANILLA CLEAN" };
            let total_tris = if showing_demake { demake_stats.total_tris } else { vanilla_stats.as_ref().map(|s| s.total_tris).unwrap_or(demake_stats.total_tris) };
            let total_verts = if showing_demake { demake_stats.total_verts } else { vanilla_stats.as_ref().map(|s| s.total_verts).unwrap_or(demake_stats.total_verts) };
            let names = if showing_demake { &demake_stats.submesh_names } else { &vanilla_stats.as_ref().unwrap_or(&demake_stats).submesh_names };
            let tris_list = if showing_demake { &demake_stats.submesh_tris } else { &vanilla_stats.as_ref().unwrap_or(&demake_stats).submesh_tris };

            gui.update(
                &mut frame_input.events,
                frame_input.accumulated_time,
                frame_input.viewport,
                frame_input.device_pixel_ratio,
                |ui| {
                    use three_d::egui;
                    egui::Window::new("Bloodborne Model Diagnostic HUD")
                        .default_open(true)
                        .resizable(true)
                        .show(ui.ctx(), |ui| {
                            ui.horizontal(|ui| {
                                ui.label("Model State:");
                                if showing_demake {
                                    ui.colored_label(egui::Color32::from_rgb(80, 220, 200), format!("[{}]", stats_name));
                                } else {
                                    ui.colored_label(egui::Color32::from_rgb(235, 195, 75), format!("[{}]", stats_name));
                                }
                            });

                            ui.label(format!("Geometry: {} tris | {} verts", total_tris, total_verts));

                            if let Some(v_stats) = vanilla_stats.as_ref() {
                                if showing_demake {
                                    let diff = total_tris as f32 - v_stats.total_tris as f32;
                                    let pct = (diff / v_stats.total_tris.max(1) as f32) * 100.0;
                                    ui.colored_label(egui::Color32::from_rgb(120, 220, 100), format!("Decimation: {:+.1}% ({} -> {})", pct, v_stats.total_tris, total_tris));
                                }
                            }

                            ui.label(format!("Shading Mode: {:?}", shading));
                            ui.separator();

                            ui.collapsing("Quick Actions Legend", |ui| {
                                ui.label("[Spacebar] : Toggle Demake / Vanilla");
                                ui.label("[F]        : Cycle Shading (Textured -> Normals -> Clay)");
                                ui.label("[1..9]     : Toggle Submesh 1..9");
                                ui.label("[A]        : Show All Submeshes");
                                ui.label("[R]        : Reset Camera Framing");
                                ui.label("[H]        : Toggle This HUD Window");
                                ui.label("[Esc]      : Quit Visualizer");
                            });

                            ui.separator();

                            ui.collapsing("Submesh Isolation Checklist", |ui| {
                                for (idx, name) in names.iter().enumerate() {
                                    if let Some(v) = submesh_visibility.get_mut(idx) {
                                        let is_cloth = name.to_lowercase().contains("cloth");
                                        let cloth_badge = if is_cloth { " [CLOTH]" } else { "" };
                                        let sub_tris = tris_list.get(idx).copied().unwrap_or(0);
                                        let label = format!("[{}] {} ({} tris){}", idx + 1, name, sub_tris, cloth_badge);
                                        if is_cloth {
                                            ui.colored_label(egui::Color32::from_rgb(100, 200, 255), "Preserved Physics Layer");
                                        }
                                        ui.checkbox(v, label);
                                    }
                                }
                            });
                        });
                },
            );
        }

        control.handle_events(&mut camera, &mut frame_input.events);

        let mut needs_hud_update = false;

        for event in frame_input.events.iter() {
            match event {
                Event::KeyPress { kind, .. } => match kind {
                    Key::Space => {
                        if vanilla_stats.is_some() {
                            showing_demake = !showing_demake;
                            needs_hud_update = true;
                        }
                    }
                    Key::F => {
                        shading = match shading {
                            ShadingMode::Textured => ShadingMode::Normals,
                            ShadingMode::Normals => ShadingMode::Clay,
                            ShadingMode::Clay => ShadingMode::Textured,
                        };
                        needs_hud_update = true;
                    }
                    Key::H => {
                        show_hud = !show_hud;
                    }
                    Key::R => {
                        camera = Camera::new_perspective(
                            frame_input.viewport,
                            initial_cam_pos,
                            center,
                            vec3(0.0, 1.0, 0.0),
                            degrees(45.0),
                            0.05,
                            150.0,
                        );
                        camera.tone_mapping = ToneMapping::Filmic;
                        control = OrbitControl::new(camera.target(), 0.1, 150.0);
                    }
                    Key::A => {
                        for v in submesh_visibility.iter_mut() {
                            *v = true;
                        }
                        needs_hud_update = true;
                    }
                    Key::Num1 => { submesh_visibility[0] = !submesh_visibility[0]; needs_hud_update = true; }
                    Key::Num2 => { submesh_visibility[1] = !submesh_visibility[1]; needs_hud_update = true; }
                    Key::Num3 => { submesh_visibility[2] = !submesh_visibility[2]; needs_hud_update = true; }
                    Key::Num4 => { submesh_visibility[3] = !submesh_visibility[3]; needs_hud_update = true; }
                    Key::Num5 => { submesh_visibility[4] = !submesh_visibility[4]; needs_hud_update = true; }
                    Key::Num6 => { submesh_visibility[5] = !submesh_visibility[5]; needs_hud_update = true; }
                    Key::Num7 => { submesh_visibility[6] = !submesh_visibility[6]; needs_hud_update = true; }
                    Key::Num8 => { submesh_visibility[7] = !submesh_visibility[7]; needs_hud_update = true; }
                    Key::Num9 => { submesh_visibility[8] = !submesh_visibility[8]; needs_hud_update = true; }
                    Key::Num0 => { submesh_visibility[9] = !submesh_visibility[9]; needs_hud_update = true; }
                    _ => {}
                },
                _ => {}
            }
        }

        if needs_hud_update {
            print_hud(showing_demake, shading, &demake_stats, vanilla_stats.as_ref(), &submesh_visibility);
        }

        // Select active model parts
        let objects: Vec<&dyn Object> = if showing_demake {
            match shading {
                ShadingMode::Textured => demake_pbr.iter()
                    .enumerate()
                    .filter(|(i, _)| *submesh_visibility.get(*i).unwrap_or(&true))
                    .map(|(_, p)| p as &dyn Object)
                    .collect(),
                ShadingMode::Normals => demake_normals.iter()
                    .enumerate()
                    .filter(|(i, _)| *submesh_visibility.get(*i).unwrap_or(&true))
                    .map(|(_, p)| p as &dyn Object)
                    .collect(),
                ShadingMode::Clay => demake_clay.iter()
                    .enumerate()
                    .filter(|(i, _)| *submesh_visibility.get(*i).unwrap_or(&true))
                    .map(|(_, p)| p as &dyn Object)
                    .collect(),
            }
        } else if let (Some(v_pbr), Some(v_norm), Some(v_clay)) = (&vanilla_pbr, &vanilla_normals, &vanilla_clay) {
            match shading {
                ShadingMode::Textured => v_pbr.iter()
                    .enumerate()
                    .filter(|(i, _)| *submesh_visibility.get(*i).unwrap_or(&true))
                    .map(|(_, p)| p as &dyn Object)
                    .collect(),
                ShadingMode::Normals => v_norm.iter()
                    .enumerate()
                    .filter(|(i, _)| *submesh_visibility.get(*i).unwrap_or(&true))
                    .map(|(_, p)| p as &dyn Object)
                    .collect(),
                ShadingMode::Clay => v_clay.iter()
                    .enumerate()
                    .filter(|(i, _)| *submesh_visibility.get(*i).unwrap_or(&true))
                    .map(|(_, p)| p as &dyn Object)
                    .collect(),
            }
        } else {
            Vec::new()
        };

        // Render Frame with Dark Retro Gothic Slate Background (0x0b0d13) and write GUI
        frame_input.screen()
            .clear(ClearState::color_and_depth(0.043, 0.051, 0.075, 1.0, 1.0))
            .render(&camera, &objects, &[&ambient, &dir1, &dir2, &dir3])
            .write(|| {
                if show_hud {
                    gui.render()?;
                }
                Ok::<(), three_d::CoreError>(())
            })
            .unwrap();

        FrameOutput::default()
    });

    Ok(())
}
