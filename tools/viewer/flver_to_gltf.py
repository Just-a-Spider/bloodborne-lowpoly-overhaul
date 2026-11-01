"""
Bloodborne FLVER2 to glTF 2.0 (Binary .glb) Exporter.
Extracts FLVER submeshes, vertex positions, normals, UVs, and decoded/deswizzled TPF textures,
packaging them into a self-contained GLB file for WebGL Three.js or Blender inspection.
"""

import sys, os, struct, json, io
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import soulstruct_patch
from soulstruct.containers import Binder
from soulstruct.flver import FLVER
from ps4_swizzle import deswizzle_level
from demake_color_engine import get_mip_sizes, decode_bc1_to_rgba

try:
    import texture2ddecoder
except ImportError:
    texture2ddecoder = None

def extract_textures_from_tpf(tpf_bytes: bytes) -> dict[str, bytes]:
    """
    Extracts and decodes diffuse textures from a TPF archive into PNG byte buffers.
    Returns mapping: lower_base_name -> png_bytes.
    """
    tpf = bytearray(tpf_bytes)
    if tpf[:4] != b'TPF\x00':
        return {}

    tex_count = struct.unpack('<I', tpf[8:12])[0]
    textures = {}

    for i in range(tex_count):
        e = tpf[0x10 + i*36 : 0x10 + (i+1)*36]
        tex_off, tex_sz, unk1, unk2, unk3, unk4, str_off = struct.unpack('<7I', e[:28])

        curr = str_off
        while curr < len(tpf) - 1:
            if tpf[curr] == 0 and tpf[curr+1] == 0: break
            curr += 2
        name = tpf[str_off:curr].decode('utf-16le', errors='ignore')
        w = unk2 & 0xFFFF
        h = (unk2 >> 16) & 0xFFFF
        fmt = unk1 & 0xFF
        bpb = 16 if fmt in (0x66, 0x6c, 0x6d) else 8

        # Only decode diffuse albedos (_a) and normal maps (_n)
        low = name.lower()
        if not (low.endswith('_a') or low.endswith('_n')):
            continue

        mips = get_mip_sizes(w, h, bpb)
        if not mips:
            continue
        w0, h0, pw0, ph0, sz0 = mips[0]

        if tex_off + sz0 > len(tpf):
            continue

        linear0 = deswizzle_level(tpf[tex_off : tex_off + sz0], w0, h0, bpb)

        rgba0 = None
        if fmt == 0x66 and texture2ddecoder: # BC7
            bgra = np.frombuffer(texture2ddecoder.decode_bc7(bytes(linear0), pw0, ph0), dtype=np.uint8).reshape(ph0, pw0, 4)
            rgba0 = bgra[:h0, :w0, [2, 1, 0, 3]].copy()
        elif fmt in (0, 1): # BC1
            rgba0 = decode_bc1_to_rgba(linear0, pw0, ph0)[:h0, :w0]
        elif fmt in (0x6c, 0x6d) and texture2ddecoder: # BC5 (Normal map)
            bgra = np.frombuffer(texture2ddecoder.decode_bc5(bytes(linear0), pw0, ph0), dtype=np.uint8).reshape(ph0, pw0, 4)
            rgba0 = bgra[:h0, :w0, [2, 1, 0, 3]].copy()
            # If Z channel is flat, reconstruct Z = sqrt(1 - X^2 - Y^2)
            nx = rgba0[:, :, 0].astype(np.float32) / 255.0 * 2.0 - 1.0
            ny = rgba0[:, :, 1].astype(np.float32) / 255.0 * 2.0 - 1.0
            nz2 = np.clip(1.0 - nx**2 - ny**2, 0.0, 1.0)
            nz = np.sqrt(nz2)
            rgba0[:, :, 2] = np.clip((nz * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
            rgba0[:, :, 3] = 255

        if rgba0 is not None:
            im = Image.fromarray(rgba0)
            bio = io.BytesIO()
            im.save(bio, format='PNG')
            textures[low] = bio.getvalue()

    return textures

def flver_to_glb_bytes(flv: FLVER, textures: dict[str, bytes] = None, nearest_filter: bool = True) -> bytes:
    """
    Converts a Soulstruct FLVER object into a Binary glTF 2.0 (.glb) byte string.
    """
    if textures is None:
        textures = {}

    bin_chunks = []
    current_bin_offset = 0

    def add_binary_data(raw_bytes: bytes, alignment: int = 4) -> tuple[int, int]:
        nonlocal current_bin_offset
        # Pad to alignment
        pad_needed = (alignment - (current_bin_offset % alignment)) % alignment
        if pad_needed > 0:
            bin_chunks.append(b'\x00' * pad_needed)
            current_bin_offset += pad_needed
        offset = current_bin_offset
        bin_chunks.append(raw_bytes)
        current_bin_offset += len(raw_bytes)
        return offset, len(raw_bytes)

    gltf = {
        "asset": {"version": "2.0", "generator": "Bloodborne FLVER2 to GLTF 2.0 Exporter"},
        "scene": 0,
        "scenes": [{"name": "DefaultScene", "nodes": [0]}],
        "nodes": [{"name": "FLVER_Root", "children": []}],
        "meshes": [],
        "materials": [],
        "textures": [],
        "images": [],
        "samplers": [{
            "magFilter": 9728 if nearest_filter else 9729, # 9728 = NEAREST (retro), 9729 = LINEAR
            "minFilter": 9984 if nearest_filter else 9987, # 9984 = NEAREST_MIPMAP_NEAREST
            "wrapS": 10497, # REPEAT
            "wrapT": 10497  # REPEAT
        }],
        "accessors": [],
        "bufferViews": [],
        "buffers": []
    }

    # Map texture image name to glTF image/texture index
    tex_to_gltf_tex = {}
    for tex_name, png_data in textures.items():
        off, length = add_binary_data(png_data, alignment=4)
        bv_idx = len(gltf["bufferViews"])
        gltf["bufferViews"].append({
            "buffer": 0,
            "byteOffset": off,
            "byteLength": length
        })
        img_idx = len(gltf["images"])
        gltf["images"].append({
            "bufferView": bv_idx,
            "mimeType": "image/png",
            "name": tex_name
        })
        tex_idx = len(gltf["textures"])
        gltf["textures"].append({
            "sampler": 0,
            "source": img_idx,
            "name": tex_name
        })
        tex_to_gltf_tex[tex_name] = tex_idx

    # Process each FLVER submesh
    for mi, m in enumerate(flv.meshes):
        if not m.face_sets or len(m.vertex_arrays) == 0:
            continue

        faces = m.face_sets[0].vertex_indices.flatten()
        if len(faces) == 0:
            continue

        va0 = m.vertex_arrays[0]
        pos = va0.array['position'].astype(np.float32)
        norm = va0.array['normal'].astype(np.float32) if 'normal' in va0.array.dtype.names else None

        # Look for UV and Tangent in vertex arrays
        uv = None
        tan = None
        for va in m.vertex_arrays:
            for uv_name in ['uv_0', 'uv']:
                if uv is None and uv_name in va.array.dtype.names:
                    uv = va.array[uv_name].astype(np.float32)
            if tan is None and 'tangent_0' in va.array.dtype.names:
                tan = va.array['tangent_0'].astype(np.float32)
            if uv is not None and tan is not None:
                break

        # 1. Add Positions
        pos_bytes = pos.tobytes()
        pos_off, pos_len = add_binary_data(pos_bytes, alignment=4)
        pos_bv = len(gltf["bufferViews"])
        gltf["bufferViews"].append({
            "buffer": 0,
            "byteOffset": pos_off,
            "byteLength": pos_len,
            "target": 34962 # ARRAY_BUFFER
        })
        pos_acc = len(gltf["accessors"])
        gltf["accessors"].append({
            "bufferView": pos_bv,
            "byteOffset": 0,
            "componentType": 5126, # FLOAT
            "count": len(pos),
            "type": "VEC3",
            "min": pos.min(axis=0).tolist(),
            "max": pos.max(axis=0).tolist()
        })

        # 2. Add Normals
        norm_acc = None
        if norm is not None:
            norm_bytes = norm.tobytes()
            norm_off, norm_len = add_binary_data(norm_bytes, alignment=4)
            norm_bv = len(gltf["bufferViews"])
            gltf["bufferViews"].append({
                "buffer": 0,
                "byteOffset": norm_off,
                "byteLength": norm_len,
                "target": 34962
            })
            norm_acc = len(gltf["accessors"])
            gltf["accessors"].append({
                "bufferView": norm_bv,
                "byteOffset": 0,
                "componentType": 5126,
                "count": len(norm),
                "type": "VEC3",
                "min": norm.min(axis=0).tolist(),
                "max": norm.max(axis=0).tolist()
            })

        # 3. Add UVs
        uv_acc = None
        if uv is not None:
            uv_bytes = uv.tobytes()
            uv_off, uv_len = add_binary_data(uv_bytes, alignment=4)
            uv_bv = len(gltf["bufferViews"])
            gltf["bufferViews"].append({
                "buffer": 0,
                "byteOffset": uv_off,
                "byteLength": uv_len,
                "target": 34962
            })
            uv_acc = len(gltf["accessors"])
            gltf["accessors"].append({
                "bufferView": uv_bv,
                "byteOffset": 0,
                "componentType": 5126,
                "count": len(uv),
                "type": "VEC2",
                "min": uv.min(axis=0).tolist(),
                "max": uv.max(axis=0).tolist()
            })

        # 3b. Add Tangents
        tan_acc = None
        if tan is not None:
            tan_bytes = tan.tobytes()
            tan_off, tan_len = add_binary_data(tan_bytes, alignment=4)
            tan_bv = len(gltf["bufferViews"])
            gltf["bufferViews"].append({
                "buffer": 0,
                "byteOffset": tan_off,
                "byteLength": tan_len,
                "target": 34962
            })
            tan_acc = len(gltf["accessors"])
            gltf["accessors"].append({
                "bufferView": tan_bv,
                "byteOffset": 0,
                "componentType": 5126,
                "count": len(tan),
                "type": "VEC4",
                "min": tan.min(axis=0).tolist(),
                "max": tan.max(axis=0).tolist()
            })

        # 4. Add Indices
        # Use uint16 if max index < 65535, otherwise uint32
        max_idx = faces.max()
        idx_dtype = np.uint16 if max_idx < 65535 else np.uint32
        idx_comp_type = 5123 if max_idx < 65535 else 5125 # 5123=USHORT, 5125=UINT
        idx_arr = faces.astype(idx_dtype)
        idx_bytes = idx_arr.tobytes()
        idx_off, idx_len = add_binary_data(idx_bytes, alignment=4)
        idx_bv = len(gltf["bufferViews"])
        gltf["bufferViews"].append({
            "buffer": 0,
            "byteOffset": idx_off,
            "byteLength": idx_len,
            "target": 34963 # ELEMENT_ARRAY_BUFFER
        })
        idx_acc = len(gltf["accessors"])
        gltf["accessors"].append({
            "bufferView": idx_bv,
            "byteOffset": 0,
            "componentType": idx_comp_type,
            "count": len(faces),
            "type": "SCALAR",
            "min": [int(idx_arr.min())],
            "max": [int(idx_arr.max())]
        })

        # 5. Resolve Material, Diffuse & Normal Textures (FromSoft PBR Pipeline)
        mat_name = m.material.name if m.material else f"Submesh_{mi}"
        mtd_name = m.material.mat_def_name if m.material else ""
        is_cloth = 'cloth' in mat_name.lower() or '_cloth' in mtd_name.lower()

        diffuse_tex_idx = None
        normal_tex_idx = None
        if m.material:
            for tex in m.material.textures:
                tex_type = tex.texture_type
                base = Path(tex.path.replace('\\', '/')).stem.lower()
                if tex_type in ('g_DiffuseTexture', 'g_DiffuseMap') and diffuse_tex_idx is None:
                    if base in tex_to_gltf_tex:
                        diffuse_tex_idx = tex_to_gltf_tex[base]
                elif tex_type in ('g_BumpmapTexture', 'g_NormalMap') and normal_tex_idx is None:
                    if base in tex_to_gltf_tex:
                        normal_tex_idx = tex_to_gltf_tex[base]

        # If material doesn't explicitly link texture, match any texture with matching prefix
        if diffuse_tex_idx is None and tex_to_gltf_tex:
            diffuse_tex_idx = list(tex_to_gltf_tex.values())[0]

        # FromSoftware PBR Material Parameters
        low_mat = mat_name.lower()
        low_mtd = mtd_name.lower()
        if 'skin' in low_mat or 'skin' in low_mtd:
            metallic = 0.04
            roughness = 0.42 # smooth porcelain doll skin
        elif is_cloth:
            metallic = 0.02
            roughness = 0.88 # matte cloth
        elif 'hair' in low_mat or 'hr' in low_mat:
            metallic = 0.05
            roughness = 0.60 # hair specular sheen
        else:
            metallic = 0.06
            roughness = 0.72

        mat_dict = {
            "name": f"{mat_name} [{'CLOTH' if is_cloth else 'RIGID'}]",
            "pbrMetallicRoughness": {
                "metallicFactor": metallic,
                "roughnessFactor": roughness
            },
            "doubleSided": True
        }
        is_alpha_cutout = ('_e.' in low_mtd or '_e_' in low_mtd or '_al.' in low_mtd or 
                           any(k in low_mat or k in low_mtd for k in ['cutout', 'alpha', 'fur', 'hair', 'beard', 'foliage', 'feather']))
        if is_alpha_cutout:
            mat_dict["alphaMode"] = "MASK"
            mat_dict["alphaCutoff"] = 0.5

        if diffuse_tex_idx is not None:
            mat_dict["pbrMetallicRoughness"]["baseColorTexture"] = {"index": diffuse_tex_idx}
        if normal_tex_idx is not None:
            mat_dict["normalTexture"] = {"index": normal_tex_idx, "scale": 1.0}

        mat_idx = len(gltf["materials"])
        gltf["materials"].append(mat_dict)

        # 6. Create glTF Mesh & Primitive
        primitive = {
            "attributes": {"POSITION": pos_acc},
            "indices": idx_acc,
            "material": mat_idx
        }
        if norm_acc is not None:
            primitive["attributes"]["NORMAL"] = norm_acc
        if tan_acc is not None:
            primitive["attributes"]["TANGENT"] = tan_acc
        if uv_acc is not None:
            primitive["attributes"]["TEXCOORD_0"] = uv_acc

        mesh_idx = len(gltf["meshes"])
        gltf["meshes"].append({
            "name": f"Submesh_{mi}_{mat_name}",
            "primitives": [primitive]
        })

        node_idx = len(gltf["nodes"])
        gltf["nodes"].append({
            "name": f"Node_Submesh_{mi}",
            "mesh": mesh_idx
        })
        gltf["nodes"][0]["children"].append(node_idx)

    # Finalize buffer
    total_bin = b''.join(bin_chunks)
    # Pad total binary buffer to 4 bytes
    pad_total = (4 - (len(total_bin) % 4)) % 4
    if pad_total > 0:
        total_bin += b'\x00' * pad_total

    gltf["buffers"].append({"byteLength": len(total_bin)})

    # Serialize JSON chunk
    json_bytes = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
    json_pad = (4 - (len(json_bytes) % 4)) % 4
    if json_pad > 0:
        json_bytes += b' ' * json_pad

    # GLB Header (12 bytes)
    # 0x46546C67 = "glTF"
    # version = 2
    # length = 12 + 8 + len(json_bytes) + 8 + len(total_bin)
    glb_length = 12 + 8 + len(json_bytes) + 8 + len(total_bin)
    header = struct.pack('<4sII', b'glTF', 2, glb_length)

    # Chunk 0: JSON (0x4E4F534A = "JSON")
    chunk0_hdr = struct.pack('<I4s', len(json_bytes), b'JSON')

    # Chunk 1: BIN (0x004E4942 = "BIN\0")
    chunk1_hdr = struct.pack('<I4s', len(total_bin), b'BIN\x00')

    return header + chunk0_hdr + json_bytes + chunk1_hdr + total_bin

def convert_container_to_glb(filepath: str | Path, output_glb: str | Path = None, nearest_filter: bool = True) -> bytes:
    """
    Extracts FLVER and TPF from a .partsbnd.dcx, .chrbnd.dcx, or .flver.dcx file
    and returns or saves the GLB binary bytes.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    flver_obj = None
    all_textures = {}

    if filepath.name.endswith('.flver.dcx') or filepath.name.endswith('.flver'):
        flver_obj = FLVER.from_path(str(filepath))
        # Look for companion map BXF texture archives if inside a map folder
        import re
        map_match = re.search(r'm\d{2}', str(filepath))
        if map_match:
            map_id = map_match.group(0)
            map_dir = None
            for cand_dir in [
                filepath.parent.parent / map_id,
                Path("CUSA03173-PSX/dvdroot_ps4/map") / map_id,
                Path("CUSA03173/dvdroot_ps4/map") / map_id,
            ]:
                if cand_dir.exists():
                    map_dir = cand_dir
                    break
            if map_dir:
                needed = set()
                for m in flver_obj.meshes:
                    if m.material:
                        for t in m.material.textures:
                            clean = t.path.replace('\\', '/')
                            needed.add(Path(clean).stem.lower())
                for bhd_file in sorted(map_dir.glob("*.tpfbhd")):
                    if 'patch' in bhd_file.name:
                        continue
                    bdt_file = bhd_file.with_suffix(".tpfbdt")
                    if not bdt_file.exists():
                        continue
                    bhd_bytes = bhd_file.read_bytes()
                    bdt_bytes = bdt_file.read_bytes()
                    count = struct.unpack('<I', bhd_bytes[12:16])[0]
                    for i in range(count):
                        rec_off = 0x40 + i * 36
                        name_off = struct.unpack('<I', bhd_bytes[rec_off + 32 : rec_off + 36])[0]
                        name = bhd_bytes[name_off:].split(b'\x00\x00\x00')[0].decode('utf-16le', errors='ignore')
                        stem = name.split('.')[0].lower()
                        if stem in needed:
                            comp_sz = struct.unpack('<Q', bhd_bytes[rec_off + 8 : rec_off + 16])[0]
                            data_off = struct.unpack('<I', bhd_bytes[rec_off + 24 : rec_off + 28])[0]
                            from soulstruct.dcx import decompress
                            try:
                                tpf_raw, _ = decompress(bytes(bdt_bytes[data_off : data_off + comp_sz]))
                                all_textures.update(extract_textures_from_tpf(tpf_raw))
                            except Exception:
                                pass
    else:
        binder = Binder.from_path(str(filepath))
        for e in binder.entries:
            if e.name.endswith('.flver') and len(e.get_uncompressed_data()) > 1000:
                flver_obj = FLVER.from_bytes(e.get_uncompressed_data())
            elif e.name.endswith('.tpf'):
                tex_map = extract_textures_from_tpf(e.get_uncompressed_data())
                all_textures.update(tex_map)

        # Check for companion external TPF archives (e.g. c5000_2.tpf.dcx)
        stem = filepath.name.split('.')[0]
        parent = filepath.parent
        for cand_name in [f"{stem}_2.tpf.dcx", f"{stem}_1.tpf.dcx", f"{stem}.tpf.dcx"]:
            cand = parent / cand_name
            if cand.exists():
                from soulstruct.dcx import decompress
                try:
                    raw, _ = decompress(str(cand))
                    tex_map = extract_textures_from_tpf(raw)
                    all_textures.update(tex_map)
                except Exception:
                    pass

    if flver_obj is None:
        raise ValueError(f"No FLVER model found in {filepath.name}")

    glb_bytes = flver_to_glb_bytes(flver_obj, textures=all_textures, nearest_filter=nearest_filter)

    if output_glb:
        out_p = Path(output_glb)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_bytes(glb_bytes)

    return glb_bytes

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 flver_to_gltf.py <input.dcx> [output.glb]")
        sys.exit(1)

    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else Path(inp).stem + ".glb"
    convert_container_to_glb(inp, out)
    print(f"[SUCCESS] Exported {inp} -> {out} ({os.path.getsize(out):,} bytes)")
