# Quickstart & Verification Guide: bbhost Migration & Retro Plugin

**Feature**: `006-bbhost-retro-plugin`
**Date**: 2026-11-11

## Prerequisites

1. Linux x86-64 workstation with NVIDIA dedicated GPU offload tool (`/home/andre/.local/bin/offload`).
2. Build tools: `cmake`, `ninja`, `g++` (supporting C++20).
3. Verified pristine base game directory at `/home/andre/Games/Bloodborne/CUSA03173` (immutable).
4. Save directory at `~/.local/share/bbhost/data/saves` (protected).

## Scenario 1: Clean Host Runner Build & Migration

Prove that obsolete `bbhost v0.2.18` is replaced by compiled `v0.2.32` without touching player saves.

### Step 1: Pre-Migration Backup & Save Verification
```bash
# Verify saves are untouched and present
ls -la ~/.local/share/bbhost/data/saves

# Backup existing configuration
cp ~/.config/bbhost/bbhost.toml ~/.config/bbhost/bbhost.toml.bak 2>/dev/null || true
```

### Step 2: Compile & Deploy bbhost v0.2.32
```bash
# Build from bbhost-src
cd /home/andre/Games/bbhost-src
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j$(nproc)

# Retire legacy folder and install new build
rm -rf /home/andre/Games/bbhost.v0.2.16.bak /home/andre/Games/bbhost/bbhost
# Move build output and assets to /home/andre/Games/bbhost
```

### Step 3: Verification
```bash
/home/andre/Games/bbhost/bbhost --help
# Expected: Confirms version v0.2.32
```

---

## Scenario 2: Build & Deploy Pure Retro Plugin

Prove that `lowpoly_overhaul.so` compiles and loads into `bbhost`.

### Step 1: Compile Plugin
```bash
cd /home/andre/Games/reference/plugins/lowpoly_overhaul
g++ -O3 -shared -fPIC -std=c++20 \
    -I/home/andre/Games/bbhost/include \
    lowpoly_overhaul.cpp -o lowpoly_overhaul.so

# Deploy to bbhost plugins directory
cp lowpoly_overhaul.so /home/andre/Games/bbhost/plugins/
```

### Step 2: Verification
```bash
# Verify plugin exported symbols
nm -D /home/andre/Games/bbhost/plugins/lowpoly_overhaul.so | grep bb_plugin
# Expected: bb_plugin_info, bb_plugin_options, bb_plugin_init, bb_plugin_image
```

---

## Scenario 3: Launch & End-to-End Visual Verification

Prove that game launches via Steam wrapper and renders with complete 32-bit PSX graphics.

### Step 1: Launch Game
```bash
/home/andre/.local/bin/bbhost
```

### Step 2: In-Game Verification Checklist
1. **Save Loading**: Continue game from main menu; character loads into existing save progress.
2. **Vertex Snapping**: Walk near Hunter's Dream workshop; geometry corners jump along grid (240p).
3. **Affine Mapping**: Observe wall and floor textures at acute angles; textures exhibit perspective-incorrect warping.
4. **Luminance Dither**: Stand in dark shadow; lighting transitions display fine monochrome 4x4 Bayer cross-hatching without green/magenta rainbow grain.
5. **Point Filtering**: Examine character garment textures; crisp nearest-neighbor texels without bilinear blur.
6. **Live Menu Control**: Press F9; toggle individual retro effects on and off in real-time.

---

## Scenario 4: bbport Save Import & Integrity Verification

Prove that player saves from `bbport` import safely into `bbhost` with automatic pre-import backup.

### Step 1: Run Save Import Utility
```bash
python3 /home/andre/Games/reference/tools/import_bbport_saves.py
# Expected:
# 1. Detects ~/.local/share/bbport/user/savedata/1/CUSA00207/SPRJ0005
# 2. Creates ~/.local/share/bbhost/data/saves/SPRJ0005.pre_import_bak_<timestamp>
# 3. Copies and validates userdata0000 (1,310,720 bytes) and related files
# 4. Reports successful sync
```

### Step 2: Verification in bbhost
```bash
/home/andre/.local/bin/bbhost
# Load game -> verify character level, inventory, and location match bbport campaign progress
```

