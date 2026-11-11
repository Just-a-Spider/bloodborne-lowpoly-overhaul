# Interface Contract: bbhost Launcher & Steam Shortcut

**Feature**: `006-bbhost-retro-plugin`

## Executable Wrapper (`/home/andre/.local/bin/bbhost`)

The wrapper mirrors `/home/andre/.local/bin/bbport` and routes execution through the offload runner:

```bash
#!/usr/bin/env bash
set -euo pipefail

HERE="/home/andre/Games/bbhost"
cd "$HERE"
exec /home/andre/.local/bin/offload --no-boost "$HERE/run-bbhost.sh" "$@"
```

### Environment Variables & Flags Configured in `run-bbhost.sh`:
- `BBHOST_TIGHT_MEMORY=1`: Enforces 4GB VRAM ceiling for low-spec GTX 1650.
- `BBHOST_BUFFER_SHADOW=1`: Prevents buffer contention on low memory bandwidth.
- `BBHOST_CS_OPTIMIZE=1`: Optimizes compute shader dispatches.
- `BBHOST_FAST_LOADING=1`: Enables parallel asset preloading.
- `BBHOST_UNTILE_THREADS=4`: Parallel texture untile worker count.

## Desktop & Steam Entry (`~/.local/share/applications/io.github.bbhost.desktop`)

```ini
[Desktop Entry]
Type=Application
Name=Bloodborne (bbhost)
GenericName=Bloodborne Native Host Runner
Comment=Run Bloodborne Low-Poly Overhaul natively with bbhost
Exec=/home/andre/.local/bin/bbhost
Icon=/home/andre/Games/bbhost/res/icon.png
Categories=Game;
Keywords=bloodborne;bbhost;demake;psx;
StartupNotify=true
```
