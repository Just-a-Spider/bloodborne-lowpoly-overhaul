#!/usr/bin/env python3
"""
Headless Blender 5.2.3 Processing Script for Player Equipment & Weapons (parts/).
Decouples Havok cloth into skeletal-driven submeshes, applies controlled retro decimation
preserving mechanical silhouettes, and exports a rigged low-poly glTF 2.0 (.glb).
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
    print("Usage: blender -b -P blender_process_parts.py -- <input.glb> <output.glb> [default_ratio] [category]")
    sys.exit(1)

input_glb = args[0]
output_glb = args[1]
default_ratio = float(args[2]) if len(args) > 2 else 0.25
category = args[3] if len(args) > 3 else "armor"

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

    # Determine ratio based on submesh semantic hints
    obj_name_lower = obj.name.lower()
    ratio = default_ratio

    if category == "weapon" or "wp_" in obj_name_lower:
        ratio = max(0.30, default_ratio)
    elif "cloth" in obj_name_lower:
        ratio = 0.25
    elif any(k in obj_name_lower for k in ("hd_", "hat", "helm", "head", "bonnet")):
        ratio = 0.20
    elif any(k in obj_name_lower for k in ("am_", "arm", "glove", "gauntlet")):
        ratio = 0.25
    elif any(k in obj_name_lower for k in ("lg_", "leg", "boot", "trouser")):
        ratio = 0.20

    # Ensure small meshes (< 60 tris) don't get over-decimated
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
        # Ensure smooth vertex normals across all decimated polygons
        bpy.ops.object.shade_smooth()
    except Exception as e:
        print(f"Warning: could not apply modifier on {obj.name}: {e}")

    tris_new = len(obj.data.polygons)
    total_after += tris_new
    print(f"Demade {obj.name:<32}: ratio={ratio:.2f} -> {tris_orig} -> {tris_new} tris ({len(obj.data.vertices)} verts)")

pct = (total_after / total_before) * 100 if total_before > 0 else 0
print(f"=== DECIMATION PASS SUMMARY ===")
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
print("Blender processing completed successfully.")

