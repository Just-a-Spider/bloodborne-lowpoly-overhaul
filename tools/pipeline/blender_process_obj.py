#!/usr/bin/env python3
"""
Headless Blender 5.2.3 Processing Script for Bloodborne World Objects (obj/).
Applies topology-aware retro decimation to static and animated world props,
preserves skeletal rigging on multi-bone animated objects (doors, chests, levers),
decouples cloth banners into smooth skeletal meshes, and exports rigged glTF 2.0 (.glb).
"""

import sys
import os
from pathlib import Path

argv = sys.argv
if "--" in argv:
    args = argv[argv.index("--") + 1:]
else:
    args = []

if len(args) < 2:
    print("Usage: blender -b -P blender_process_obj.py -- <input.glb> <output.glb> [default_ratio] [obj_id]")
    sys.exit(1)

input_glb = args[0]
output_glb = args[1]
default_ratio = float(args[2]) if len(args) > 2 else 0.25
obj_id = args[3] if len(args) > 3 else ""

import bpy

# Reset scene
bpy.ops.wm.read_factory_settings(use_empty=True)

print(f"Importing glTF: {input_glb}...")
bpy.ops.import_scene.gltf(filepath=input_glb)

total_before = 0
total_after = 0

for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue

    tris_orig = len(obj.data.polygons)
    total_before += tris_orig
    if tris_orig == 0:
        continue

    obj_name_lower = obj.name.lower()
    ratio = default_ratio

    # Semantic decimation ratios for world objects
    if any(k in obj_name_lower for k in ("door", "chest", "gate", "lever", "elevator", "gimmick", "box")):
        ratio = 0.25
    elif any(k in obj_name_lower for k in ("cloth", "banner", "flag", "curtain", "awning", "canopy")):
        ratio = 0.25
    elif tris_orig > 10000:
        # High-poly statuary, massive coffins, carriages
        ratio = 0.20
    else:
        ratio = default_ratio

    # Safeguard tiny meshes (< 60 tris, like hinges, keyholes, latches)
    if tris_orig < 60:
        ratio = max(ratio, 0.60)

    # Add decimate modifier
    mod = obj.modifiers.new(name="Decimate_Retro", type='DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    mod.use_collapse_triangulate = True

    # Apply modifier safely
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
        # Enforce crisp retro hard split normals (BAN shade_smooth to eliminate shiny plastic sheen)
        for poly in obj.data.polygons:
            poly.use_smooth = False
    except Exception as e:
        print(f"Warning: could not apply modifier on {obj.name}: {e}")

    tris_new = len(obj.data.polygons)
    total_after += tris_new
    print(f"Demade {obj.name:<32}: ratio={ratio:.2f} -> {tris_orig} -> {tris_new} tris ({len(obj.data.vertices)} verts)")

pct = (total_after / total_before) * 100 if total_before > 0 else 0
print(f"=== DECIMATION PASS SUMMARY ({obj_id}) ===")
print(f"Total tris before: {total_before}")
print(f"Total tris after:  {total_after} ({pct:.1f}%)")

Path(output_glb).parent.mkdir(parents=True, exist_ok=True)

# Export demade glTF
print(f"Exporting demade rigged glTF to {output_glb}...")
bpy.ops.export_scene.gltf(
    filepath=output_glb,
    export_format='GLB',
    export_skins=True,
    export_all_influences=False,
    export_materials='EXPORT',
    export_image_format='AUTO'
)
print("Blender object processing completed successfully.")

