# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Read the JSON part of .glb / .gltf files (no geometry), pure Python.

Source2Viewer writes the original CS2 material into each glTF material's
``extras.vmat`` (shader name, Int/Float/Vector/TextureParams).
"""

import json
import struct

GLB_MAGIC = 0x46546C67  # b"glTF"
CHUNK_JSON = 0x4E4F534A


def read_json(path):
    """glTF JSON of a .glb or .gltf file. Raises ValueError for bad files."""
    with open(path, "rb") as fh:
        head = fh.read(12)
        if len(head) == 12 and struct.unpack("<I", head[:4])[0] == GLB_MAGIC:
            length, kind = struct.unpack("<II", fh.read(8))
            if kind != CHUNK_JSON:
                raise ValueError(f"{path}: first GLB chunk is not JSON")
            return json.loads(fh.read(length).decode("utf-8"))
        fh.seek(0)
        try:
            return json.loads(fh.read().decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}: not a glTF file ({exc})") from None


def material_extras(data):
    """[(material name, vmat dict or None)] in glTF material order."""
    out = []
    for i, mat in enumerate(data.get("materials", [])):
        extras = mat.get("extras") or {}
        vmat = extras.get("vmat") if isinstance(extras, dict) else None
        out.append((mat.get("name") or f"material_{i}", vmat if isinstance(vmat, dict) else None))
    return out


def joint_names(data):
    """Bone names of the first skin ([] for unrigged models)."""
    skins = data.get("skins") or []
    nodes = data.get("nodes") or []
    if not skins:
        return []
    return [nodes[i].get("name", f"joint_{i}") for i in skins[0].get("joints", []) if i < len(nodes)]


def has_skin(data):
    return bool(data.get("skins"))


def image_uris(data):
    """Relative image files the glTF references (textures next to the model)."""
    return [img["uri"] for img in data.get("images", []) if img.get("uri") and "://" not in img["uri"]]
