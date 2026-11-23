# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Generate the test library (run inside Blender):

    blender -b --factory-startup --python tests/fixtures/generate_fixtures.py

Writes tests/fixtures/library/: catalog.json, two models (.glb) and small
procedural textures. Everything is made from scratch here, no game assets.
The data layout matches a real CS2 export, so the tests run the whole
pipeline:

* "Demo Hen"   rigged (armature with a few bones, skinned mesh), two
               glTF materials (body, comb), two color variants that remap
               the body material, csgo_character.vfx with tint mask and
               aniso gloss
* "Demo Egg"   unrigged sphere, one material with DynamicParams driven by
               ``$egg_hue`` / ``$egg_brightness`` (appearance inputs)
"""

import json
import math
import os
import sys

import bpy
import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library")
TEX = 64


def save_png(name, rgba):
    h, w = rgba.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(np.flipud(rgba).astype(np.float32).ravel())
    path = os.path.join(OUT, "textures", name + ".png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return f"textures/{name}.png"


def solid(rgb, alpha=1.0):
    out = np.ones((TEX, TEX, 4))
    out[..., :3] = rgb
    out[..., 3] = alpha
    return out


def stripes(a, b):
    v = np.mgrid[0:TEX, 0:TEX][0] / (TEX - 1)
    mask = (np.sin(v * math.pi * 8) > 0)[..., None]
    out = np.where(mask, np.asarray(a + (1.0,)), np.asarray(b + (1.0,)))
    return out


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def export(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    path = os.path.join(OUT, "models", name + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                              export_materials="EXPORT", export_image_format="NONE",
                              export_yup=True, export_apply=False, export_animations=False)
    return f"models/{name}.glb"


def build_hen():
    """Armature (pelvis, spine, neck, head) and a skinned body + comb."""
    arm_data = bpy.data.armatures.new("demo_hen_skel")
    arm = bpy.data.objects.new("demo_hen", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    chain = (("pelvis", (0, 0, 0.12), (0, 0, 0.18)), ("spine_0", (0, 0, 0.18), (0, 0.05, 0.24)),
             ("neck_0", (0, 0.05, 0.24), (0, 0.08, 0.32)), ("head_0", (0, 0.08, 0.32), (0, 0.10, 0.38)))
    parent = None
    for name, head, tail in chain:
        bone = arm_data.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent is not None:
            bone.parent = parent
            bone.use_connect = True
        parent = bone
    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.1, location=(0, 0, 0.2))
    body = bpy.context.active_object
    body.name = "demo_hen_body"
    body.data.materials.append(material("hen_body_white", (0.9, 0.9, 0.85, 1)))
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.03, depth=0.05, location=(0, 0.1, 0.36))
    comb = bpy.context.active_object
    comb.data.materials.append(material("hen_comb", (0.8, 0.1, 0.1, 1)))
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    comb.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    body = bpy.context.active_object
    for v_group in ("pelvis", "spine_0", "neck_0", "head_0"):
        body.vertex_groups.new(name=v_group)
    for v in body.data.vertices:
        z = v.co.z + body.location.z
        name = "pelvis" if z < 0.17 else "spine_0" if z < 0.24 else "neck_0" if z < 0.32 else "head_0"
        body.vertex_groups[name].add([v.index], 1.0, "REPLACE")
    bpy.ops.object.transform_apply(location=True)
    body.parent = arm
    mod = body.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return [arm, body]


def build_egg():
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.04, location=(0, 0, 0.05))
    egg = bpy.context.active_object
    egg.name = "demo_egg"
    egg.scale = (1, 1, 1.3)
    bpy.ops.object.transform_apply(location=True, scale=True)
    egg.data.materials.append(material("egg_shell", (0.95, 0.9, 0.8, 1)))
    return [egg]


def main():
    for sub in ("models", "textures"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    reset()
    normal = save_png("demo_normal", solid((0.5, 0.5, 1.0)))
    tint = save_png("demo_tint", stripes((1.0, 1.0, 1.0), (0.0, 0.0, 0.0)))
    gloss = save_png("demo_gloss", solid((0.6, 0.5, 0.5)))
    tex = {
        "white": save_png("demo_hen_white", stripes((0.92, 0.9, 0.85), (0.8, 0.78, 0.7))),
        "black": save_png("demo_hen_black", stripes((0.1, 0.1, 0.1), (0.2, 0.18, 0.15))),
        "comb": save_png("demo_comb", solid((0.75, 0.08, 0.06))),
        "egg": save_png("demo_egg", solid((0.9, 0.85, 0.75))),
    }

    def character(color, extra=None, dynamic=None, constants=None):
        params = {"F_TINT_MASK": 1, "F_ANISOTROPIC_GLOSS": 1, "g_fHueShift": 0.0, "g_fSaturation": 1.0,
                  "g_fBrightness": 1.0, "g_fContrast": 1.0, "g_vColorTint": [1, 1, 1, 0]}
        params.update(extra or {})
        return {"shader": "csgo_character.vfx", "params": params, "dynamic": dynamic or {},
                "textures": {"TextureColor": color, "TextureNormal": normal, "TextureTintMask": tint,
                             "g_tAnisoGloss": gloss},
                "constants": constants or {}}

    materials = {
        "materials/demo/hen_body_white.vmat": character(tex["white"]),
        "materials/demo/hen_body_black.vmat": character(tex["black"], {"g_fBrightness": 1.2}),
        "materials/demo/hen_comb.vmat": character(tex["comb"], {"F_TINT_MASK": 0}),
        "materials/demo/egg_shell.vmat": {
            "shader": "csgo_character.vfx",
            "params": {"F_TINT_MASK": 1, "g_fHueShift": 0.0, "g_fBrightness": 1.0},
            "dynamic": {"g_fHueShift": "return lerp(-12,165,$egg_hue*$egg_hue);",
                        "g_fBrightness": "return lerp(.8,1.2,$egg_brightness);"},
            "textures": {"TextureColor": tex["egg"], "TextureNormal": normal, "TextureTintMask": tint},
            "constants": {"TextureRoughness": [0.6, 0.6, 0.6, 1.0]},
        },
        "materials/demo/unsupported.vmat": {"shader": "csgo_complex.vfx", "params": {}, "dynamic": {},
                                            "textures": {}, "constants": {}},
    }
    hen_model = export(build_hen(), "demo_hen")
    reset()
    egg_model = export(build_egg(), "demo_egg")

    def hen(variant, body):
        return {"id": f"demo_hen_{variant}", "name": "Demo Hen", "kind": "CHICKEN", "breed": "Demo",
                "variant": variant.capitalize(), "model": hen_model, "icon": "",
                "slots": {"hen_body_white": body, "hen_comb": "materials/demo/hen_comb.vmat"},
                "def_index": 90, "tags": ["chicken_demo_01"],
                "skeleton": "animation/skeletons/demo/demo_hen.vnmskel", "age_scale": [0.3, 0.5]}

    catalog = {
        "version": 1,
        "generator": "cs.chicken tests/fixtures/generate_fixtures.py",
        "note": "Test chickens made from scratch, no game assets.",
        "chickens": [
            hen("white", "materials/demo/hen_body_white.vmat"),
            hen("black", "materials/demo/hen_body_black.vmat"),
            {"id": "demo_egg", "name": "Demo Egg", "kind": "EGG", "breed": "", "variant": "",
             "model": egg_model, "icon": "", "slots": {"egg_shell": "materials/demo/egg_shell.vmat"},
             "def_index": 91, "tags": ["chicken_egg_01"], "skeleton": ""},
            {"id": "demo_missing", "name": "Demo Missing", "kind": "PROP", "model": "models/nope.glb",
             "slots": {}, "tags": []},
        ],
        "materials": materials,
    }
    with open(os.path.join(OUT, "catalog.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(catalog, fh, indent=1)
        fh.write("\n")
    print(f"demo chickens -> {OUT}")


if __name__ == "__main__":
    main()
    sys.exit(0)
