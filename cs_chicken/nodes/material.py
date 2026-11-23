# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Material assembly: one Blender material per CS2 material::

    UV Map ─┬──────────────────── TEX_COLOR / TEX_NORMAL / TEX_ROUGHNESS / ...
            └─ CHICKEN_DETAIL_UV ── TEX_DETAIL ─┐
                                                └─ CHICKEN_MAIN ── Output

CHICKEN_MAIN is the "CS2 Chicken Character" group. Static parameters and
the evaluated DynamicParams are written to its inputs through
library/shading.py. A JSON copy of the spec is stored on the material so
the appearance can be changed in saved files without the library.

Materials without appearance inputs are shared by all chickens of that
variant; with inputs (egg, chick) every chicken gets its own copy.
"""

import json
import os

import bpy

from .. import utils
from ..library import catalog as C
from ..library import shading as S
from . import groups

_TEX_PREFIX = "TEX_"


def _load_image(path, colorspace):
    """Load (or reuse) a texture. Alpha is never premultiplied into the
    color: CS2 maps carry data in alpha or have alpha 0."""
    img = bpy.data.images.load(path, check_existing=True)
    try:
        img.colorspace_settings.name = colorspace
    except TypeError:  # colorspace missing in a custom OCIO config
        pass
    img.alpha_mode = "CHANNEL_PACKED"
    return img


def spec_from_material(mat):
    raw = mat.get(utils.PROP_MATERIAL_SPEC) if mat else None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return C.MaterialSpec.from_dict(data.get("key", mat.name), data)


def is_chicken_material(mat):
    return mat is not None and utils.PROP_MATERIAL_KEY in mat


def build_material(spec, name, env=None):
    """Create a material for ``spec``. Returns (material, warnings)."""
    warnings = []
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    main = nodes.new("ShaderNodeGroup")
    main.name = main.label = S.NODE_MAIN
    main.node_tree = groups.ensure_group("CHARACTER")
    main.location = (350, 0)
    main.width = 240
    links.new(main.outputs[0], out.inputs["Surface"])

    uv = nodes.new("ShaderNodeUVMap")
    uv.location = (-900, 0)

    y = 600
    for key, path in spec.textures.items():
        role_info = S.texture_role(key)
        if role_info is None:
            continue
        role, colorspace = role_info
        if role == "ANISO" and not spec.flag("F_ANISOTROPIC_GLOSS"):
            continue
        if not os.path.isfile(path):
            warnings.append(f"{name}: missing texture {os.path.basename(path)}")
            continue
        tex = nodes.new("ShaderNodeTexImage")
        tex.name = tex.label = _TEX_PREFIX + role
        tex.location = (-350, y)
        y -= 280
        tex.image = _load_image(path, colorspace)
        if role == "DETAIL":
            helper = nodes.new("ShaderNodeGroup")
            helper.name = helper.label = S.NODE_DETAIL_UV
            helper.node_tree = groups.ensure_group("UV")
            helper.location = (-650, tex.location.y)
            links.new(uv.outputs[0], helper.inputs["UV"])
            links.new(helper.outputs[0], tex.inputs["Vector"])
        else:
            links.new(uv.outputs[0], tex.inputs["Vector"])
        _wire_texture(links, tex, role, main)

    mat[utils.PROP_MATERIAL_KEY] = spec.key
    mat[utils.PROP_MATERIAL_SPEC] = json.dumps(dict(spec.to_dict(), key=spec.key, textures={}))
    if spec.flag("F_ALPHA_TEST") or spec.flag("F_RENDER_BACKFACES"):
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        mat.use_backface_culling = False
    if spec.flag("F_DO_NOT_CAST_SHADOWS") and hasattr(mat, "use_transparent_shadow"):
        mat.use_transparent_shadow = True
    apply_values(mat, spec, env)
    return mat, warnings


def _wire_texture(links, tex, role, main):
    inputs = main.inputs
    if role == "COLOR":
        links.new(tex.outputs["Color"], inputs["Color"])
        if not inputs["Alpha"].is_linked:  # a separate alpha texture wins
            links.new(tex.outputs["Alpha"], inputs["Alpha"])
    elif role == "ALPHA":
        links.new(tex.outputs["Color"], inputs["Alpha"])
    elif role == "NORMAL":
        links.new(tex.outputs["Color"], inputs["Normal Map"])
    elif role == "ROUGHNESS":
        links.new(tex.outputs["Color"], inputs["Roughness"])
    elif role == "ANISO":
        links.new(tex.outputs["Color"], inputs["Aniso Gloss"])
    elif role == "AO":
        links.new(tex.outputs["Color"], inputs["Ambient Occlusion"])
    elif role == "TINT":
        links.new(tex.outputs["Color"], inputs["Tint Mask"])
    elif role == "DETAIL":
        links.new(tex.outputs["Color"], inputs["Detail"])
    elif role == "IRIDESCENCE":
        links.new(tex.outputs["Color"], inputs["Iridescence Mask"])


def apply_values(mat, spec, env=None):
    """Write static params + the evaluated DynamicParams to the nodes."""
    nodes = mat.node_tree.nodes if mat and mat.node_tree else None
    if nodes is None:
        return
    for (node_name, input_name), value in S.node_values(spec, env).items():
        node = nodes.get(node_name)
        if node is None:
            continue
        sock = node.inputs.get(input_name)
        if sock is None or not hasattr(sock, "default_value") or sock.is_linked:
            continue
        try:
            if isinstance(value, tuple):
                sock.default_value = value[:len(sock.default_value)]
            else:
                sock.default_value = value
        except (TypeError, ValueError) as exc:
            utils.log.warning("cs.chicken: %s.%s = %r failed: %s", node_name, input_name, value, exc)


def main_node(mat):
    if mat is None or mat.node_tree is None:
        return None
    return mat.node_tree.nodes.get(S.NODE_MAIN)
