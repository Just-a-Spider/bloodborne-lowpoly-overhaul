"""
Master 3D Model Diagnostic Viewer & Visual Inspection Suite for Bloodborne PSX Demake.

Features:
- Instant interactive WebGL 3D model inspection in browser (Three.js OrbitControls).
- Live A/B Comparison: Toggle between PSX Demake and Vanilla Clean models in-place.
- Wireframe overlay, flat/smooth shading modes, and submesh isolation hierarchy.
- Geometry metrics HUD: Total triangles, vertices, reduction percentage, AABB dimensions.
- Optional Blender 5.2.2 integration (--blender).
- Headless snapshot rendering for visual QA (--snapshot).
"""

import sys, os, io, argparse, webbrowser, subprocess, tempfile
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

sys.path.insert(0, os.path.dirname(__file__))
from flver_to_gltf import convert_container_to_glb

HTML_TEMPLATE_PATH = Path(__file__).parent / "viewer_template.html"

class ModelViewerServer(BaseHTTPRequestHandler):
    """Micro HTTP server providing GLB models and Three.js client."""
    demake_glb = b''
    vanilla_glb = b''
    model_name = "Model Viewer"

    def do_HEAD(self):
        self.do_GET(head_only=True)

    def do_GET(self, head_only: bool = False):
        if self.path in ('/', '/index.html'):
            html = HTML_TEMPLATE_PATH.read_text(encoding='utf-8')
            html = html.replace('Model Diagnostic Viewer', f'{self.model_name} — PSX Diagnostic Viewer')
            data = html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            if not head_only:
                self.wfile.write(data)

        elif self.path == '/model.glb':
            if not self.demake_glb:
                self.send_error(404, "Demake GLB not loaded")
                return
            self.send_response(200)
            self.send_header('Content-Type', 'model/gltf-binary')
            self.send_header('Content-Length', str(len(self.demake_glb)))
            self.end_headers()
            if not head_only:
                self.wfile.write(self.demake_glb)

        elif self.path == '/vanilla.glb':
            if not self.vanilla_glb:
                self.send_error(404, "Vanilla GLB not available")
                return
            self.send_response(200)
            self.send_header('Content-Type', 'model/gltf-binary')
            self.send_header('Content-Length', str(len(self.vanilla_glb)))
            self.end_headers()
            if not head_only:
                self.wfile.write(self.vanilla_glb)

        else:
            self.send_error(404, "File not found")

    def log_message(self, format, *args):
        # Suppress routine HTTP log spam
        pass

def render_blender_snapshot(glb_path: Path, output_png: Path, yaw: float = 180.0, pitch: float = 5.0, focus: str = "full"):
    """Renders an offscreen preview snapshot using Blender headless mode."""
    blender_script = f"""
import bpy, math, mathutils
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=r'{glb_path}')

# Add Camera
cam_data = bpy.data.cameras.new("Camera")
cam_obj = bpy.data.objects.new("Camera", cam_data)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

# Position camera to frame all objects
bbox_min = [1e9, 1e9, 1e9]
bbox_max = [-1e9, -1e9, -1e9]
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        for v in obj.bound_box:
            world_v = obj.matrix_world @ mathutils.Vector(v)
            for i in range(3):
                bbox_min[i] = min(bbox_min[i], world_v[i])
                bbox_max[i] = max(bbox_max[i], world_v[i])

center = [(bbox_min[i] + bbox_max[i]) / 2.0 for i in range(3)]
size = max(bbox_max[0] - bbox_min[0], bbox_max[1] - bbox_min[1], bbox_max[2] - bbox_min[2])

focus = '{focus}'
if focus == 'head':
    target = mathutils.Vector((center[0], center[1], bbox_max[2] - 0.15))
    dist = max(0.4, size * 0.45)
else:
    target = mathutils.Vector((center[0], center[1], center[2]))
    dist = size * 2.2

rad_yaw = math.radians({yaw})
rad_pitch = math.radians({pitch})

dx = dist * math.cos(rad_pitch) * math.sin(rad_yaw)
dy = -dist * math.cos(rad_pitch) * math.cos(rad_yaw)
dz = dist * math.sin(rad_pitch)

cam_obj.location = (target.x + dx, target.y + dy, target.z + dz)
direction = target - cam_obj.location
cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# Studio Light
light_data = bpy.data.lights.new("Sun", type='SUN')
light_data.energy = 3.5
light_obj = bpy.data.objects.new("Sun", light_data)
bpy.context.scene.collection.objects.link(light_obj)
light_dir = target - mathutils.Vector((target.x + dx * 0.8 + 0.5, target.y + dy * 0.8, target.z + dz + 1.0))
light_obj.rotation_euler = light_dir.to_track_quat('-Z', 'Y').to_euler()

# Fill Light
fill_data = bpy.data.lights.new("FillSun", type='SUN')
fill_data.energy = 1.2
fill_obj = bpy.data.objects.new("FillSun", fill_data)
bpy.context.scene.collection.objects.link(fill_obj)
fill_dir = target - mathutils.Vector((target.x - dx * 0.5, target.y - dy * 0.5, target.z + 1.5))
fill_obj.rotation_euler = fill_dir.to_track_quat('-Z', 'Y').to_euler()

# Render settings
bpy.context.scene.render.resolution_x = 1280
bpy.context.scene.render.resolution_y = 960
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.filepath = r'{output_png}'
bpy.ops.render.render(write_still=True)
"""
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as tf:
        tf.write(blender_script)
        tf_name = tf.name

    try:
        subprocess.run(['blender', '-b', '-P', tf_name], check=True, stdout=subprocess.DEVNULL)
        print(f"[SUCCESS] Rendered offscreen snapshot -> {output_png} (yaw={yaw}deg, pitch={pitch}deg, focus={focus})")
    finally:
        os.unlink(tf_name)

def find_target_asset(target_str: str, mods_dir: Path, vanilla_dir: Path) -> Path:
    """Resolves a target file path or asset code (e.g. c2500, o282020) against mods or vanilla game."""
    target_path = Path(target_str)
    if target_path.exists():
        return target_path.resolve()

    if (mods_dir / target_str).exists():
        return (mods_dir / target_str).resolve()
    if (vanilla_dir / target_str).exists():
        return (vanilla_dir / target_str).resolve()

    clean_target = target_str.strip()
    patterns = [clean_target]
    if not any(clean_target.endswith(ext) for ext in [".dcx", ".flver", ".gltf", ".glb"]):
        patterns.extend([
            f"{clean_target}.chrbnd.dcx",
            f"{clean_target}.partsbnd.dcx",
            f"{clean_target}.objbnd.dcx",
            f"{clean_target}.flver.dcx",
            f"{clean_target}*.dcx",
        ])

    for pat in patterns:
        if mods_dir.exists():
            matches = list(mods_dir.rglob(pat))
            if matches:
                exact = [m for m in matches if m.name.lower() == pat.lower()]
                return (exact[0] if exact else matches[0]).resolve()

    for pat in patterns:
        if vanilla_dir.exists():
            matches = list(vanilla_dir.rglob(pat))
            if matches:
                exact = [m for m in matches if m.name.lower() == pat.lower()]
                return (exact[0] if exact else matches[0]).resolve()

    raise FileNotFoundError(f"Target '{target_str}' not found as file or within mods dir '{mods_dir}' or game dir '{vanilla_dir}'.")

def find_vanilla_counterpart(target_path: Path, vanilla_dir: Path) -> Path | None:
    """Locates the vanilla counterpart for a given modded asset."""
    if not vanilla_dir.exists():
        return None

    # Strategy 1: Check dvdroot_ps4 relative path
    parts = list(target_path.parts)
    if "dvdroot_ps4" in parts:
        idx = parts.index("dvdroot_ps4")
        rel_subpath = Path(*parts[idx:])
        cand1 = vanilla_dir / rel_subpath
        if cand1.exists():
            return cand1.resolve()
        cand2 = vanilla_dir / Path(*parts[idx+1:])
        if cand2.exists():
            return cand2.resolve()

    # Strategy 2: If target path belongs to dev folder CUSA03173-PSX
    target_str = str(target_path)
    if "CUSA03173-PSX" in target_str:
        cand3 = Path(target_str.replace("CUSA03173-PSX", str(vanilla_dir)))
        if cand3.exists():
            return cand3.resolve()

    # Strategy 3: Search by exact filename inside vanilla directory
    matches = list(vanilla_dir.rglob(target_path.name))
    if matches:
        return matches[0].resolve()

    return None

def main():
    parser = argparse.ArgumentParser(description="Bloodborne 3D Model Diagnostic Visualizer")
    parser.add_argument("target", help="Path to .partsbnd.dcx, .chrbnd.dcx, .flver.dcx, or asset code (e.g. c2500, o282020)")
    parser.add_argument("--game", "--vanilla-root", dest="game_dir",
                        default=os.environ.get("BLOODBORNE_GAME_DIR", "CUSA03173"),
                        help="Path to vanilla Bloodborne game root (default: CUSA03173 or $BLOODBORNE_GAME_DIR)")
    parser.add_argument("--mods-dir", dest="mods_dir",
                        default=os.environ.get("BLOODBORNE_MODS_DIR", "mods"),
                        help="Path to modular mods directory (default: mods or $BLOODBORNE_MODS_DIR)")
    parser.add_argument("--vanilla", help="Explicit path to vanilla reference file (auto-detected if omitted)")
    parser.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open web browser")
    parser.add_argument("--export-glb", help="Export as .glb file and exit")
    parser.add_argument("--blender", action="store_true", help="Launch in Blender 5.2.2")
    parser.add_argument("--rust", action="store_true", help="Launch native Rust desktop viewer (bb-viewer)")
    parser.add_argument("--engine", action="store_true", help="Launch in-engine isolated viewer via bbhost (100%% save protection)")
    parser.add_argument("--snapshot", help="Render offscreen snapshot to PNG and exit")
    parser.add_argument("--yaw", type=float, default=180.0, help="Camera yaw angle in degrees (default: 180.0 for front view, 0.0 for back)")
    parser.add_argument("--pitch", type=float, default=5.0, help="Camera pitch elevation in degrees (default: 5.0)")
    parser.add_argument("--focus", choices=["full", "head"], default="full", help="Camera focus framing (default: full)")

    args = parser.parse_args()
    vanilla_dir = Path(args.game_dir).resolve()
    mods_dir = Path(args.mods_dir).resolve()

    try:
        target_path = find_target_asset(args.target, mods_dir, vanilla_dir)
    except FileNotFoundError as err:
        print(f"Error: {err}")
        sys.exit(1)

    vanilla_path = Path(args.vanilla).resolve() if args.vanilla else find_vanilla_counterpart(target_path, vanilla_dir)

    # In-Engine isolated viewer mode
    if args.engine:
        engine_script = Path(__file__).parent / "launch_engine_viewer.sh"
        if not engine_script.exists():
            print(f"Error: Engine launcher script not found at {engine_script}")
            sys.exit(1)
        print(f"Launching in-engine isolated viewer for {target_path.name}...")
        subprocess.run([str(engine_script), str(target_path)])
        return

    # Native Rust viewer mode
    if args.rust:
        rust_bin = Path(__file__).parent / "bb_viewer" / "target" / "release" / "bb-viewer"
        if not rust_bin.exists():
            print("Building native Rust viewer (bb-viewer)...")
            subprocess.run(["cargo", "build", "--release", "--manifest-path", str(Path(__file__).parent / "bb_viewer" / "Cargo.toml")], check=True)

        temp_demake = Path(tempfile.gettempdir()) / f"{target_path.stem}_demake.glb"
        convert_container_to_glb(target_path, temp_demake)

        # Detect vanilla
        vanilla_arg = []
        if vanilla_path and vanilla_path.exists():
            temp_vanilla = Path(tempfile.gettempdir()) / f"{target_path.stem}_vanilla.glb"
            convert_container_to_glb(vanilla_path, temp_vanilla)
            vanilla_arg = ["--vanilla", str(temp_vanilla)]

        print(f"Launching native Rust viewer ({rust_bin.name})...")
        cmd = [str(rust_bin), str(temp_demake)] + vanilla_arg
        subprocess.run(cmd)
        return

    # Export GLB mode
    if args.export_glb:
        print(f"Exporting GLB from {target_path.name} -> {args.export_glb}...")
        convert_container_to_glb(target_path, args.export_glb)
        print(f"[SUCCESS] Exported GLB to {args.export_glb}")
        return

    # Blender direct launch mode
    if args.blender:
        temp_glb = Path(tempfile.gettempdir()) / f"{target_path.stem}.glb"
        convert_container_to_glb(target_path, temp_glb)
        print(f"Launching Blender with {temp_glb}...")
        subprocess.Popen(['blender', '--python-expr', f"import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=r'{temp_glb}')"])
        return

    # Headless snapshot mode
    if args.snapshot:
        temp_glb = Path(tempfile.gettempdir()) / f"{target_path.stem}.glb"
        convert_container_to_glb(target_path, temp_glb)
        render_blender_snapshot(
            temp_glb,
            Path(args.snapshot).resolve(),
            yaw=args.yaw,
            pitch=args.pitch,
            focus=args.focus
        )
        temp_glb.unlink(missing_ok=True)
        return

    # Interactive WebGL Viewer mode
    print("\n=============================================================")
    print(f">>> BLOODBORNE 3D MODEL DIAGNOSTIC VIEWER <<<")
    print(f"Target Model: {target_path.name} ({target_path})")
    print("=============================================================")

    print("Extracting FLVER geometry and deswizzling textures...")
    demake_glb = convert_container_to_glb(target_path)
    print(f"  [PSX Demake] Processed: {len(demake_glb):,} bytes")

    # Detect vanilla counterpart
    vanilla_glb = b''
    if vanilla_path and vanilla_path.exists():
        print(f"Auto-detected Vanilla Clean counterpart: {vanilla_path.name} ({vanilla_path})")
        try:
            vanilla_glb = convert_container_to_glb(vanilla_path)
            print(f"  [Vanilla Clean] Processed: {len(vanilla_glb):,} bytes")
        except Exception as e:
            print(f"  [Warning] Failed to process vanilla counterpart: {e}")

    # Set up server
    ModelViewerServer.demake_glb = demake_glb
    ModelViewerServer.vanilla_glb = vanilla_glb
    ModelViewerServer.model_name = target_path.name

    server_address = ('', args.port)
    try:
        httpd = HTTPServer(server_address, ModelViewerServer)
    except OSError:
        # Port busy, try next port
        server_address = ('', args.port + 1)
        httpd = HTTPServer(server_address, ModelViewerServer)

    url = f"http://localhost:{server_address[1]}"
    print(f"\n[SERVER READY] 3D Viewer running at: {url}")
    print("Controls:")
    print("  - Orbit / Pan / Zoom: Mouse Drag & Scroll")
    print("  - [Spacebar]: Instant Toggle between PSX Demake & Vanilla Clean")
    print("  - [W]: Toggle Wireframe Overlay")
    print("  - [F]: Toggle Flat Facet Retro Shading")
    print("  - [R]: Reset Camera View")
    print("\nPress Ctrl+C to terminate viewer.\n")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nViewer stopped.")
        httpd.server_close()

if __name__ == '__main__':
    main()
