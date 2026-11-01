#!/usr/bin/env python3
"""
Bloodborne FLVER2 Rigged glTF 2.0 Exporter.
Extracts FLVER submeshes, complete skeleton bone hierarchies, vertex skinning
weights (JOINTS_0, WEIGHTS_0), and decoded TPF textures into a rigged Binary glTF (.glb).

Supports direct import into Blender 5.2.3 LTS with full Armature and Vertex Groups.
"""

import sys
import os
import struct
import json
import io
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

# Allow importing local tools
TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(TOOLS_DIR / "viewer"))

import soulstruct_patch
from soulstruct.containers import Binder
from soulstruct.flver.core import FLVER
from ps4_swizzle import deswizzle_level
from demake_color_engine import get_mip_sizes, decode_bc1_to_rgba

try:
    import texture2ddecoder
except ImportError:
    texture2ddecoder = None


def extract_textures_from_tpf(tpf_bytes: bytes) -> dict[str, bytes]:
    """Extracts and decodes diffuse (_a) textures from a TPF archive into PNG byte buffers."""
    tpf = bytearray(tpf_bytes)
    if tpf[:4] != b'TPF\x00':
        return {}

    tex_count = struct.unpack('<I', tpf[8:12])[0]
    textures = {}

    for i in range(tex_count):
        e = tpf[0x10 + i * 36 : 0x10 + (i + 1) * 36]
        tex_off, tex_sz, unk1, unk2, unk3, unk4, str_off = struct.unpack('<7I', e[:28])

        curr = str_off
        while curr < len(tpf) - 1:
            if tpf[curr] == 0 and tpf[curr + 1] == 0:
                break
            curr += 2
        name = tpf[str_off:curr].decode('utf-16le', errors='ignore')
        w = unk2 & 0xFFFF
        h = (unk2 >> 16) & 0xFFFF
        fmt = unk1 & 0xFF
        bpb = 16 if fmt in (0x66, 0x6C, 0x6D) else 8

        low = name.lower()
        if not low.endswith('_a'):
            continue

        mips = get_mip_sizes(w, h, bpb)
        if not mips:
            continue
        w0, h0, pw0, ph0, sz0 = mips[0]
        if tex_off + sz0 > len(tpf):
            continue

        linear0 = deswizzle_level(tpf[tex_off : tex_off + sz0], w0, h0, bpb)

        rgba0 = None
        if fmt == 0x66 and texture2ddecoder:  # BC7
            bgra = np.frombuffer(texture2ddecoder.decode_bc7(bytes(linear0), pw0, ph0), dtype=np.uint8).reshape(ph0, pw0, 4)
            rgba0 = bgra[:h0, :w0, [2, 1, 0, 3]].copy()
        elif fmt in (0, 1):  # BC1
            rgba0 = decode_bc1_to_rgba(linear0, pw0, ph0)[:h0, :w0]

        if rgba0 is not None:
            im = Image.fromarray(rgba0)
            bio = io.BytesIO()
            im.save(bio, format='PNG')
            textures[low] = bio.getvalue()

    return textures


def euler_to_matrix_and_quat(euler_rad, scale=(1.0, 1.0, 1.0), translate=(0.0, 0.0, 0.0)):
    """
    Converts FromSoft XZY EulerRad, scale, and translate to a 4x4 matrix and glTF quaternion [x, y, z, w].
    FromSoft applies Euler angles in XZY (pitch, roll, yaw) order:
    angles = [pitch (x), roll (z), yaw (y)]
    """
    # angles in XZY order: X (pitch), Z (roll), Y (yaw)
    angles = [float(euler_rad.x), float(euler_rad.z), float(euler_rad.y)]
    rot = Rotation.from_euler('xzy', angles)
    r_mat = rot.as_matrix()
    quat = rot.as_quat()  # [x, y, z, w]

    # Normalize quat to avoid numerical drift
    q_norm = np.linalg.norm(quat)
    if q_norm > 1e-6:
        quat = quat / q_norm
    else:
        quat = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)

    # 4x4 affine matrix
    m = np.eye(4, dtype=np.float32)
    s = np.array(scale, dtype=np.float32)
    m[:3, :3] = r_mat * s
    m[:3, 3] = np.array(translate, dtype=np.float32)

    return m, quat.tolist()


def flver_to_rigged_glb(flv: FLVER, textures: dict[str, bytes] = None) -> bytes:
    """Converts a Soulstruct FLVER model into a fully rigged Binary glTF 2.0 (.glb) with skeleton skinning."""
    if textures is None:
        textures = {}

    bin_chunks = []
    current_bin_offset = 0

    def add_binary_data(raw_bytes: bytes, alignment: int = 4) -> tuple[int, int]:
        nonlocal current_bin_offset
        pad_needed = (alignment - (current_bin_offset % alignment)) % alignment
        if pad_needed > 0:
            bin_chunks.append(b'\x00' * pad_needed)
            current_bin_offset += pad_needed
        offset = current_bin_offset
        bin_chunks.append(raw_bytes)
        current_bin_offset += len(raw_bytes)
        return offset, len(raw_bytes)

    num_bones = len(flv.bones)

    # Check whether model contains actual vertex skinning weights
    has_skin = any(
        any(fld in va.array.dtype.names for fld in ("bone_indices", "bone_weights"))
        for m in flv.meshes
        for va in m.vertex_arrays
    )

    if has_skin and num_bones > 0:
        # 1. Compute bone local and world transform matrices
        local_matrices = []
        quats = []
        for b in flv.bones:
            m_loc, q = euler_to_matrix_and_quat(b.rotate, scale=b.scale, translate=b.translate)
            local_matrices.append(m_loc)
            quats.append(q)

        # Compute world matrices by walking the parent chain
        world_matrices = [None] * num_bones

        def get_world_matrix(bone_idx: int) -> np.ndarray:
            if world_matrices[bone_idx] is not None:
                return world_matrices[bone_idx]
            b = flv.bones[bone_idx]
            m_loc = local_matrices[bone_idx]
            if b.parent_bone_index == -1:
                m_w = m_loc.copy()
            else:
                m_parent = get_world_matrix(b.parent_bone_index)
                m_w = m_parent @ m_loc
            world_matrices[bone_idx] = m_w
            return m_w

        for i in range(num_bones):
            get_world_matrix(i)

        # Compute Inverse Bind Matrices (IBM)
        inv_bind_matrices = []
        for i in range(num_bones):
            try:
                ibm = np.linalg.inv(world_matrices[i])
            except np.linalg.LinAlgError:
                ibm = np.eye(4, dtype=np.float32)
            # Column-major for glTF MAT4
            inv_bind_matrices.append(ibm.T.flatten().astype(np.float32))

        ibm_array = np.concatenate(inv_bind_matrices)
        ibm_offset, ibm_len = add_binary_data(ibm_array.tobytes(), alignment=4)

        # 2. Build bone child relationships
        bone_children = [[] for _ in range(num_bones)]
        root_bones = []
        for i, b in enumerate(flv.bones):
            if b.parent_bone_index == -1:
                root_bones.append(i)
            elif 0 <= b.parent_bone_index < num_bones:
                bone_children[b.parent_bone_index].append(i)

        # glTF Nodes:
        # Node 0: Root "Armature"
        # Nodes 1..num_bones: Bone nodes (offset by +1)
        # Nodes num_bones+1..: Mesh nodes
        bone_node_offset = 1
        nodes = []

        # Node 0: Armature root
        nodes.append({
            "name": "Armature",
            "children": [r + bone_node_offset for r in root_bones]
        })

        # Bone nodes
        for i, b in enumerate(flv.bones):
            bone_node = {
                "name": b.name,
                "translation": [float(b.translate.x), float(b.translate.y), float(b.translate.z)],
                "rotation": quats[i],
                "scale": [float(b.scale.x), float(b.scale.y), float(b.scale.z)]
            }
            if bone_children[i]:
                bone_node["children"] = [c + bone_node_offset for c in bone_children[i]]
            nodes.append(bone_node)
    else:
        # Pure unskinned rigid / static objects (doors, levers, chests, elevators):
        # Vertices are in bone-local coordinates; NO Armature or IBM to prevent coordinate distortion
        nodes = []
        ibm_offset, ibm_len = 0, 0

    # 3. Textures and Materials
    gltf_textures = []
    gltf_images = []
    gltf_buffer_views = []
    gltf_accessors = []
    tex_to_gltf_idx = {}

    for tex_name, png_data in textures.items():
        off, length = add_binary_data(png_data, alignment=4)
        bv_idx = len(gltf_buffer_views)
        gltf_buffer_views.append({
            "buffer": 0,
            "byteOffset": off,
            "byteLength": length
        })
        img_idx = len(gltf_images)
        gltf_images.append({
            "bufferView": bv_idx,
            "mimeType": "image/png",
            "name": tex_name
        })
        tex_idx = len(gltf_textures)
        gltf_textures.append({
            "sampler": 0,
            "source": img_idx,
            "name": tex_name
        })
        tex_to_gltf_idx[tex_name] = tex_idx

    # Pack IBM accessor and skin
    if has_skin and num_bones > 0:
        ibm_bv_idx = len(gltf_buffer_views)
        gltf_buffer_views.append({
            "buffer": 0,
            "byteOffset": ibm_offset,
            "byteLength": ibm_len
        })
        ibm_accessor_idx = len(gltf_accessors)
        gltf_accessors.append({
            "bufferView": ibm_bv_idx,
            "componentType": 5126,  # FLOAT
            "count": num_bones,
            "type": "MAT4"
        })

        # Skin definition
        joint_node_indices = list(range(bone_node_offset, bone_node_offset + num_bones))
        skins = [{
            "name": "ArmatureSkin",
            "inverseBindMatrices": ibm_accessor_idx,
            "joints": joint_node_indices
        }]
    else:
        skins = []

    # 4. Meshes & Primitives
    gltf_meshes = []
    gltf_materials = []

    for mi, m in enumerate(flv.meshes):
        if not m.face_sets or len(m.vertex_arrays) == 0:
            continue

        faces = m.face_sets[0].vertex_indices.flatten().astype(np.uint32)
        if len(faces) == 0:
            continue

        # Extract vertex attributes across arrays
        attrs = {}
        for va in m.vertex_arrays:
            for name in va.array.dtype.names:
                if name not in attrs:
                    attrs[name] = va.array[name]

        pos = attrs.get('position')
        if pos is None:
            continue
        pos = pos.astype(np.float32)
        num_v = len(pos)

        norm = attrs.get('normal')
        if norm is not None:
            norm = norm.astype(np.float32)
            # Normalize normals
            norm_len = np.linalg.norm(norm, axis=1, keepdims=True)
            norm_len[norm_len < 1e-6] = 1.0
            norm = (norm / norm_len).astype(np.float32)
        else:
            norm = np.zeros((num_v, 3), dtype=np.float32)
            norm[:, 1] = 1.0

        uv = None
        for uv_name in ['uv_0', 'uv']:
            if uv_name in attrs:
                uv = attrs[uv_name].astype(np.float32)
                break
        if uv is None:
            uv = np.zeros((num_v, 2), dtype=np.float32)

        # Bone indices and weights (only for models with skeletal skinning)
        if has_skin and num_bones > 0:
            b_idx = attrs.get('bone_indices')
            b_wt = attrs.get('bone_weights')

            if b_idx is not None and b_wt is not None:
                joints = b_idx.astype(np.uint16)
                weights = b_wt.astype(np.float32)
                # Normalize weights to sum to 1.0
                wt_sum = weights.sum(axis=1, keepdims=True)
                wt_zero_mask = (wt_sum < 1e-6).flatten()
                wt_sum[wt_sum < 1e-6] = 1.0
                weights = weights / wt_sum
                # For unweighted vertices, bind to default_bone_index
                def_bone = max(0, min(m.default_bone_index, num_bones - 1))
                joints[wt_zero_mask, 0] = def_bone
                weights[wt_zero_mask, 0] = 1.0
            else:
                def_bone = max(0, min(m.default_bone_index, num_bones - 1))
                joints = np.zeros((num_v, 4), dtype=np.uint16)
                joints[:, 0] = def_bone
                weights = np.zeros((num_v, 4), dtype=np.float32)
                weights[:, 0] = 1.0

        # Pack Position
        pos_off, pos_len = add_binary_data(pos.tobytes(), alignment=4)
        pos_bv_idx = len(gltf_buffer_views)
        gltf_buffer_views.append({"buffer": 0, "byteOffset": pos_off, "byteLength": pos_len})
        pos_acc_idx = len(gltf_accessors)
        gltf_accessors.append({
            "bufferView": pos_bv_idx,
            "componentType": 5126,  # FLOAT
            "count": num_v,
            "type": "VEC3",
            "max": pos.max(axis=0).tolist(),
            "min": pos.min(axis=0).tolist()
        })

        # Pack Normal
        norm_off, norm_len = add_binary_data(norm.tobytes(), alignment=4)
        norm_bv_idx = len(gltf_buffer_views)
        gltf_buffer_views.append({"buffer": 0, "byteOffset": norm_off, "byteLength": norm_len})
        norm_acc_idx = len(gltf_accessors)
        gltf_accessors.append({
            "bufferView": norm_bv_idx,
            "componentType": 5126,
            "count": num_v,
            "type": "VEC3"
        })

        # Pack UV
        uv_off, uv_len = add_binary_data(uv.tobytes(), alignment=4)
        uv_bv_idx = len(gltf_buffer_views)
        gltf_buffer_views.append({"buffer": 0, "byteOffset": uv_off, "byteLength": uv_len})
        uv_acc_idx = len(gltf_accessors)
        gltf_accessors.append({
            "bufferView": uv_bv_idx,
            "componentType": 5126,
            "count": num_v,
            "type": "VEC2"
        })

        prim_attrs = {
            "POSITION": pos_acc_idx,
            "NORMAL": norm_acc_idx,
            "TEXCOORD_0": uv_acc_idx,
        }

        if has_skin and num_bones > 0:
            # Pack JOINTS_0 (uint16)
            joints_off, joints_len = add_binary_data(joints.tobytes(), alignment=4)
            joints_bv_idx = len(gltf_buffer_views)
            gltf_buffer_views.append({"buffer": 0, "byteOffset": joints_off, "byteLength": joints_len})
            joints_acc_idx = len(gltf_accessors)
            gltf_accessors.append({
                "bufferView": joints_bv_idx,
                "componentType": 5123,  # UNSIGNED_SHORT
                "count": num_v,
                "type": "VEC4"
            })

            # Pack WEIGHTS_0 (float)
            weights_off, weights_len = add_binary_data(weights.tobytes(), alignment=4)
            weights_bv_idx = len(gltf_buffer_views)
            gltf_buffer_views.append({"buffer": 0, "byteOffset": weights_off, "byteLength": weights_len})
            weights_acc_idx = len(gltf_accessors)
            gltf_accessors.append({
                "bufferView": weights_bv_idx,
                "componentType": 5126,  # FLOAT
                "count": num_v,
                "type": "VEC4"
            })

            prim_attrs["JOINTS_0"] = joints_acc_idx
            prim_attrs["WEIGHTS_0"] = weights_acc_idx

        # Pack Indices (Faces)
        faces_off, faces_len = add_binary_data(faces.tobytes(), alignment=4)
        faces_bv_idx = len(gltf_buffer_views)
        gltf_buffer_views.append({"buffer": 0, "byteOffset": faces_off, "byteLength": faces_len})
        faces_acc_idx = len(gltf_accessors)
        gltf_accessors.append({
            "bufferView": faces_bv_idx,
            "componentType": 5125,  # UNSIGNED_INT
            "count": len(faces),
            "type": "SCALAR"
        })

        # Material setup
        mat_name = m.material.name if m.material else f"Material_{mi}"
        mat_idx = len(gltf_materials)
        mat_dict = {
            "name": mat_name,
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.8
            },
            "doubleSided": True
        }

        # Match diffuse texture if available
        matched_tex = None
        for t_name, t_idx in tex_to_gltf_idx.items():
            if mat_name.lower() in t_name or any(part in t_name for part in mat_name.lower().split('_')):
                matched_tex = t_idx
                break
        if matched_tex is None and gltf_textures:
            matched_tex = 0

        if matched_tex is not None:
            mat_dict["pbrMetallicRoughness"]["baseColorTexture"] = {"index": matched_tex}

        gltf_materials.append(mat_dict)

        # glTF Primitive & Mesh
        mesh_idx = len(gltf_meshes)
        gltf_meshes.append({
            "name": f"Mesh_{mi}_{mat_name}",
            "primitives": [{
                "attributes": prim_attrs,
                "indices": faces_acc_idx,
                "material": mat_idx
            }]
        })

        # Mesh Node
        mesh_node_idx = len(nodes)
        mesh_node = {
            "name": f"Node_Mesh_{mi}_{mat_name}",
            "mesh": mesh_idx,
        }
        if has_skin and skins:
            mesh_node["skin"] = 0
            nodes.append(mesh_node)
            nodes[0]["children"].append(mesh_node_idx)
        else:
            nodes.append(mesh_node)

    # Assemble glTF JSON structure
    scene_nodes = [0] if (has_skin and skins) else list(range(len(nodes)))
    gltf = {
        "asset": {"version": "2.0", "generator": "Bloodborne FLVER2 Rigged glTF Exporter"},
        "scene": 0,
        "scenes": [{"name": "DefaultScene", "nodes": scene_nodes}],
        "nodes": nodes,
        "skins": skins,
        "meshes": gltf_meshes,
        "materials": gltf_materials,
        "textures": gltf_textures,
        "images": gltf_images,
        "samplers": [{
            "magFilter": 9729,  # LINEAR
            "minFilter": 9987,  # LINEAR_MIPMAP_LINEAR
            "wrapS": 10497,     # REPEAT
            "wrapT": 10497
        }],
        "accessors": gltf_accessors,
        "bufferViews": gltf_buffer_views,
        "buffers": [{"byteLength": current_bin_offset}]
    }

    # Encode JSON Chunk
    json_bytes = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
    json_pad = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b' ' * json_pad

    # Combine Binary Chunks
    bin_data = b''.join(bin_chunks)
    bin_pad = (4 - (len(bin_data) % 4)) % 4
    bin_data += b'\x00' * bin_pad

    # Assemble GLB Header
    total_len = 12 + 8 + len(json_bytes) + 8 + len(bin_data)
    header = struct.pack('<4sII', b'glTF', 2, total_len)
    chunk0 = struct.pack('<II', len(json_bytes), 0x4E4F534A) + json_bytes
    chunk1 = struct.pack('<II', len(bin_data), 0x004E4942) + bin_data

    return header + chunk0 + chunk1


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export Bloodborne FLVER to Rigged glTF 2.0 (.glb)")
    parser.add_argument("chrbnd", help="Path to character .chrbnd.dcx archive")
    parser.add_argument("output", help="Path to output .glb file")
    args = parser.parse_args()

    chrbnd_path = Path(args.chrbnd)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading {chrbnd_path}...")
    binder = Binder.from_path(chrbnd_path)

    flv_entry = None
    tpf_entry = None
    for e in binder.entries:
        if e.name.lower().endswith('.flver'):
            flv_entry = e
        elif e.name.lower().endswith('.tpf'):
            tpf_entry = e

    if not flv_entry:
        print("Error: No .flver found in binder!")
        sys.exit(1)

    flv = FLVER.from_bytes(flv_entry.data)
    print(f"Loaded FLVER: {len(flv.bones)} bones, {len(flv.meshes)} meshes")

    textures = {}
    if tpf_entry:
        print(f"Decoding textures from {tpf_entry.name}...")
        textures = extract_textures_from_tpf(tpf_entry.data)
        print(f"Decoded {len(textures)} diffuse textures")

    print(f"Compiling rigged glTF 2.0...")
    glb_data = flver_to_rigged_glb(flv, textures)
    out_path.write_bytes(glb_data)
    print(f"Successfully wrote {len(glb_data)} bytes to {out_path}")


if __name__ == "__main__":
    main()
