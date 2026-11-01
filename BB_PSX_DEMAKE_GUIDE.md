# Bloodborne PSX Demake & Performance Mod: Research & Implementation Guide

> [!NOTE]
> **Mathematical Foundations & Engineering Findings**: For the complete mathematical proofs (Garland-Heckbert QEM, Skeleton-Driven Semantic Partitioning, Per-Corner Barycentric UV/LBS Transfer, Thurmer-Wüthrich Angle-Weighted Normals, Handedness-Aware Tangents, Rigid `normal_w` Hinge Binding, GCN Morton Swizzling, RGB555 Color Quantization, BC1 De-Crochet Proof, Havok Cloth Constraints, and DOL Lightmaps) and detailed breakdown of Tests 1–42, see [BB_PSX_DEMAKE_MATH_AND_FINDINGS.md](BB_PSX_DEMAKE_MATH_AND_FINDINGS.md).

## 1. Project Goal & Vision
Create an authentic **authentic 32-bit retro style** demake mod for *Bloodborne* running on **shadPS4** and native Linux **bbhost**, designed specifically to **maximize performance and eliminate VRAM bottlenecks** on entry-level hardware (e.g. GTX 1650 Max-Q 4GB VRAM).

### Core Aesthetic Pillars
1. **Rustic, Chunky Textures**: Low-resolution diffuse textures (32x32 to 256x256 equivalent) with 15-bit RGB555 palette stepping.
2. **Retro Shading with PBR Safety**: Removal of high-frequency skin/cloth gloss while preserving essential metallic specular reflectance (`_r`), anisotropic hair highlights, and directional offline lightmap (DOL) normal vectors (`_n`) so surfaces never collapse into pitch-black silhouettes.
3. **Low-Polygon Silhouette**: Simplified angular geometry and collapsed edge loops with shared welded manifold vertices (`num_verts < num_tris`), preserved mechanical/weapon creases, and intact facial likeness (600–800 tris).
4. **Zero Impact on Base Game**: Maintain an isolated Btrfs copy-on-write sandbox (`CUSA03173-PSX`) where experiments never touch or degrade the pristine game setup (`CUSA03173`).

---

## 2. Architecture & Sandbox Setup

### Filesystem & Command Configuration
- **Filesystem**: Btrfs on Linux (`/home`).
- **Main Clean Game**: `CUSA03173/` (1.09 GotY / The Old Hunters Complete Edition)
  - Launched via: `bb` (shadPS4) / `bbhost` (native Linux Vulkan port)
- **Isolated PSX Sandbox**: `CUSA03173-PSX/`
  - Created using instant copy-on-write (`cp -a --reflink=always`), consuming **0 MB extra disk space**.
  - Launched via: `bb-psx` (shadPS4) / `bbhost-psx` (native Linux Vulkan port)
- **bbhost Configuration**:
  - Main config: `~/.config/bbhost/bbhost.toml` (`app0 = CUSA03173`, `eboot = CUSA03173/eboot.elf`).
  - PSX config: `~/.config/bbhost/bbhost-psx.toml` (`app0 = CUSA03173-PSX`, `eboot = CUSA03173-PSX/eboot.elf`).
  - Account & Saves: Shared via `~/.local/share/bbhost/data/saves` with `JustASpider` account.
  - Pipeline Cache: `~/.local/share/bbhost/data/bbhost/*.bin` (must be cleared whenever containers are repacked).
- **Custom Tooling Directory**: `tools/`
  - `tools/`: Active 15-tool core production pipeline and shared engines.
  - `tools/legacy/`: Deprecated / superseded tools (`batch_demake_objects_ultralow.py`, etc.).
  - `tools/archive/`: Historical one-offs and diagnostic test scripts.
  - `tools/viewer/`: Standalone glTF web viewer and 3D visualizers.

---

## 3. FromSoftware Asset Pipeline Reverse-Engineering

### Container Structure
Assets are stored in proprietary FromSoftware archives inside `dvdroot_ps4/`:
- **`parts/`**: Player gear, armor, weapons, facegen heads (`.partsbnd.dcx`).
- **`chr/`**: Enemies, bosses, NPCs (`.chrbnd.dcx`).
- **`obj/`**: Interactive world props, doors, levers, chests, tombstones, carriages (`.objbnd.dcx`).
- **`map/`**: World geometry (`mXX_YY_ZZ_WW/*.flver.dcx`) and split BXF environment texture archives (`mXX/*.tpfbhd`, `*.tpfbdt`).
  - `m21`: Hunter's Dream.
  - `m22`: Central Yharnam & Cathedral Ward Approaches.
  - `m29`: Modular Chalice Dungeon Labyrinths (`m29_00_00_00`, `m29_01_00_00`, etc.).
- **`menu/`**: Scaleform UI & HUD texture atlases (`common.tpf.dcx`).

### Binary Layers
```
[DCX Container] (Deflate / DFLT compression with DCS/DCP/DCA headers)
    │
    ▼ (zlib decompress)
[BND4 / BXF4 Container] (FromSoftware 64-bit Package)
    │
    ├── Entry 0: [.TPF Container] (Texture Package Format - GCN Morton Swizzled)
    │       ├── Albedo / Diffuse (_a)      [BC1 8B/block or BC7 16B/block]
    │       ├── Normal Map (_n)            [BC5 16B/block or BC6H 16B/block]
    │       ├── Reflectance / Specular (_r)[BC1 8B/block]
    │       └── Shininess / Gloss (_s)     [BC4 8B/block]
    ├── Entry 1: [.FLVER Model] (3D Geometry, VA0/VA1 Split Vertex Arrays, 206 Bone Rigs)
    ├── Entry 2: [.HKX] (Havok Cloth & Collision Physics)
    └── Entry 3: [.CLM2] (Cloth Simulation Config)
```

---

## 4. Tests Conducted & Engineering Findings (Tests 1–44)

| Test # | Experiment | Target Asset | Result | Technical Takeaway |
| :--- | :--- | :--- | :--- | :--- |
| **Test 1–3** | Armor ID & Gender Schema Audit | `bd_a_9700`, `bd_f_9300` | Confirmed FromSoft separates gear into `bd_a_` (unisex), `bd_m_` (male), `bd_f_` (female), plus `_09` 1.09 GotY overrides. | Always inspect active save slot (`userdata0000`) and process both base and `_09` / `_l` variants. |
| **Test 4–6** | PS4 GCN Morton Swizzle Engine | `tools/ps4_swizzle.py` | Raw linear block downsampling produced rainbow confetti. Closed-form 6-bit Morton Z-order interleaving (`8x8` block micro-tiles) solved tiling 100%. | PS4 textures must be deswizzled to linear row-major layout before decoding and re-swizzled before packing. |
| **Test 7–8** | Potatoborne Audit & Native `bbhost-psx` | `CUSA03173-PSX` + `bbhost` | Confirmed Potatoborne only bilinearly downsampled maps while keeping modern PBR. Fixed rogue `~/.local/bin/env` script shadowing `/usr/bin/env`. | `bbhost-psx` runs natively on Linux Vulkan with shared saves. |
| **Test 10** | FLVER Split Vertex Arrays (`VA0`/`VA1`) | `c8030.chrbnd.dcx` | Blind float snapping corrupted `VA1` bone weights, causing accordion explosion. | Bloodborne splits vertex attributes across `VA0` (pos/norm/tan) and `VA1` (weights/indices/UVs); both arrays must maintain identical vertex counts. |
| **Test 11 & 15** | Havok Cloth `SpClothVertexUpdate` Invariant | `c8030.flver` + `_c.hkx` | Decimating cloth submeshes or stripping `_c.hkx` caused `SpClothVertexUpdate` to shoot vertices to $\pm\infty$ or crash. | Keep `_c.hkx` and `_c.clm2` intact and 100% bypass QEM decimation on `_Cloth.mtd` submeshes. |
| **Test 12** | Alpha Mask Preservation (BC7 Hair & BC1 Lace) | `c8030_HR_a` (`0x66`), `c8030_BD_a` (`0x01`) | Overwriting BC7 hair with BC1 math erased hair; ignoring 1-bit alpha turned lace into black squares. | Skip BC7 (`0x66`) hair/fur cutouts and preserve 1-bit alpha (`c0 <= c1`, index `3`) on BC1 cutouts. |
| **Test 13 & 15** | Zero-Crochet Uniform BC1 Proof | `demake_color_engine.py` | Copying compressed BC1 blocks created repeating $4\times 4$ "granny square" patterns. | Decode to uncompressed RGBA in pixel space; encoding $c_0 = c_1$ with index `0` guarantees zero sub-block variance. |
| **Test 16** | CUSA03173 (1.09 GotY) Migration | `CUSA03173-PSX` | Migrated from 1.00 (`CUSA00900`) to 1.09 GotY (`CUSA03173`). | Eliminated base-engine camera frustum drops; added `_09` equipment support. |
| **Test 18 & 20** | GPU Occlusion Query (`SET_PREDICATION`) & AABBs | `c8030.chrbnd.dcx` | Desynced auxiliary FaceSets (`FS1..FS5`) or $+20\%$ padded AABBs penetrating the floor caused `SET_PREDICATION` to drop draw calls at camera angles. | Sync `FS1..FS5 = FS0.copy()`, use exact tight vertex bounds on rigid submeshes, and preserve vanilla AABBs on cloth and bones (`soulstruct_patch.py`). |
| **Test 21–25** | Map Native LODs, Blend Masks & DOL Lightmaps | `map/m21_00_00_00`, `m21_0000.tpfb*` | Flattening map normals turned workshop pillars black because `GXFlver_ColDifSpcBumpDOL.spx` computes $\text{dot}(\mathbf{N}_{\text{world}}, \mathbf{L}_{\text{DOL}})$. Quantizing `blendmsk_050_a` caused black ground stripes. | Promote native `LodLevel1`/`LodLevel2` on FaceSet 0 only (keep FS 1..N for lightmaps). Keep map normals, blend masks (`blendmsk`, `msk`, `_m`), sky domes, and foliage cards 100% vanilla. |
| **Test 26** | bbhost Vulkan Pipeline & Descriptor Cache | `~/.local/share/bbhost/data/bbhost/*.bin` | Repacked TPF/FLVER archives sampled stale cached descriptor offsets in `bbhost`, causing black surfaces or missing changes across reboots. | Always delete `~/.local/share/bbhost/data/bbhost/*.bin` after modifying containers. |
| **Test 27** | BXF4 Split Header Corruption & In-Place Patching | `m21_0000.tpfbhd` / `.tpfbdt` | Soulstruct `Binder.write()` corrupted `BHF4`/`BDF4` magic and offsets. | Bypass `Binder.write()` on map BXF archives; overwrite compressed DCX payloads in-place when `len(recomp) <= comp_sz` (or 16-byte aligned EOF append). |
| **Test 28–29** | Hybrid Map LOD & Doll Carpet Pipeline | `map/m21_00_00_00/*.flver.dcx` | Uniform `LodLevel2` culled 93% of pathway gravel and collapsed doors to 5 tris. | Use Hybrid LOD (LOD1 on landmarks `001000..001035`, LOD2 on distant cliffs) and guard submeshes from collapsing below 25% tris. |
| **Test 30–31** | PBR Metals, BC6H Face Normals & Facegen Morphs | `dvdroot_ps4/parts/*` | Zeroing `_r` turned metals/embroidery pitch black; writing 8B BC1 into 16B BC6H (`0x6A`) face normals caused black blotches; decimating `fc_`/`fg_`/`hr_` broke 1:1 Facegen morph sliders. | Never zero `_r` or flatten `_n` on equipment/weapons/faces; skip mesh decimation and texture edits on `fc_*`, `fg_*`, and `hr_*`. |
| **Test 32** | Scaleform UI Zero-Mip Memory Bounds | `menu/common.tpf.dcx` | Writing 12 mips into single-mip (`unk3 == 1`) UI slots overflowed 1.26 MB into adjacent textures. | Constrain UI mips strictly to `unk3` (`1` level) and isolate scaling to `MENU_Icon_*` atlases. |
| **Test 33–36** | Plain Doll Definitive Overhaul & BC5 16-Byte Blocks | `chr/c8030.chrbnd.dcx` | Triangle unrolling caused dynamic lighting tears; 8-byte BC1 normal blocks corrupted 16-byte BC5 `c8030_skin_n`. | Implemented shared welded vertices (`num_verts < num_tris`), 600–800 tri head likeness floor, radial bonnet clearance, distance-transform lace alpha bleed, and 16-byte BC5 blocks. |
| **Test 37–39** | Skeleton-Driven Partitioning, Ear Masking & Hand Demake | `tools/mesh_decimator.py` & `c8030` | Global QEM tilted facial symmetry; shell clearance pushed lateral ear vertices inward; hands were skipped; `normal_w` shape `(N,1)` failed broadcast from `(N,)`. | Added `flv.bones` connected-component partitioning (`HEAD_SKIN` vs `HANDS` at 0.45 ratio), lateral ear exclusion mask ($\|x\| \le 0.35 \cdot \text{span}_x$), and exact trailing shape matching. |
| **Test 40** | Hard-Surface Weapon Crease & Border Protection | `wp_a_1000` / `wp_a_1001` (Saw Cleaver) | Aggressive QEM across mechanical weapon edges created a visible seam line between the hunter's hand and saw tip. | Added weapon detection (`wp_`) in `mesh_decimator.py` forcing `preserve_border=True` and lower QEM aggressiveness (`3`) to lock hard-surface blade edges. |
| **Test 41** | Rigid Object `normal_w` Hinge Bone Preservation & Sky FLVER Isolation | `obj/o21*.objbnd.dcx` & `map/m21_00_00_00` | Zeroing `normal_w` detached workshop doors from their left/right hinge bones (sinking them into the floor), and LOD promotion decimated `009xxx` sky dome FLVERs. | Transferred `normal_w` from nearest original vertices, included `normal_w` in the $0.1\text{ mm}$ pre-weld key so door leaves never weld together, and isolated sky/cloud FLVERs (`>= 9000` / sky materials) as 100% vanilla. |
| **Test 42** | Universal Texture Batch Overwrite Prevention & Chalice Dungeon (`m29`) Multi-Block Support | `batch_demake_all_textures.py` & `map/m29_*` | Running `batch_demake_all_textures.py` loaded containers from `VANILLA_ROOT` and overwrote decimated `.flver` meshes in `SANDBOX_ROOT` back to vanilla. | Updated texture batcher to read existing containers from `SANDBOX_ROOT` (preserving decimated FLVERs) while pulling source `.tpf` data from `VANILLA_ROOT`. Added multi-block wildcard (`m29_*`) support for Chalice Dungeons. |
| **Test 43** | Ultra-Low-Poly Aggressive Decimation — v1 Failure Analysis | `tools/demake_c8030_ultralow.py` v1 | Targets `{3:50, 4:200, 5:220, 6:24, 8:50, 9:200, 12:30}` + `head=300` produced: (a) `shared=False` unrolling on Meshes 3, 5, 8 — UV seam verts exceeded tri count at extreme reduction; (b) Bonnet AABB collapsed to ~190 tris, triggering `SET_PREDICATION` draw-call drops on arms, chest, and legs in-game; (c) texture pipeline not invoked (script loads from VANILLA, bypasses `build_c8030_container` texture pass). Total: `63,494 → 16,152 tris` but visually broken — arms/dress/face disappeared in-game. | Three hard floors discovered: (1) **`shared=True` invariant floor**: every mesh that is `shared=True` in vanilla must remain `shared=True` after decimation — enforce via pre/post baseline comparison gate; (2) **Bonnet AABB minimum**: Bonnet (Mesh 4) must stay ≥ 400 tris to avoid `SET_PREDICATION` culling the character's rigid submeshes at camera angles; (3) **Collar lace topology**: Mesh 3 (`Material #3`, lace collar) has 27 post-QEM slivers from its UV chart density that invert the `shared` invariant regardless of target — preserve at vanilla count. |
| **Test 44** | Ultra-Low-Poly Aggressive Decimation — v2 Stable Deploy | `tools/demake_c8030_ultralow.py` v2 | Revised targets `{3:921(vanilla), 4:500, 5:800, 6:80, 8:120, 9:500, 12:80}` + `head=400`. Added dual safety gate: abort if any vanilla-`shared=True` mesh becomes `shared=False`, abort if any rigid mesh reaches 0 tris. Result: `63,494 → 17,737 tris (27.9%)` — all rigid meshes `shared=True`, zero bad weights, zero slivers on body/face. Deployed stable to `CUSA03173-PSX`. Snapshot fallback at `.snap_pre_ultralow`. **Open problem**: at 400-tri head budget, QEM global minimization collapses mouth cavity, nostril geometry, and eyelid crease — facial identity of the Doll is lost. Character likeness requires landmark-aware decimation that explicitly protects semantic face regions. |
| **Test 45** | Foliage/Flower LOD Promotion & Moon Object Protection | `tools/batch_demake_environment.py` & `map/m21_00_00_00` | (a) In Hunter's Dream, FromSoft authored grass/flower cards with LOD2 at ~19.9% tris. The 25% floor guard rejected LOD2 and had no LOD1 fallback, keeping foliage at 100% tris. (b) Foliage diffuse textures were unconditionally blocked in `PROTECTED_ENV_KEYWORDS` and BC1 cutout skip. (c) `o210020.objbnd.dcx` (Moon) has 1 bone, so `safe` mesh mode decimated it into an octagonal polygon clump. | (a) Lowered foliage geometry floor to 15% and added LOD2->LOD1 fallback before LOD0 fallback (foliage now drops ~80% tris, 25k -> 5k). (b) Added `--demake-foliage` with 1-bit alpha thresholding and 1.35x brightness boost. (c) Protected `o210020`/`o210021` and celestial objects from QEM decimation in all modes. |
| **Test 46** | Native bbport PSX Demake Engine Integration | `bbport-src` | vkBasalt failed (not in Arch official repos, unable to intercept vertex coords or affine UVs). Need native PSX rendering engine in bbport accessible via GTK4 desktop launcher, in-game ImGui overlay, and `bbport.ini`. | (a) Settings & GUI: Added `psx_mode`, `psx_dither`, `psx_point_filter`, `psx_vertex_snap`, `psx_affine`, `psx_snap_res` to `bbport_settings.h/.cpp`, `bbport.ini`, `bbport_launcher.py` (Adw preferences group) and `bbport_overlay.cpp` (ImGui). (b) 15-bit color + 4x4 Bayer dither: Implemented in `present_encode.frag` and passed via `present_passes.h`/`presenter.cpp`. (c) Point filtering: Forced `vk::Filter::eNearest` & nearest mipmap filtering in `sampler.cpp`. (d) Screen-space vertex wobble: Fixed-point NDC grid snapping in `emit_spirv_special.cpp` excluding UI (`motion_param != 0`). (e) Affine UVs: Forced `spv::Decoration::NoPerspective` in `spirv_emit_context.cpp`. (f) Cache: Bumped `ShaderBinaryVersion = 21u` in `pipeline_store.h`. |
| **Test 47** | Ultra-Low-Poly World Decimation & Master Engine Cascade | `tools/batch_demake_world_ultralow.py` & `bbport-src` | (a) World meshes require balanced decimation without collapsing structural step risers and floor planes. (b) Native `bbport` PSX demake engine needed English translations and a master switch cascade enabling all sub-options simultaneously. | (a) `batch_demake_world_ultralow.py` aggressive preset deployed stable to `m21` (7,769,107 -> 2,781,132 tris, 35.8% budget, 449 QEM passes, 81 gated fallbacks). (b) Added full English localization to `launcher/bbport_i18n.py`. (c) Updated master toggle in `bbport_launcher.py` and `bbport_overlay.cpp` to automatically cascade-enable all sub-features (dither, point filter, vertex snap, affine UVs) on activation. |
| **Test 48** | True VRAM Reduction via Top-Mip Bitstream Slicing | `tools/batch_shrink_world_textures.py` & `tools/shrink_chr_textures.py` | Discovered previous color demake scripts downsampled then upscaled back to canvas dimensions ($2048 \times 2048$), saving 0 bytes of GPU VRAM. Need true hardware VRAM reduction without re-encoding artifacts. | (a) Built `batch_shrink_world_textures.py` for BXF map archives: slices top $N$ mips from raw bitstream, repacks `tpfbdt`/`tpfbhd` with updated entry dimensions ($nw \| nh \ll 16$) and mip counts ($k - drop$). `m21` shrank 297 MB -> 77.7 MB (-74% disk, ~85-90% active VRAM reduction). (b) Expanded `shrink_chr_textures.py` across `chr/` (96 files, 301.8 MiB saved), `parts/` (802 files, 1076.9 MiB saved), and `obj/` (227 files, 309.4 MiB saved). Slicing drops `VkImage` extents in Vulkan hardware from 5.3 MB down to 85 KB per 2K texture (98.4% reduction). |
| **Test 49** | Dual-Path Asset Configuration & Live In-Game Demake Toggle | `bbport-src` | User needed frictionless switching between pristine vanilla (`CUSA03173`) and retro demake (`CUSA03173-PSX`), both at launcher boot and during live gameplay. | (a) Launcher GUI: Added separate `psx_game_dir` row with folder chooser, automatically routing `BB_GAME_DIR` on boot based on master `psx_mode`. (b) Runtime Remounting: Implemented `runtime_file_set_app0()` in `src/runtime_file.c` to update `/app0` and `/hostapp` in-place. (c) ImGui In-Game Menu: `SetPsxMode()` toggles all shaders (15-bit color, Bayer dither, point filter, vertex wobble, affine UVs) on the next frame and remounts `/app0` for model/texture streaming across warps, reloads, and weapon swaps without restart. |
| **Test 50** | Shader Cache Collision & Vulkan Pipeline Immutability Fix | `bbport-src` | Launching with PSX Demake OFF still triggered PSX shaders, and in-game toggling had no visible effect. | Root causes: (1) `pipeline_store` used identical cache keys (`ShaderBinaryVersion=21u`) for both modes; vanilla boots loaded PSX SPIR-V bytecode cached during previous runs. (2) `VkPipeline` and `VkSampler` are immutable on GPU: vertex snapping and affine UVs cannot be mutated mid-frame without pipeline recreation. Fixes: (a) Isolated shader caches: `CUSA03173` (vanilla) vs `CUSA03173_psx` (demake) in `blob_store.cpp`, bumped `ShaderBinaryVersion=22u`. (b) Hooked `psx_mode` into `runtime_restart()` in `bbport_overlay.cpp` with restart prompt. (c) Purged contaminated cache. |
| **Test 51** | Restart Environment & Asset Path Synchronization | `bbport-src/run.sh` | Enabling PSX Demake in-game and clicking restart loaded PSX shaders, but assets remained vanilla `CUSA03173`. | Root cause: `runtime_restart()` execs `bash run.sh` preserving process environment. `run.sh` read `BB_GAME_DIR` inherited from initial boot and did not check `bbport.ini`. Fix: Updated `run.sh` to parse `psx_mode` directly from `bbport.ini` on every boot and route `game` to `BB_PSX_GAME_DIR` when `1`, and `BB_VANILLA_GAME_DIR` when `0`. Added `setenv("BB_GAME_DIR", ...)` in `bbport_overlay.cpp` and `bbport_settings.cpp`. |
| **Test 52** | Artificial VRAM Throttling & GC Thrash Resolution | `run.sh` & `bbport_launcher.py` | Setting artificial VRAM caps (`BB_GC_BUDGET_MB=1536`) resulted in `TextureCache::VramShort()` entering continuous emergency GC every frame, thrashing PCIe bus and spiking loading times to 30 FPS. | Removed `BB_GC_BUDGET_MB` and `BB_VRAM_LIMIT_MB`. True hardware VRAM reduction is achieved safely via physical top-mip slicing on disk without driver panic. |
| **Test 53** | Interactive Object Multi-Bone Rigging & Clean Repair | `tools/repair_objects_clean.py` | `batch_demake_objects_ultralow.py` decimated animated prop FLVERs, misrouting multi-bone skeletons (`o000600` chest: 78 bones, `o000650` coffin: 387 bones, `o000200` door: 202 bones) and scrambling bone weights across joints, causing mesh explosions when animated in Chalice Dungeons. | Created `repair_objects_clean.py`: restored 100% pristine FromSoftware FLVER meshes and bone rigs across all 1,880 archives while slicing embedded TPF textures to $\le 256$px/128px (-93.8% texture bytes, 0 mesh risk). Deprecated `batch_demake_objects_ultralow.py` to `tools/legacy/`. |
| **Test 54** | Launcher GUI Persistence, Pango Markup & Path Unification | `launcher/bbport_launcher.py` & `bbport_i18n.py` | (a) `on_psx_mode_toggle()` forcibly called `set_active(True)` on all sub-switches on startup. (b) Premature `self.store()` call during widget construction threw `AttributeError: 'LauncherWindow' object has no attribute 'fps_row'`, leaving the window completely black. (c) Unescaped `&` in labels triggered Pango markup warnings. (d) `game_environment()` omitted `BB_CONFIG`, causing `run.sh` to read a stale config file. | Fixed forced overwrite, eliminated premature `store()` during `__init__`, escaped `&`, and exported `BB_CONFIG` and `BB_DATA_DIR` in `game_environment()`. Verified clean 0-warning launcher window. |
| **Test 55** | Live Vulkan Sampler Cache Key Hashing | `gpu/textures/texture_cache.cpp` | Toggling "Point texture filtering" in the in-game overlay had no effect because `TextureCache::GetSampler` never hashed `psx_point_filter` into its 64-bit key, causing a cache hit on the previous sampler. | Incorporated `BbSettings::Get().psx_point_filter` into the sampler hash key via `HashCombine()`. Point texture filtering now swaps dynamically between Nearest-neighbor and Bilinear in real-time mid-game without restart. |
| **Test 56** | Chroma-Locked Luminance Dithering & Visual Restoration | `gpu/render/shaders/present_encode.frag` | Independent RGB scalar quantization in `present_encode.frag` caused 25% channel ratio flips in dark areas, producing violent magenta/green/teal blotches across dark coats and stone walls. Flat grey shadow lift (`+0.045`) washed out black levels into milky haze. | Replaced with Chroma-Locked Luminance Dithering: extract luminance $Y$, apply 4x4 Bayer dither and 6-bit quantization to $Y$ only, and scale $RGB \times (Y_{quant} / Y)$ to strictly lock chromaticity angles. Eliminated 100% of color blotches, preserved inky true blacks, and re-enabled SSAO (`effect_ssao=1`) for grounding contact shadows at 50–60 FPS on GTX 1650 Max-Q. |
| **Test 57** | Blender Rigged glTF Pipeline & Havok Cloth Decoupling | `tools/pipeline/deploy_c8030_blender_psx.py` | Algorithmic QEM decimation collapsed facial features (eyes, nose, mouth cavities) on character models, and decimating cloth submeshes caused Havok solver (`SpClothVertexUpdate`) crashes. | Built decoupled glTF 2.0 interchange pipeline with Blender 5.2.3 LTS. (a) Discovered `c8030.flver` already has 46 skeletal cloth bones with complete vertex skinning. (b) Replaced cloth materials (`C[ARSN]_e_Cloth.mtd` -> `C[ARSN]_e.mtd`) and excluded `c8030_c.hkx` from `.chrbnd.dcx`, preventing `SpClothVertexUpdate` from ever initializing. (c) Resolved Blender alphabetical joint sorting bug via dynamic bone remap LUT. (d) Applied smooth shading and Gram-Schmidt tangents. (e) Sliced 24 embedded textures to $\le 256$px (TPF: 14.6 MB -> 754 KB). Deployed 10.2K tri Plain Doll model (total archive 825 KB, -95.4% size). Verified 100% stable at 86 FPS in Hunter's Dream with working talking/level-up animations and zero cloth crashes. |
| **Test 58** | Plain Doll Facial Seam Normal/Tangent Alignment & Symmetry Pass | `tools/pipeline/rigged_gltf_to_flver.py` & `tools/mesh_decimator.py` | Plain Doll face exhibited a harsh vertical lighting split down the nose bridge and forehead, plunging the right side into dark shadow while the left side remained lit. | Root causes: (1) FromSoftware's FLVER format stores the V-derivative ($tdir$) in `tangent_0`, NOT the U-derivative ($sdir$); standard glTF tangents rotated the normal mapping frame by $90^\circ$. (2) Handedness $W$ formula was inverted on mirrored UVs, turning $W$ to $+1.0$ instead of $-1.0$. (3) Decimation introduced sagittal tilt on midline vertices ($|N_x| \approx 0.315$). Fixes: (a) Aligned `tangent_0` with $tdir$ and derived $T_w = +1.0$ if $\det_{\text{UV}} \ge 0$ else $-1.0$ in `mesh_decimator.py` (dot product with vanilla $>0.95$, $100\%$ handedness match). (b) Enforced sagittal symmetry: clamped vertices within $5.0\text{mm}$ of $X=0$ to $X=0.0$, $N_x=0.0$, and $T_x=0.0$. (c) Synced default vertex colors to `[1.0, 0.0, 1.0, 1.0]` ($G=0.0$ subsurface mask). Verified photometric symmetry and smooth lighting across the face. |
| **Test 59** | Multi-Threaded Blender Demake of All Player Equipment & Trick Weapons | `tools/pipeline/batch_blender_demake_parts.py` | In-memory Python QEM decimation (`pyfqmr`) caused flat "origami" faceting on player shoulders, and armor cloth meshes (`_Cloth.mtd`) were skipped entirely to avoid Havok crashes, leaving 7.3K high-poly PS4 cloth triangles flapping against crushed low-poly torsos. | Replaced with headless Blender 5.2.3 pipeline across all 984 eligible armors (`bd_`, `hd_`, `am_`, `lg_`) and weapons (`wp_`): (a) Decoupled armor cloth: converted `_Cloth.mtd` to `_e.mtd`, stripped all `_c.hkx`/`_c.clm2` files, and decimated cloth submeshes cleanly in Blender. (b) Preserved 100% of weapon `Dummy` points across all trick weapon transformation states (`WP_A_XXXX.flver`, `_1.flver`, `_2.flver`). (c) Applied smooth shading and FromSoft tangent alignment ($\mathbf{T}_{\text{dir}}$ + $\det_{\text{UV}}$ handedness). (d) Processed 984 files in 206.3s with 12 parallel workers (0 fails): triangles reduced from 11,372,322 to 2,725,034 (-76.0%, -8.65M tris). |
| **Test 60** | Multi-Threaded Blender Demake Across All Enemy & Boss Characters | `tools/pipeline/batch_blender_demake_chr.py` | Legacy Python QEM decimation caused non-manifold spikes on beast fur shells and left 23+ Havok cloth solver dependencies active across enemy archives (`_Cloth.mtd`, `_Cloth_PDEnhanced`, `[Cloth]`), wasting CPU/GPU cycles on `SpClothVertexUpdate`. | Deployed headless Blender 5.2.3 demake engine across all 245 archives in `dvdroot_ps4/chr/`: (a) Semantic decimation ratios: mob bodies 0.22, cloth/robes 0.25, beast fur 0.20, weapons 0.35, high-poly bosses >15k tris 0.20 with smooth shading and influence prune $\le 4$. (b) Decoupled all 20 FromSoft cloth MTD variants (including `C[DSB][IBL][Cloth]`, `_PDEnhanced`, etc.) to standard skinned shaders and stripped all `_c.hkx`/`_c.clm2` solvers. (c) Strictly protected Plain Doll (`c8030`). (d) Processed 245 archives (230 FLVERs, 2,478 meshes) in 84.6s with 12 workers (0 fails): triangles cut from 11,843,416 to 2,541,360 (-78.5%, saved 9.30M tris). Verified 0 cloth solver files, 0 cloth MTDs, and 100% normalized bone weights. |
| **Test 61** | Multi-Threaded Blender Demake of All World Objects & Interactive Props | `tools/pipeline/batch_blender_demake_obj.py` | Test 53 temporarily reverted all 1,880 object archives to vanilla high-poly geometry because legacy Python QEM scrambled bone indices on animated rigs (chests, doors, coffins). Furthermore, 37 Central Yharnam hanging banners and awnings still ran active Havok cloth simulations. | Built headless Blender 5.2.3 object demake engine: (a) Preserved 100% of multi-bone skeletons via dynamic bone remap LUT (e.g. `o000650` coffin: 387 bones, `o000200` door: 202 bones, `o000600` chest: 78 bones). (b) Preserved 1,857 rigid player collision files (`.hkx`) and 505 animation archives (`.anibnd`) while purging 37 cloth solvers (`_cloth.hkx`, `_cloth.clm`, `_c.clm2`). (c) Converted 54 cloth MTDs to skinned shaders. (d) Processed all 1,885 archives in 410.9s with 12 workers (0 fails): triangles reduced from 26,744,491 to 5,478,523 (-79.5%, saved 21.27M tris). Verified 0 cloth solver leaks and 100% normalized bone weights. |
| **Test 62** | Object Gameplay Whitelisting & Retro Hard Split Normals (Anti-Plastic Sheen) | `tools/pipeline/blender_process_obj.py` & `batch_blender_demake_obj.py` | Initial uniform decimation caused gameplay regressions: doors appeared permanently closed because `default_bone_index` was reset to 0 in Blender, ladders lost horizontal rungs due to edge collapse, and `bpy.ops.object.shade_smooth()` created an unnatural specular "plastic sheen" across hard stone and iron surfaces. | (a) Banned `shade_smooth()`, enforcing `poly.use_smooth = False` (hard split normals) on all static props to restore gritty chiseled stone. (b) Whitelisted all 504 animated objects (`.anibnd`) and ladders (`o0001*`) to retain 100% pristine FLVER geometry + sliced TPF textures. (c) Decimated static heavy scenery props (fountains, carriages, statues) with hard split normals. Verified door `default_bone_index` (96, 98, 100, 102) and 100% ladder rung integrity. |
| **Test 63** | Non-Destructive World Maps Demake Engine (`map/`) | `tools/pipeline/batch_demake_maps_fidelity.py` | Prior aggressive LOD2 promotion and QEM decimation in `m22` through `m36` stripped architectural details (arches, railings, banisters) into flat rectangular boxes, creating a smooth "plastic" world appearance. | Built fidelity map demake engine: (a) Preserved 100% pristine FromSoftware LOD0 geometry across all foreground/walkable chunks (`< 2000`, 2,617 FLVERs), completely eliminating the plastic box effect. (b) Promoted gentle native LOD1 with a strict 50% floor exclusively on distant vista/cliff chunks (`>= 2000`, 5,946 FLVERs, saving 35.63M tris). (c) Kept 100% of sliced 256px/128px BXF textures (-85% to -98% VRAM). Processed all 11,033 FLVERs across 84 maps in 97.6s with 0 failures. |
| **Test 64** | Level Geometry Boundary Threshold (< 8000) & Staircase Whitelisting | `tools/pipeline/batch_demake_maps_fidelity.py` & `batch_blender_demake_obj.py` | (a) In Central Yharnam, city streets and stairs (`002000..007999`) were erroneously classified as distant vistas by the `< 2000` filter, causing stair step ribs/platforms to collapse and producing a giant exploded slanted polygon in `m22_00_00_00_002020`. (b) Movable wooden stair props (`o257200` `obj_stair_01`) collapsed under Blender decimation. | (a) Corrected level geometry threshold from `< 2000` to `< 8000`: 6,502 playable chunks preserved at 100% pristine LOD0 across all 84 maps. Chunks `002000..002030` restored, eliminating the mesh explosion and restoring stair steps/platforms. (b) Whitelisted all stair/step objects (`o257200`, `o257201`, `o214007`, `o243001`, `o259000`, `o323080`) to retain pristine FLVER geometry. |

---

## 5. Standard Execution Workflow (Order of Operations)

To ensure decimated meshes, sliced retro textures, and engine modifications remain consistent and never overwrite one another, execute pipelines in this order:

```bash
# 1. Plain Doll Definitive Demake (chr/c8030)
# (Historical baseline already deployed to sandbox, script archived in tools/archive/)
uv run python tools/archive/demake_c8030_doll.py --deploy

# 2. All Player Equipment, Armor Sets & Trick Weapons (Ultra-Low PSX Demake Pass)
# Cuts rigid body to ~20-30%, saves 6.6M tris across parts/:
uv run python tools/batch_demake_parts_ultralow.py --all --deploy --workers 12

# 3. All Enemies & Bosses (Ultra-Low PSX Demake Pass)
# Decimates rigid bodies & alpha fur cards to 20-25%, strictly preserves Havok cloth & Plain Doll (c8030), saves 7.9M tris across chr/:
uv run python tools/batch_demake_characters_ultralow.py --all --deploy --workers 12

# 3. Environment Maps (Geometry LOD Promotion + In-Place BXF Textures + Map Objects)
# Hunter's Dream (m21):
uv run python tools/batch_demake_environment.py --map m21 --clean --all --dim 32
# Central Yharnam (m22):
uv run python tools/batch_demake_environment.py --map m22 --clean --all --dim 32 --downsample-pbr
# Chalice Dungeons (m29 modular tilesets):
uv run python tools/batch_demake_environment.py --map m29 --clean --flvers --textures --dim 32

# 4. Interactive World Objects & Props (Clean Geometry + Sliced Textures)
# Restores pristine FLVER meshes/rigs for all 1,880 objects, slices embedded textures -94%:
uv run python tools/repair_objects_clean.py --all --workers 12

# 5. Ultra-Low World Geometry Decimation Pass
uv run python tools/batch_demake_world_ultralow.py --map m21 --preset aggressive --deploy

# 6. True Hardware VRAM Reduction (Mip Slicing Across All Assets)
# World Environment Maps (BXF containers, slice to <= 256px):
uv run python tools/batch_shrink_world_textures.py --map m21 --target 256 --deploy
# Characters & Enemies (chr, slice diffuse to <= 256px, secondary to <= 128px, keep fur intact):
uv run python tools/shrink_chr_textures.py --category chr --all --textures '*' --target 256 --secondary-target 128 --workers 12 --deploy
# Weapons & Armor Equipment (parts, slice diffuse to <= 256px, secondary to <= 128px):
uv run python tools/shrink_chr_textures.py --category parts --all --textures '*' --target 256 --secondary-target 128 --workers 12 --deploy

# 7. Clear Vulkan Pipeline Cache
rm -f ~/.local/share/bbhost/data/bbhost/*.bin

# 8. Engine Build & Launch (bbport Native Workflow)
# Fast incremental GPU rebuild:
ninja -C ../bbport-src/out/gpu
# Full engine rebuild & verification:
cd ../bbport-src && bash build.sh
# Launch native application (Desktop Launcher runs build.sh automatically):
bbport
```

---

## 6. Recommended 60 FPS Performance Profile (GTX 1650 / Low-Mid Range)

To achieve rock-solid 50–60 FPS with authentic retro aesthetic and pristine visual stability:

```ini
# bbport.ini configuration
preset = 2                    # FSR 3 Balanced (960x600 internal render) - cuts deferred fillrate by 65%
effect_ssao = 1               # Screen-Space Ambient Occlusion - grounds characters & geometry
effect_dynamic_shadows = 0    # Dynamic Light Shadows OFF - saves ~3-5ms deferred light pass
effect_aa = 0                 # Post-AA OFF - crisp retro edges
psx_dither = 1                # Chroma-Locked Bayer Luminance Dithering ON
psx_point_filter = 0          # Bilinear texture sampling ON (prevents Nyquist high-frequency crawl)
psx_vertex_snap = 0           # Screen-space vertex jitter OFF (eliminates camera motion fatigue)
psx_affine = 0                # Affine perspective distortion OFF (clean corridor geometry)
```

---

## 7. Interactive Objects, Ladders & Animated Rigs Policy

- **Pristine Mechanism Whitelist**: All interactive ladders across the game (Chalice ladders `o2980*`, `o2981*`, `o2982*`, plus `o000100`, `o00992*`, `o220002`, `o23991*`, `o24051*`, `o282030`, `o3210*`, `o32309*`, `o32609*`, `o34210*`, `o35050*`, `o353010`, `o360010`, `o368*`), Chalice door statues (`o290500`–`o290504`, `o291110`), and bone-offset workshop doors (`o210010`–`o210013`) are strictly kept at 100% pristine FromSoftware geometry and rigging. Standard decimation dissolves thin 3D ladder rungs and causes multi-bone rigid objects (such as `o298000`/`o298100` ladders with `lower_Lantern` child bones) to displace vertically by $-0.688$ m, floating off the floor.
- **Chalice Composite Assemblies & Corridor Lighting Whitelist**: Multi-bone composite room props (`o2996*`, `o2949*`, `o2994*`, `o2999*`), corridor hanging chandeliers (`o2953*`, `o2950*`, `o2951*`, `o2952*`, `o2956*`, `o2961*`), pedestal candlestick statues (`o2973*`, `o2937*`), and cage elevators (`o2902*`, `o2903*`, `o2904*`) are strictly whitelisted for pristine vanilla bypass. Decimation collapses thin chain links vertically by $+2.09$ m and destroys spatial bounding boxes, causing chandeliers to clip inside statues and plinths to float off the floor.
- **FLVER Bounding Box Mathematical Invariant**: In `tools/soulstruct_patch.py`, `refresh_bounding_boxes` must compute submesh and model bounding boxes in model space by accumulating parent bone hierarchy affine matrices ($M_{\text{parent}} \cdot T \cdot R \cdot S$). Untransformed local bounds break engine frustum and occlusion culling, making objects vanish or render misaligned.
- **World Maps Native LOD0 Invariant**: All 3,498 world map chunks (`map/*.flver.dcx`) strictly retain pristine FromSoftware LOD0 geometry. LOD1 promotion destroys stairs, handrails, and platforms and causes catastrophic mesh explosions in playable zones.
- **Alpha Cutout Protection (`has_alpha_cutout`)**: Ladders (`o000100`), workshop doors (`o210010`–`o210013`), and glass props (`o213002`) strictly retain pristine vanilla TPF containers (1.6 MB with intact BC3 alpha).
- **Static Decimation Target**: All 1,350+ static decorative props (rubble, tombstones, fences, carts, plain pillars) receive retro low-poly Blender decimation in pure bone-local space (`has_skin = False`).

---

## 8. Empirical Performance Findings & Dual-Bottleneck Architecture

Telemetry on GTX 1650 Max-Q (4GB VRAM):

```
Vanilla Retail (PSX OFF, 1050p):     2,449 MiB | 22–27 FPS  (Compute/Fillrate Bottlenecked)
Vanilla Retail (PSX ON, 1050p):      2,449 MiB | 40–50 FPS  (+80% FPS, No Aniso, No Dynamic Light Shadows)
PSX Mod Stage  (PSX ON, 1050p P2):   2,083 MiB | 55–60 FPS  (-366 MiB VRAM, Eliminates Micro-Triangles)
PSX Mod Stage  (Great Bridge P2):    2,385 MiB | ~55 FPS    (Dense Outdoor Area Baseline)
PSX Mod Stage  (Great Bridge P3):    2,244 MiB | ~65 FPS    (-141 MiB via FSR Performance Render Scale)
PSX Mod Stage  (Great Bridge 800p):  2,155 MiB | ~75 FPS    (-230 MiB vs 1050p P2)
PSX Mod Stage  (Chalice 800p):       2,060–2,127 MiB | 80–90 FPS (Solid High-FPS Floor)
PSX Mod Stage  (Hunter's Dream 800p):1,952 MiB | 80–90 FPS  (SUB-2GiB BARRIER BROKEN: < 2,048 MiB)
```

1. **ALU / Fillrate Relief**: `effect_dynamic_shadows=0`, `psx_point_filter=1` (disables anisotropic filtering), and `psx_affine=1` (`spv::Decoration::NoPerspective`) liberate GPU ALUs and TMU caches.
2. **Bandwidth & Front-End Relief**: Low-poly meshes + $128\times 128$ / $256\times 256$ textures free 366 MiB VRAM and stop primitive pipeline stalls.

---

## 9. Clean Distribution & Offline Mod Reconstruction System

### 100% Legal Redistribution Model (XOR Differential Container)
Distributing modified `.dcx` files directly risks copyright strikes from Sony/FromSoftware. The project solves this using an autonomous XOR differential container (`.patch`):
- **Mathematical Principle**: For each file, the patch stores $D = M \oplus V$. The patch file contains pure pseudo-random XOR entropy. Without the user's legally owned PlayStation 4 retail dump (`CUSA03173`), it is mathematically impossible to reconstruct a single 3D model, texture, or audio clip.
- **Client Requirements**: Zero external packages (`pip`, `gcc`, `blender`, `soulstruct` NOT required). Runs in 7.0 seconds on standard Python 3.9+ using native arbitrary-precision integer bitwise operations.

### Developer CLI (Generate Patch):
```bash
uv run python tools/pipeline/create_psx_patch.py \
  --vanilla CUSA03173 \
  --mod "../bbport-src/mods/Bloodborne PSX Demake" \
  --out dist/bloodborne_psx_demake.patch
```
*Performance: 25.2s total processing time, 16.4s full in-memory SHA256 verification, < 150 MB RAM.*

### Client / End-User CLI (Reconstruct Mod on Any PC):
```bash
python3 apply_psx_patch.py \
  --game /path/to/CUSA03173 \
  --patch bloodborne_psx_demake.patch \
  --out "Bloodborne PSX Demake"
```
*Performance: 7.01s total reconstruction time, 100.000000% bit-for-bit SHA256 parity across all 2,669 files.*

### Modder Pipeline CLI (Rebuild from Scratch via Blender):
```bash
uv run python tools/pipeline/build_from_scratch.py \
  --vanilla CUSA03173 \
  --psx CUSA03173-PSX \
  --mod-out "../bbport-src/mods/Bloodborne PSX Demake"
```

---

## 10. Low-VRAM (<2 GiB) Roadmap

To support 2GB VRAM cards and low-spec laptop iGPUs:
1. **FSR Internal Render Scale**: Lower internal render resolution (e.g., 960x540 / 720p FSR performance) to reduce 1080p deferred G-Buffer allocations by ~200 MiB.
2. **Remaining Map Textures (`map/*.tpf.dcx`)**: Downscale the remaining world environment map textures to $128\times 128$ / $256\times 256$, recovering ~200–250 MiB.
3. **Vulkan Sampler Mip Bias**: In `gpu/textures/sampler.cpp`, optionally clamp `minLod = 1.0f` or apply `extra_lod_bias = 1.5f` to skip Mip 0 (75% texel reduction), immediately reclaiming ~300 MiB.

---

## 11. Upstream v0.7 Integration & Native Build Quirks

### 11.1 GNU `ld` Undefined Symbol Error (`ffxVkShaderOverride`, `ffxVkJobMark`)
- **Root Cause**: Upstream v0.7 introduced `FfxShaders` and `FgProfile` hooks declared as `extern "C" bool (*ffxVkShaderOverride)(...);` and `extern "C" void (*ffxVkJobMark)(...);`. In C++, an `extern "C"` declaration without an initializer is strictly an unresolved external declaration, not a tentative definition. When linking host binaries (e.g., `bb-probe`) against `libbbgpu.so`, GNU `ld` fails with:
  ```
  /usr/bin/ld: out/gpu/libbbgpu.so: undefined reference to `ffxVkShaderOverride`
  /usr/bin/ld: out/gpu/libbbgpu.so: undefined reference to `ffxVkJobMark`
  ```
- **Fix / Workaround**: Provide explicit zero-initialization (`= nullptr;`) at file scope in `gpu/upscale/ffx_shaders.cpp` and `gpu/upscale/fg_profile.cpp`, placing the symbols into `.bss` of `libbbgpu.so`.

### 11.2 Overlay Modularization & Windows CRLF Formatting
- **Root Cause**: Upstream v0.7 split `bbport_overlay.cpp` into `bbport_overlay_sections.cpp` and `bbport_overlay_internal.h`, while introducing CRLF line endings for native Windows compatibility.
- **Fix / Workaround**:
  - Implemented `void RetroGraphicsSection(BbSettings::Values& s)` inside `bbport_overlay_sections.cpp` under the `BbOverlay::detail` namespace.
  - Added declaration to `bbport_overlay_internal.h` and hooked call in `bbport_overlay.cpp`.
  - Preserved CRLF line endings on modified files to maintain clean, minimal git diffs.

### 11.3 Launcher Modularization
- **Root Cause**: In upstream v0.7, top-level constants (`INI_DEFAULTS`, `MODEL_LOD`, `EFFECTS`) and common helpers were refactored into `bbport_launcher_common.py`.
- **Fix / Workaround**:
  - Defined `RETRO_RESOLUTIONS` and default `retro_*` values in `launcher/bbport_launcher_common.py`.
  - Added `retro_group` under `sec["graphics"]` in `launcher/bbport_launcher.py`.
  - Merged retro settings into `store()` and `environment()`.


