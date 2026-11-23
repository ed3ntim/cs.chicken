# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Creating chicken objects: glTF import, templates, materials, variants.

The first spawn of a model imports the .glb with Blender's glTF importer
(armature + skinned mesh) into a template collection that is not part of
any scene. Every spawn copies the template: a new armature object with its
own armature data and new mesh objects whose Armature modifiers point to
it, so every chicken can be posed and animated on its own (cs.anim).
Unrigged models (egg) get an empty as root.

Each mesh remembers the glTF material name per slot (``cs_chicken_slots``)
because the slots get cs.chicken materials: switching the color variant
just assigns the materials of another catalog entry of the same model.
Materials with appearance inputs (egg, chick) belong to one chicken;
all others are shared between chickens of the same variant.
"""

import json
import math
import os
import random

import bpy

from .. import api, utils
from ..library import catalog as C
from ..library import registry
from ..nodes import material as M

TEMPLATE_PREFIX = "cs.chicken template "
TEMPLATE_VERSION = 1
BONE_HEURISTIC = "TEMPERANCE"
PROP_SLOTS = "cs_chicken_slots"          # on meshes: glTF material names per slot
PROP_BONE_HEURISTIC = "cs_chicken_bone_heuristic"


def _strip_suffix(name):
    head, _, tail = name.rpartition(".")
    return head if head and tail.isdigit() and len(tail) == 3 else name


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _template_key(model):
    return json.dumps([os.path.normcase(os.path.abspath(model)), round(_mtime(model), 3), TEMPLATE_VERSION])


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def _find_template(key):
    for coll in bpy.data.collections:
        if coll.get(utils.PROP_TEMPLATE) == key and coll.objects:
            return coll
    return None


def _template_root(coll):
    return next((o for o in coll.objects if o.get(utils.PROP_TEMPLATE_ROOT)), None)


def _import_gltf(path):
    kwargs = {"filepath": path, "bone_heuristic": BONE_HEURISTIC}
    for extra in ({"guess_original_bind_pose": True, "disable_bone_shape": True},
                  {"guess_original_bind_pose": True}, {}):
        try:
            return bpy.ops.import_scene.gltf(**kwargs, **extra)
        except TypeError:  # option renamed / missing in this Blender version
            continue
    return bpy.ops.import_scene.gltf(filepath=path)


def _import_template(model):
    before_objs = set(bpy.data.objects)
    before_colls = set(bpy.data.collections)
    if "FINISHED" not in _import_gltf(model):
        raise RuntimeError(f"glTF import failed: {model}")
    new_objs = [o for o in bpy.data.objects if o not in before_objs]
    if not any(o.type == "MESH" for o in new_objs):
        for o in new_objs:
            bpy.data.objects.remove(o, do_unlink=True)
        raise RuntimeError(f"no mesh in {os.path.basename(model)}")

    coll = bpy.data.collections.new(TEMPLATE_PREFIX + os.path.basename(model))
    coll.use_fake_user = True
    coll[utils.PROP_TEMPLATE] = _template_key(model)
    for obj in new_objs:
        for user in list(obj.users_collection):
            user.objects.unlink(obj)
        coll.objects.link(obj)
    # Leftovers of the importer (bone shapes collection)
    for extra in [c for c in bpy.data.collections if c not in before_colls and c is not coll]:
        if not extra.objects and not extra.children:
            bpy.data.collections.remove(extra)

    root = next((o for o in new_objs if o.type == "ARMATURE"), None)
    if root is None:
        root = bpy.data.objects.new(os.path.splitext(os.path.basename(model))[0], None)
        root.empty_display_type = "PLAIN_AXES"
        root.empty_display_size = 0.1
        coll.objects.link(root)
        for obj in new_objs:
            if obj.parent is None and obj.type == "MESH":
                obj.parent = root
    root[utils.PROP_TEMPLATE_ROOT] = True
    root[PROP_BONE_HEURISTIC] = BONE_HEURISTIC

    for obj in new_objs:
        if obj.type != "MESH":
            continue
        if obj.parent is not root and obj.parent is not None and obj.parent.type != "ARMATURE":
            continue  # bone shape or helper
        obj[utils.PROP_PART] = True
        obj.data[PROP_SLOTS] = [_strip_suffix(m.name) if m else "" for m in obj.data.materials]
    return coll


def template_for(model):
    """(template collection, freshly imported?)"""
    key = _template_key(model)
    coll = _find_template(key)
    if coll is not None and _template_root(coll) is not None:
        return coll, False
    return _import_template(model), True


def clear_templates():
    """Remove all cached templates. Returns the number removed."""
    count = 0
    for coll in [c for c in bpy.data.collections if utils.PROP_TEMPLATE in c]:
        for obj in list(coll.objects):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            _remove_data(data)
        bpy.data.collections.remove(coll)
        count += 1
    return count


def _remove_data(data):
    if data is None or data.users:
        return
    if isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)
    elif isinstance(data, bpy.types.Armature):
        bpy.data.armatures.remove(data)


def _copy_template(coll, target_coll):
    """Copy root and parts into ``target_coll``. Returns the new root."""
    src_root = _template_root(coll)
    sources = [src_root] + [o for o in src_root.children_recursive if o.get(utils.PROP_PART)]
    mapping = {}
    for obj in sources:
        cp = obj.copy()
        if obj.data is not None:
            cp.data = obj.data.copy()
        target_coll.objects.link(cp)
        mapping[obj] = cp
    for obj, cp in mapping.items():
        if obj.parent in mapping:
            cp.parent = mapping[obj.parent]
            cp.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
        for mod in cp.modifiers:
            if mod.type == "ARMATURE" and mod.object in mapping:
                mod.object = mapping[mod.object]
    root = mapping[src_root]
    del root[utils.PROP_TEMPLATE_ROOT]
    return root


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def _shared_material(spec):
    for mat in bpy.data.materials:
        if mat.get(utils.PROP_MATERIAL_KEY) == spec.key and utils.PROP_OWNER not in mat:
            return mat
    return None


def _material_for(spec, root, env, warnings):
    """Shared material of a spec, or a new one owned by ``root`` when the
    spec has appearance inputs."""
    name = C.variant_name(spec.key) if spec.key else root.name
    if spec.inputs:
        mat, warn = M.build_material(spec, f"{root.name} {name}", env)
        mat[utils.PROP_OWNER] = root.name
        warnings += warn
        return mat
    mat = _shared_material(spec)
    if mat is None:
        mat, warn = M.build_material(spec, f"CS2 {name}")
        warnings += warn
    return mat


def _owned(mat):
    return mat is not None and utils.PROP_OWNER in mat


def assign_materials(root, chicken):
    """Give every part slot the material of ``chicken`` (catalog entry).
    Slots without a spec keep the material of the glTF import. Returns
    warnings."""
    warnings = []
    env = appearance_env(root)
    built = {}
    old = set()
    for obj in utils.chicken_parts(root):
        names = list(obj.data.get(PROP_SLOTS, []))
        for i, slot in enumerate(obj.data.materials):
            gltf_name = names[i] if i < len(names) else (_strip_suffix(slot.name) if slot else "")
            spec = chicken.materials.get(gltf_name)
            if spec is None or not spec.supported:
                continue
            if spec.key not in built:
                built[spec.key] = _material_for(spec, root, env, warnings)
            if _owned(slot):
                old.add(slot)
            obj.data.materials[i] = built[spec.key]
    for mat in old:
        if mat.users == 0:
            bpy.data.materials.remove(mat)
    return warnings


# ---------------------------------------------------------------------------
# Appearance ($egg_hue ...)
# ---------------------------------------------------------------------------

def appearance_env(root):
    """Appearance inputs of ``root`` for the DynamicParams, None at seed 0
    (original material: the textures and values as Valve authored them,
    every CS2 range ends there, e.g. saturation lerp(.4,1,...))."""
    state = root.cs_chicken
    if int(state.seed) == C.NEUTRAL_SEED:
        return None
    return {item.name: float(item.value) for item in state.inputs}


def _set_inputs(root, names, seed):
    state = root.cs_chicken
    values = C.appearance_from_seed(seed, names)
    state.inputs.clear()
    for name in names:
        item = state.inputs.add()
        item.name = name
        item["value"] = values[name]  # item assignment: no update callback per input


def _make_own(root):
    """Per-chicken materials used outside this chicken (Shift+D copies the
    objects, not the materials) are copied, so changes stay local."""
    parts = utils.chicken_parts(root)
    own_uses = {}
    for obj in parts:
        for mat in obj.data.materials:
            if _owned(mat):
                own_uses[mat] = own_uses.get(mat, 0) + 1
    for mat, uses in own_uses.items():
        if mat.users > uses or mat.get(utils.PROP_OWNER) != root.name:
            new = mat.copy()
            new[utils.PROP_OWNER] = root.name
            new.name = f"{root.name} {C.variant_name(mat.get(utils.PROP_MATERIAL_KEY, ''))}"
            for obj in parts:
                for i, m in enumerate(obj.data.materials):
                    if m == mat:
                        obj.data.materials[i] = new


def apply_appearance(root):
    """Write the appearance inputs of ``root`` into its own materials."""
    if root is None:
        return
    _make_own(root)
    env = appearance_env(root)
    for obj in utils.chicken_parts(root):
        for mat in obj.data.materials:
            if _owned(mat):
                spec = M.spec_from_material(mat)
                if spec is not None:
                    M.apply_values(mat, spec, env)


def reseed(root):
    chicken = registry.get(root.cs_chicken.chicken_id)
    names = chicken.inputs if chicken is not None else [i.name for i in root.cs_chicken.inputs]
    _set_inputs(root, names, root.cs_chicken.seed)
    apply_appearance(root)


# ---------------------------------------------------------------------------
# Chickens
# ---------------------------------------------------------------------------

# Fluff cards (chick) stack many alpha-tested layers: with Cycles' default
# of 8 transparent bounces rays end black between them.
MIN_TRANSPARENT_BOUNCES = 128


def ensure_transparent_bounces(scene):
    """Raise Cycles' transparent bounce limit for fluff cards (never lowers it).
    Returns True if it was changed."""
    cycles = getattr(scene, "cycles", None)
    if cycles is None or cycles.transparent_max_bounces >= MIN_TRANSPARENT_BOUNCES:
        return False
    utils.log.info("cs.chicken: Cycles transparent bounces %d -> %d for fluff",
                   cycles.transparent_max_bounces, MIN_TRANSPARENT_BOUNCES)
    cycles.transparent_max_bounces = MIN_TRANSPARENT_BOUNCES
    return True


def create_chicken(context, chicken, seed=1, location=None, rotation=0.0, scale=1.0, age=None):
    """New chicken from a catalog entry. Returns (root, warnings)."""
    if not chicken.model or not os.path.isfile(chicken.model):
        raise RuntimeError(f"model not found: {chicken.model or chicken.name}")
    coll, _fresh = template_for(chicken.model)
    target = utils.chicken_collection(context)
    root = _copy_template(coll, target)
    root.name = chicken.label
    root[utils.PROP_CHICKEN_ID] = chicken.id
    root[utils.PROP_MODEL] = chicken.model
    if root.type == "ARMATURE":
        root.data.name = root.name
        root.show_in_front = False
    for obj in utils.chicken_parts(root):
        obj.name = f"{root.name} mesh"
    state = root.cs_chicken
    state.chicken_id = chicken.id
    state["seed"] = int(seed)
    _set_inputs(root, chicken.inputs, seed)
    warnings = assign_materials(root, chicken)
    if any(spec.flag("F_ALPHA_TEST") for spec in chicken.materials.values()):
        ensure_transparent_bounces(context.scene)
    if location is not None:
        root.location = location
    root.rotation_mode = "XYZ"
    root.rotation_euler.z = rotation
    age = C.DEFAULT_AGE if age is None else min(max(float(age), 0.0), 1.0)
    state["age"] = age
    factor = scale * chicken.scale_at(age)
    root.scale = (factor, factor, factor)
    api.notify_spawned(root)
    return root, warnings


def set_age(root, age):
    """Age within the stage: rescales the root by the model's age scale,
    keeping any scale the user added on top."""
    state = root.cs_chicken
    age = min(max(float(age), 0.0), 1.0)
    chicken = registry.get(state.chicken_id)
    old = float(state.get("age", C.DEFAULT_AGE))
    state["age"] = age
    if chicken is None or not chicken.age_scale:
        return False
    ratio = chicken.scale_at(age) / chicken.scale_at(old)
    root.scale = tuple(v * ratio for v in root.scale)
    return True


def set_variant(root, chicken_id):
    """Switch a chicken to another catalog entry of the same model."""
    chicken = registry.get(chicken_id)
    current = registry.get(root.cs_chicken.chicken_id)
    if chicken is None:
        return False
    if current is not None and os.path.normcase(chicken.model) != os.path.normcase(current.model):
        return False
    root[utils.PROP_CHICKEN_ID] = chicken.id
    root.cs_chicken.chicken_id = chicken.id
    names = chicken.inputs
    if sorted(i.name for i in root.cs_chicken.inputs) != names:
        _set_inputs(root, names, root.cs_chicken.seed)
    assign_materials(root, chicken)
    old_label = current.label if current else ""
    if not old_label or root.name.startswith(old_label):
        root.name = chicken.label
    return True


def delete_chicken(root):
    """Remove a chicken with its parts, data and own materials."""
    objs = [root] + list(root.children_recursive)
    datas = [o.data for o in objs if o.data is not None]
    mats = {m for o in objs if o.type == "MESH" for m in o.data.materials if _owned(m)}
    for obj in objs:
        bpy.data.objects.remove(obj, do_unlink=True)
    for data in datas:
        _remove_data(data)
    for mat in mats:
        if mat.users == 0:
            bpy.data.materials.remove(mat)


def new_seed():
    return random.randint(1, 2**31 - 1)


def random_angle():
    return random.uniform(0.0, 2.0 * math.pi)
