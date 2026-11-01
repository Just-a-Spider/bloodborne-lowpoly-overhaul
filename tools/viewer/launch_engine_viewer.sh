#!/usr/bin/env bash
# ==============================================================================
# Isolated Bloodborne Engine Model Viewer Launcher
# Runs bbhost with 100% save file protection and asset overlay injection.
# ==============================================================================
set -euo pipefail

BBHOST_DIR="${BBHOST_DIR:-$HOME/Games/bbhost}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GAME_DIR="${GAME_DIR:-$REPO_ROOT/CUSA03173-PSX}"
REAL_DATA_DIR="$HOME/.local/share/bbhost/data"
REAL_SAVE_DIR="$REAL_DATA_DIR/saves"
REAL_CONFIG_DIR="$HOME/.config/bbhost"

SANDBOX_DIR="/tmp/bb_engine_viewer_sandbox"
SANDBOX_DATA="$SANDBOX_DIR/data"
SANDBOX_MODS="$SANDBOX_DIR/mods"
SANDBOX_CFG="$SANDBOX_DIR/viewer.toml"
PRE_HASHES="$SANDBOX_DIR/pre_hashes.sha256"

# 1. Parse Arguments
MODEL_ARG="${1:-}"

echo "=================================================================="
echo ">>> BLOODBORNE IN-ENGINE ISOLATED MODEL VIEWER <<<"
echo "=================================================================="

# 2. Pre-flight Save Check & Lock
echo "[1/5] Locking real saves into READ-ONLY mode..."
mkdir -p "$SANDBOX_DIR"
if [ -d "$REAL_SAVE_DIR" ]; then
    find "$REAL_SAVE_DIR" -type f -exec sha256sum {} + > "$PRE_HASHES" 2>/dev/null || true
    chmod -R a-w "$REAL_SAVE_DIR"
    echo "  Real save locked: $(wc -l < "$PRE_HASHES" 2>/dev/null || echo 0) files protected."
fi

# Cleanup Trap: Restore write permissions & verify checksums
verify_save_integrity() {
    echo ""
    echo "[Cleanup] Restoring real save directory permissions..."
    if [ -d "$REAL_SAVE_DIR" ]; then
        chmod -R u+w "$REAL_SAVE_DIR"
        if [ -s "$PRE_HASHES" ]; then
            echo "[Audit] Verifying SHA-256 save checksums..."
            if sha256sum --quiet -c "$PRE_HASHES"; then
                echo "=================================================================="
                echo ">>> AUDIT PASSED: ZERO BYTES MODIFIED IN REAL SAVES (100% INTACT) <<<"
                echo "=================================================================="
            else
                echo ">>> WARNING: Save hash mismatch detected! Investigate immediately. <<<"
            fi
        fi
    fi
}
trap verify_save_integrity EXIT INT TERM

# 3. Setup Sandbox Directories
echo "[2/5] Initializing isolated sandbox in $SANDBOX_DIR..."
rm -rf "$SANDBOX_DATA" "$SANDBOX_MODS"
mkdir -p "$SANDBOX_DATA/saves"
mkdir -p "$SANDBOX_MODS/dvdroot_ps4/chr"
mkdir -p "$SANDBOX_MODS/dvdroot_ps4/obj"
mkdir -p "$SANDBOX_MODS/dvdroot_ps4/map"

# Create symlinks inside mods for non-prefixed paths
ln -sfn "$SANDBOX_MODS/dvdroot_ps4/chr" "$SANDBOX_MODS/chr"
ln -sfn "$SANDBOX_MODS/dvdroot_ps4/obj" "$SANDBOX_MODS/obj"
ln -sfn "$SANDBOX_MODS/dvdroot_ps4/map" "$SANDBOX_MODS/map"

# Copy user's save to sandbox so they can load directly into Hunter's Dream
if [ -d "$REAL_SAVE_DIR/SPRJ0005" ]; then
    echo "  Seeding sandbox with copy of existing Hunter's Dream save..."
    cp -r "$REAL_SAVE_DIR/SPRJ0005" "$SANDBOX_DATA/saves/"
    chmod -R u+w "$SANDBOX_DATA/saves"
fi

# Copy any existing cache or trophies to avoid cold-start delays
if [ -f "$REAL_DATA_DIR/cache.bin" ]; then
    cp "$REAL_DATA_DIR/cache.bin" "$SANDBOX_DATA/" 2>/dev/null || true
fi
if [ -d "$REAL_DATA_DIR/bbhost" ]; then
    cp -r "$REAL_DATA_DIR/bbhost" "$SANDBOX_DATA/" 2>/dev/null || true
fi

# 4. Stage Target Model into Mods Overlay
if [ -n "$MODEL_ARG" ]; then
    MODEL_PATH="$(realpath "$MODEL_ARG")"
    MODEL_FILE="$(basename "$MODEL_PATH")"
    echo "[3/5] Staging model into mods overlay: $MODEL_FILE"
    
    # Check if character model (cXXXX) or object (oXXXX) or map (mXX)
    if [[ "$MODEL_FILE" =~ ^c[0-9]{4} ]]; then
        cp "$MODEL_PATH" "$SANDBOX_MODS/dvdroot_ps4/chr/$MODEL_FILE"
        echo "  Injected into overlay: /dvdroot_ps4/chr/$MODEL_FILE"
    elif [[ "$MODEL_FILE" =~ ^o[0-9]{4} ]]; then
        cp "$MODEL_PATH" "$SANDBOX_MODS/dvdroot_ps4/obj/$MODEL_FILE"
        echo "  Injected into overlay: /dvdroot_ps4/obj/$MODEL_FILE"
    else
        cp "$MODEL_PATH" "$SANDBOX_MODS/dvdroot_ps4/$MODEL_FILE"
        echo "  Injected into overlay: /dvdroot_ps4/$MODEL_FILE"
    fi
else
    echo "[3/5] No custom model specified; running sandbox with default assets."
fi

# 5. Generate Sandbox Configuration
echo "[4/5] Writing isolated configuration: $SANDBOX_CFG"
cat <<EOF > "$SANDBOX_CFG"
[paths]
app0 = "$GAME_DIR"
eboot = "$GAME_DIR/eboot.elf"
data = "$SANDBOX_DATA"
mods = "$SANDBOX_MODS"

[online]
require_account = false
online_id = "DemakeViewer"
host = "127.0.0.1"
verify_tls = false
auth_server = "http://127.0.0.1"

[player]
name = "DemakeViewer"

[video]
width = 1280
height = 720
fps_cap = 30
headless = false

[startup]
skip_intro = true
setup_window = false

[streaming]
all_post_processors = true

[plugins]
debug_menu = true
EOF

# 6. Launch bbhost via prime-run
echo "[5/5] Launching isolated Bloodborne engine..."
echo "------------------------------------------------------------------"
echo "Controls:"
echo "  [ \` ] (Backtick) : Open FromSoftware In-Engine Debug Menu"
echo "  Hunter's Dream   : Stand directly in front of Plain Doll"
echo "  Real Save Status : PHYSICALLY LOCKED (read-only chmod + sha256 checked)"
echo "------------------------------------------------------------------"

export XDG_DATA_HOME="$SANDBOX_DIR/xdg_data"
export XDG_CONFIG_HOME="$SANDBOX_DIR/xdg_config"
export BBHOST_CONFIG="$SANDBOX_CFG"

# Hardware performance optimizations (GTX 1650 Max-Q)
export BBHOST_TIGHT_MEMORY=1
export BBHOST_BUFFER_SHADOW=1
export BBHOST_WATCHDOG_S=60
export BBHOST_CS_OPTIMIZE=1
export BBHOST_FAST_LOADING=1
export BBHOST_UNTILE_THREADS=4
export BBHOST_TEX_PREP_THREADS=4
export BBHOST_SUBMIT_THREAD=1

# Test switches
export BBHOST_TEST_WARP=1
export BBHOST_TEST_UNLOCK_LAMPS=1

cd "$BBHOST_DIR"
if command -v prime-run &>/dev/null; then
    prime-run ./bbhost --config "$SANDBOX_CFG" --data "$SANDBOX_DATA"
else
    ./bbhost --config "$SANDBOX_CFG" --data "$SANDBOX_DATA"
fi
