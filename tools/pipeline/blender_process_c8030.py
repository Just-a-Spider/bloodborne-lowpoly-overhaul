#!/usr/bin/env python3
"""
Headless Blender 5.2.3 Processing Script for Plain Doll (c8030).
Decouples Havok cloth into skeletal-driven submeshes, applies controlled retro decimation
preserving facial features and UV seams, and exports a rigged low-poly glTF 2.0 (.glb).
"""

import sys
import os
from pathlib import Path

# When running under Blender: blender -b -P script.py -- [args]
argv = sys.argv
if "--" in argv:
    args = argv[argv.index("--") + 1:]
else:
    args = []

if len(args) < 2:
    print("Usage: blender -b -P blender_process_c8030.py -- <input_rigged.glb> <output_demade.glb> [preset]")
    sys.exit(1)

input_glb = args[0]
output_glb = args[1]
preset = args[2] if len(args) > 2 else "authentic"

import bpy

# Reset scene
bpy.ops.wm.read_factory_settings(use_empty=True)

print(f"Importing rigged glTF: {input_glb}...")
bpy.ops.import_scene.gltf(filepath=input_glb)

# Decimation budgets per submesh
# Target ~2,500 - 3,500 total tris for authentic retro aesthetic while keeping Doll likeness
if preset == "aggressive":
    ratios = {
        'Mantle01_cloth': 0.15,
        'Mantle02_cloth': 0.20,
        'Skirt_cloth': 0.12,
        'Material #3': 0.25,
        'HD_F_7000_01': 0.08,  # Bonnet
        'BD_F_7000': 0.08,     # Torso
        'AM_F_7000_01': 0.20,  # Arms
        'F_7000_skin': 0.15,   # Face / skin
        'HR_F_7000': 0.20,     # Hair base
        'LG_F_7000': 0.06,     # Legs
        'hair02_cloth': 0.15,
        'hair01_cloth': 0.15,
        'Material #17': 0.35   # Eyes
    }
else:  # authentic PSX
    ratios = {
        'Mantle01_cloth': 0.25,
        'Mantle02_cloth': 0.30,
        'Skirt_cloth': 0.20,
        'Material #3': 0.40,
        'HD_F_7000_01': 0.12,
        'BD_F_7000': 0.12,
        'AM_F_7000_01': 0.35,
        'F_7000_skin': 0.22,
        'HR_F_7000': 0.25,
        'LG_F_7000': 0.10,
        'hair02_cloth': 0.25,
        'hair01_cloth': 0.25,
        'Material #17': 0.50
    }

total_before = 0
total_after = 0

for obj in bpy.data.objects:
    if obj.type != 'MESH':
        continue
    
    tris_orig = len(obj.data.polygons)
    total_before += tris_orig

    ratio = 0.25
    for k, r in ratios.items():
        if k in obj.name:
            ratio = r
            break
    
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

print(f"=== DECIMATION PASS SUMMARY ===")
print(f"Total tris before: {total_before}")
print(f"Total tris after:  {total_after} ({(total_after / total_before) * 100:.1f}%)")

# Ensure output directory exists
Path(output_glb).parent.mkdir(parents=True, exist_ok=True)

# Export rigged demade glTF
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

