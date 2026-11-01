#!/usr/bin/env python3
"""
Bloodborne Rigged glTF to FLVER2 Compiler.
Compiles a demade, bone-weighted glTF 2.0 (.glb) back into native FromSoftware FLVER format.
Swaps Havok cloth materials to standard skinned materials, rebuilds split VA0/VA1 vertex arrays,
calculates Gram-Schmidt tangent frames, and recalculates AABB bounding boxes.
"""

import sys
import os
import json
import struct
from pathlib import Path
import numpy as np

TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

import soulstruct_patch
from soulstruct.containers import Binder
from soulstruct.flver.core import FLVER
from mesh_decimator import compute_angle_weighted_normals_and_tangents


def read_gltf_accessor(gltf: dict, bin_bytes: bytes, accessor_idx: int) -> np.ndarray:
    """Extracts typed numpy array from a glTF binary buffer accessor."""
    acc = gltf['accessors'][accessor_idx]
    bv = gltf['bufferViews'][acc['bufferView']]
    start = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
    count = acc['count']
    ctype = acc['componentType']
    atype = acc['type']

    type_map = {
        5120: np.int8,
        5121: np.uint8,
        5122: np.int16,
        5123: np.uint16,
        5125: np.uint32,
        5126: np.float32,
    }
    dim_map = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}

    np_dtype = type_map[ctype]
    dim = dim_map[atype]
    raw = bin_bytes[start : start + count * dim * np_dtype().itemsize]
    arr = np.frombuffer(raw, dtype=np_dtype).copy()
    return arr.reshape((count, dim)) if dim > 1 else arr


def decouple_cloth_mtd(mtd_name: str) -> str:
    """
    Translates any FromSoftware Havok cloth MTD into its exact skeletal-driven non-cloth equivalent.
    Completely eliminates SpClothVertexUpdate physics allocations in the game engine.
    """
    if "cloth" not in mtd_name.lower():
        return mtd_name

    res = mtd_name
    res = res.replace("[Cloth]", "")
    res = res.replace("_Tr_e_Cloth_PDEnhanced", "_e_PDEnhanced")
    res = res.replace("_Tr_e_Cloth", "_e")
    res = res.replace("_SSS_e_Cloth_PDEnhanced", "_SSS_PDEnhanced")
    res = res.replace("_e_Cloth_PDEnhanced", "_e_PDEnhanced")
    res = res.replace("_Cloth_PDEnhanced", "_PDEnhanced")
    res = res.replace("_em_Glow_e_Cloth", "_em_Glow_e")
    res = res.replace("_em_Glow_Cloth", "_em_Glow")
    res = res.replace("_SSS_e_Cloth", "_SSS_e")
    res = res.replace("_SSS_Cloth", "_SSS")
    res = res.replace("_Df_e_Cloth", "_Df_e")
    res = res.replace("_Df_Cloth", "_Df")
    res = res.replace("_e_Cloth", "_e")
    res = res.replace("_Cloth", "")
    res = res.replace("_cloth", "")
    return res


def compile_glb_to_flver(
    glb_path: str | Path,
    base_flver: FLVER,
    decouple_cloth: bool = True
) -> FLVER:
    """
    Compiles geometry, UVs, and bone weights from a rigged .glb into a target FLVER.
    Preserves original skeleton bones, materials, and metadata.
    """
    with open(glb_path, 'rb') as f:
        magic, ver, length = struct.unpack('<4sII', f.read(12))
        chunk0_len, _ = struct.unpack('<II', f.read(8))
        gltf = json.loads(f.read(chunk0_len).decode('utf-8'))
        chunk1_len, _ = struct.unpack('<II', f.read(8))
        bin_bytes = f.read(chunk1_len)

    gltf_meshes = gltf.get('meshes', [])
    if len(gltf_meshes) != len(base_flver.meshes):
        print(f"Warning: glTF has {len(gltf_meshes)} meshes, FLVER has {len(base_flver.meshes)}")

    # Build Blender Joint -> FLVER Global Bone Index Mapping
    # Blender's glTF exporter sorts joints alphabetically; we must resolve by node name
    skins = gltf.get('skins', [])
    skin = skins[0] if skins else {}
    skin_joints = skin.get('joints', [])
    nodes = gltf.get('nodes', [])

    bone_name_to_flver_idx = {bone.name: i for i, bone in enumerate(base_flver.bones)}
    blender_to_flver_bone = np.zeros(max(1, len(skin_joints)), dtype=np.int32)

    for j_idx, node_idx in enumerate(skin_joints):
        b_name = nodes[node_idx].get('name', '')
        if b_name in bone_name_to_flver_idx:
            blender_to_flver_bone[j_idx] = bone_name_to_flver_idx[b_name]
        else:
            blender_to_flver_bone[j_idx] = 0

    if len(skin_joints) > 0:
        print(f"Constructed Blender-to-FLVER bone remap LUT for {len(blender_to_flver_bone)} joints")

    for mi, m in enumerate(base_flver.meshes):
        if mi >= len(gltf_meshes):
            break

        gm = gltf_meshes[mi]
        p = gm['primitives'][0]

        pos = read_gltf_accessor(gltf, bin_bytes, p['attributes']['POSITION'])
        norm = (
            read_gltf_accessor(gltf, bin_bytes, p['attributes']['NORMAL'])
            if 'NORMAL' in p['attributes']
            else np.tile(np.array([0.0, 1.0, 0.0], dtype=np.float32), (len(pos), 1))
        )
        uv = (
            read_gltf_accessor(gltf, bin_bytes, p['attributes']['TEXCOORD_0'])
            if 'TEXCOORD_0' in p['attributes']
            else np.zeros((len(pos), 2), dtype=np.float32)
        )
        raw_joints = (
            read_gltf_accessor(gltf, bin_bytes, p['attributes']['JOINTS_0'])
            if 'JOINTS_0' in p['attributes']
            else np.zeros((len(pos), 4), dtype=np.int32)
        )
        weights = (
            read_gltf_accessor(gltf, bin_bytes, p['attributes']['WEIGHTS_0'])
            if 'WEIGHTS_0' in p['attributes']
            else np.zeros((len(pos), 4), dtype=np.float32)
        )
        if 'WEIGHTS_0' not in p['attributes']:
            weights[:, 0] = 1.0

        if 'indices' in p:
            faces = read_gltf_accessor(gltf, bin_bytes, p['indices']).reshape((-1, 3)).astype(np.uint32)
        else:
            faces = np.arange(len(pos), dtype=np.uint32).reshape((-1, 3))

        # Remap Blender alphabetical joint indices to FromSoft global bone indices
        remapped_joints = np.zeros_like(raw_joints, dtype=np.int32)
        if len(skin_joints) > 0:
            for slot in range(min(4, raw_joints.shape[1] if len(raw_joints.shape) > 1 else 1)):
                remapped_joints[:, slot] = blender_to_flver_bone[np.clip(raw_joints[:, slot], 0, len(blender_to_flver_bone) - 1)]

        # Zero out bone indices where influence weight is 0.0
        zero_mask = (weights < 1e-5)
        remapped_joints[zero_mask] = 0

        # Compute angle-weighted smooth normals and Gram-Schmidt tangent frames
        calc_norm, tan0, tan1 = compute_angle_weighted_normals_and_tangents(pos, uv, uv, faces)

        # Midline sagittal symmetry enforcement (only for skinned character rigs, NOT for world objects/doors)
        if len(skin_joints) > 0:
            midline_mask = np.abs(pos[:, 0]) < 0.0050
            if np.any(midline_mask):
                pos[midline_mask, 0] = 0.0
                calc_norm[midline_mask, 0] = 0.0
                n_len = np.linalg.norm(calc_norm[midline_mask], axis=1, keepdims=True)
                calc_norm[midline_mask] = np.where(
                    n_len > 1e-6, calc_norm[midline_mask] / np.maximum(n_len, 1e-6), np.array([[0.0, 0.0, -1.0]], dtype=np.float32)
                )
                tan0[midline_mask, 0] = 0.0
                t_len = np.linalg.norm(tan0[midline_mask, :3], axis=1, keepdims=True)
                tan0[midline_mask, :3] = np.where(
                    t_len > 1e-6, tan0[midline_mask, :3] / np.maximum(t_len, 1e-6), np.array([[0.0, -1.0, 0.0]], dtype=np.float32)
                )
                tan1[midline_mask] = tan0[midline_mask]

        num_v = len(pos)
        # FromSoftware character vertex color default is RGBA [1.0, 0.0, 1.0, 1.0] (G=0.0 subsurface mask)
        color_default = np.tile(np.array([1.0, 0.0, 1.0, 1.0], dtype=np.float32), (num_v, 1))

        attrs = {
            'position': pos,
            'normal': calc_norm,
            'uv_0': uv,
            'tangent_0': tan0,
            'tangent_1': tan1,
            'color_0': color_default,
        }
        if len(skin_joints) > 0:
            attrs['bone_indices'] = remapped_joints
            attrs['bone_weights'] = weights

        # Sync to FLVER dual vertex arrays (VA0/VA1)
        for va in m.vertex_arrays:
            new_arr = np.zeros(num_v, dtype=va.array.dtype)
            for fld in va.array.dtype.names:
                t_shape = new_arr[fld].shape
                if fld in attrs:
                    val = attrs[fld]
                    if val.shape != t_shape and val.size == int(np.prod(t_shape)):
                        val = val.reshape(t_shape)
                    new_arr[fld] = val
                elif fld.startswith('uv_'):
                    new_arr[fld] = attrs['uv_0'].reshape(t_shape)
                elif fld.startswith('tangent_'):
                    new_arr[fld] = attrs['tangent_0'].reshape(t_shape)
                elif fld.startswith('color_'):
                    new_arr[fld] = color_default.reshape(t_shape)
            va.array = new_arr

        # Update FaceSets (all LOD face sets synced to new faces)
        m.face_sets[0].vertex_indices = faces
        for fsi in range(1, len(m.face_sets)):
            m.face_sets[fsi].vertex_indices = faces.copy()

        # Decouple Havok cloth by swapping MTD to standard non-cloth shader
        if decouple_cloth and m.material.mat_def_name:
            new_mtd = decouple_cloth_mtd(m.material.mat_def_name)
            if new_mtd != m.material.mat_def_name:
                m.material.mat_def_name = new_mtd

    base_flver.refresh_bounding_boxes()
    return base_flver


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compile rigged glTF to Bloodborne FLVER")
    parser.add_argument("glb", help="Path to input .glb file")
    parser.add_argument("template_flver", help="Path to template FLVER or .chrbnd.dcx")
    parser.add_argument("output_flver", help="Path to output .flver file")
    parser.add_argument("--no-decouple-cloth", action="store_true", help="Keep original cloth MTDs")
    args = parser.parse_args()

    template_path = Path(args.template_flver)
    if template_path.name.endswith('.dcx'):
        b = Binder.from_path(template_path)
        flv_entry = next(e for e in b.entries if e.name.endswith('.flver'))
        base_flver = FLVER.from_bytes(flv_entry.data)
    else:
        base_flver = FLVER.from_path(template_path)

    compiled_flver = compile_glb_to_flver(args.glb, base_flver, decouple_cloth=not args.no_decouple_cloth)
    out_path = Path(args.output_flver)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_bytes = compiled_flver.to_bytes()
    out_path.write_bytes(out_bytes)
    print(f"Successfully compiled {len(out_bytes)} bytes to {out_path}")


if __name__ == "__main__":
    main()

