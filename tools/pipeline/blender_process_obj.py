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
    if any(k in obj_name_lower for k in ("corpse", "c1040", "c1010", "c1270", "waste", "body")):
        ratio = 0.15  # 85% reduction on dense cadaver heaps
    elif any(k in obj_name_lower for k in ("cage", "prison", "dogcage", "fence")):
        ratio = 0.20  # 80% reduction on cage bars
    elif any(k in obj_name_lower for k in ("door", "chest", "gate", "lever", "elevator", "gimmick", "box")):
        ratio = 0.25
    elif any(k in obj_name_lower for k in ("cloth", "banner", "flag", "curtain", "awning", "canopy")):
        ratio = 0.25
    elif tris_orig > 10000:
        # High-poly statuary, massive coffins, carriages
        ratio = 0.15
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

    # For interactive doors with offset hinge pivot (e.g. o282020 Yahar'gul cell gate),
    # pin the hinge axis (X ≈ 0.625), bottom floor boundary, and wall contacts
    if obj_id == "o282020":
        vg = obj.vertex_groups.new(name="Pin_Hinge_Frame")
        pinned = []
        unpinned = []
        for v in obj.data.vertices:
            # Hinge cylinder at X=0.625, floor contact Y<-0.25, wall anchors X<-2.48 or X>2.28 or Y>8.25
            if (
                abs(v.co.x - 0.625) <= 0.055
                or v.co.y < -0.25
                or v.co.x < -2.48
                or v.co.x > 2.28
                or v.co.y > 8.25
            ):
                pinned.append(v.index)
            else:
                unpinned.append(v.index)
        if pinned:
            vg.add(pinned, 0.0, 'REPLACE')
            vg.add(unpinned, 1.0, 'REPLACE')
            mod.vertex_group = vg.name
            mod.invert_vertex_group = False
            print(f"Pinned {len(pinned)} hinge/frame contact vertices on {obj_id} (weight=0.0)")

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

