"""
Runtime monkeypatch for Soulstruct FLVERBone deserialization.
Fixes silent dropping of bone bounding boxes in Bloodborne FLVER2 files.
"""

from soulstruct.flver.bone import FLVERBone
from soulstruct.utilities.binary import BinaryReader
from soulstruct.utilities.maths.aabb import AABB

_orig_from_flver_reader = FLVERBone.from_flver_reader

def patched_from_flver_reader(cls, reader: BinaryReader, encoding: str) -> FLVERBone:
    bone_struct = cls.STRUCT.from_bytes(reader)
    name = reader.unpack_string(offset=bone_struct.pop("_name_offset"), encoding=encoding)
    bb = AABB(bone_struct.bounding_box_min, bone_struct.bounding_box_max)
    flver_bone = bone_struct.to_object(cls, name=name, bounding_box=bb)
    return flver_bone

def apply_soulstruct_patches():
    FLVERBone.from_flver_reader = classmethod(patched_from_flver_reader)

    # Patch FLVER.refresh_bounding_boxes with bone-hierarchy-aware model space bounds
    from soulstruct.flver.core import FLVER
    from soulstruct.utilities.maths import Vector3
    from scipy.spatial.transform import Rotation
    import numpy as np

    def compute_bone_world_matrices(bones):
        num_bones = len(bones)
        world_matrices = [None] * num_bones

        def get_world(bi):
            if bi < 0 or bi >= num_bones:
                return np.eye(4, dtype=np.float32)
            if world_matrices[bi] is not None:
                return world_matrices[bi]
            b = bones[bi]
            r = Rotation.from_euler('xzy', [b.rotate.x, b.rotate.z, b.rotate.y], degrees=False).as_matrix()
            s = np.array([b.scale.x, b.scale.y, b.scale.z], dtype=np.float32)
            m_loc = np.eye(4, dtype=np.float32)
            m_loc[:3, :3] = r * s
            m_loc[:3, 3] = np.array([b.translate.x, b.translate.y, b.translate.z], dtype=np.float32)

            if b.parent_bone_index == -1:
                m_w = m_loc
            else:
                m_w = get_world(b.parent_bone_index) @ m_loc
            world_matrices[bi] = m_w
            return m_w

        for i in range(num_bones):
            get_world(i)
        return world_matrices

    def patched_refresh_bounding_boxes(self):
        w_mats = compute_bone_world_matrices(self.bones) if self.bones else []
        mesh_mins = []
        mesh_maxs = []
        for mesh in self.meshes:
            if not mesh.face_sets or len(mesh.vertex_arrays) == 0:
                continue
            pos = None
            has_skin = False
            for va in mesh.vertex_arrays:
                if 'position' in va.array.dtype.names and pos is None:
                    pos = va.array['position']
                if 'bone_indices' in va.array.dtype.names:
                    has_skin = True

            if pos is not None and len(pos) > 0:
                # If mesh has vertex bone weights, positions are already in model/bind space.
                # If unskinned, transform positions by default_bone_index world matrix.
                if has_skin or not w_mats:
                    pos_w = pos
                else:
                    bi = mesh.default_bone_index
                    M = w_mats[bi] if (0 <= bi < len(w_mats)) else np.eye(4, dtype=np.float32)
                    pos_w = pos @ M[:3, :3].T + M[:3, 3]

                m_min = pos_w.min(axis=0)
                m_max = pos_w.max(axis=0)
                if mesh.uses_bounding_boxes:
                    mesh.bounding_box = AABB(Vector3(m_min), Vector3(m_max))
                mesh_mins.append(m_min)
                mesh_maxs.append(m_max)

        if mesh_mins:
            self.bounding_box = AABB(
                Vector3(np.min(mesh_mins, axis=0)),
                Vector3(np.max(mesh_maxs, axis=0))
            )

    FLVER.refresh_bounding_boxes = patched_refresh_bounding_boxes
    
    # Patch Binder._entries_into_writer_v4 for BXF4 (split BHD/BDT)
    from soulstruct.containers.core import Binder, BinderHashTable
    
    def patched_entries_into_writer_v4(self, header_writer, entry_writer, rebuild_hash_table=False):
        sorted_entries = list(sorted(self.entries, key=lambda e: e.entry_id))
        sorted_entry_headers = [entry.get_header(self.flags) for entry in sorted_entries]
        for entry_header in sorted_entry_headers:
            entry_header.into_bnd4_writer(header_writer, self.flags, self.bit_big_endian)

        if self.flags.has_names:
            path_encoding = entry_writer.get_utf_16_encoding() if self.v4_info.unicode else self.ENTRY_PATH_ENCODING
            for entry, entry_header in zip(sorted_entries, sorted_entry_headers):
                entry_header.pack_path(header_writer, entry.get_packed_path(encoding=path_encoding))

        if self.v4_info.hash_table_type == 4:
            header_writer.fill_with_position("_hash_table_offset", obj=self)
            if rebuild_hash_table:
                header_writer.append(BinderHashTable.build_hash_table(self.entries))
            else:
                header_writer.append(self.v4_info.most_recent_hash_table)
        else:
            header_writer.fill("_hash_table_offset", 0, obj=self)

        # In split BXF4 (BHF4 header), _data_offset must be 0 because BDT contains all data.
        data_off = 0 if self.is_split_bxf else entry_writer.position
        header_writer.fill("_data_offset", data_off, obj=self)

        for entry, entry_header in zip(sorted_entries, sorted_entry_headers):
            entry_header.pack_data(header_writer, entry_writer, entry.data + b"\0" * 10)

    Binder._entries_into_writer_v4 = patched_entries_into_writer_v4

apply_soulstruct_patches()

