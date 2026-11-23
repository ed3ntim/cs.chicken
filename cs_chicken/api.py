# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Public API for partner add-ons (planned: cs.anim).

Import it through the add-on module so it works for legacy installs,
extensions and the cs.blend suite alike::

    import sys
    mod = next(m for k, m in sys.modules.items()
               if k == "cs_chicken" or k.endswith(".cs_chicken"))
    api = mod.api
    if api.API_VERSION >= 1:
        for chicken in api.chickens(bpy.context.scene):
            arm = api.armature(chicken)

Stable within an ``API_VERSION``. What it offers:

* Finding chickens: ``chickens``, ``chicken_root``, ``is_chicken``,
  ``parts``, ``kind`` ('EGG', 'CHICK', 'CHICKEN', 'HATCHING', 'ROASTED',
  'PROP'), ``info`` (catalog data as a dict).
* The rig: ``armature`` (None for unrigged models such as the egg),
  ``skeleton`` (CS2 skeleton path, e.g.
  'animation/skeletons/characters/chicken/chicken.vnmskel'; clips of
  ``animation/anims/chicken/`` belong to it), ``bone_names``,
  ``rest_pose``, ``bone_heuristic`` (glTF import option the model was
  imported with; clips must be imported the same way).
* Spawning: ``catalog_ids`` and ``spawn`` / ``remove``.
* Providers: ``register_provider("animation", provider)`` puts a
  provider's UI into the "Integrations" panel of the active chicken. A
  provider is any object with ``label`` (str), ``draw(layout, context,
  chicken)`` and optionally ``poll(chicken) -> bool``.
* ``register_spawn_handler(fn)``: ``fn(chicken)`` runs after every spawn.

No function raises for objects that are not chickens (they return None /
empty results instead).
"""

import bpy

from . import utils

API_VERSION = 1

PROVIDER_KINDS = ("animation",)
_providers = {kind: [] for kind in PROVIDER_KINDS}
_spawn_handlers = []


# ---------------------------------------------------------------------------
# Chickens
# ---------------------------------------------------------------------------

def chickens(scene=None):
    """Chicken roots in ``scene`` (default: current)."""
    scene = scene or bpy.context.scene
    return [o for o in scene.objects if utils.is_chicken(o)]


def is_chicken(obj):
    return utils.is_chicken(obj)


def chicken_root(obj):
    return utils.chicken_root(obj)


def parts(chicken):
    return utils.chicken_parts(chicken) if utils.is_chicken(chicken) else []


def _entry(chicken):
    from .library import registry
    if not utils.is_chicken(chicken):
        return None
    return registry.get(chicken.get(utils.PROP_CHICKEN_ID, ""))


def kind(chicken):
    entry = _entry(chicken)
    return entry.kind if entry is not None else ""


def info(chicken):
    """Catalog data of a chicken: id, name, label, kind, breed, variant,
    model, skeleton, def_index. {} for non-chickens or unknown ids."""
    entry = _entry(chicken)
    if entry is None:
        return {}
    return {"id": entry.id, "name": entry.name, "label": entry.label, "kind": entry.kind,
            "breed": entry.breed, "variant": entry.variant, "model": entry.model,
            "skeleton": entry.skeleton, "def_index": entry.def_index}


# ---------------------------------------------------------------------------
# Rig
# ---------------------------------------------------------------------------

def armature(chicken):
    """The armature object of a chicken (its root), or None for unrigged models."""
    return chicken if utils.is_chicken(chicken) and chicken.type == "ARMATURE" else None


def skeleton(chicken):
    entry = _entry(chicken)
    return entry.skeleton if entry is not None else ""


def bone_names(chicken):
    arm = armature(chicken)
    return [b.name for b in arm.data.bones] if arm else []


def bone_heuristic(chicken):
    from .ops import spawn
    return chicken.get(spawn.PROP_BONE_HEURISTIC, spawn.BONE_HEURISTIC) if utils.is_chicken(chicken) else ""


def rest_pose(chicken):
    """Clear all pose transforms (back to the bind pose)."""
    arm = armature(chicken)
    if arm is None:
        return
    for pb in arm.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Spawning
# ---------------------------------------------------------------------------

def catalog_ids(kind=None):
    """Ids of the loaded library, optionally of one kind."""
    from .library import registry
    return [c.id for c in registry.get_catalog() if kind is None or c.kind == kind]


def spawn(chicken_id, location=(0.0, 0.0, 0.0), seed=1, context=None, age=None):
    """Spawn a chicken from the library. Returns the root or None. ``age``
    (0..1) only matters for models with age scales (the chick)."""
    from .library import registry
    from .ops import spawn as S
    entry = registry.get(chicken_id)
    if entry is None:
        return None
    try:
        root, _warnings = S.create_chicken(context or bpy.context, entry, seed=seed, location=location, age=age)
    except RuntimeError as exc:
        utils.log.warning("cs.chicken: %s", exc)
        return None
    return root


def set_age(chicken, age):
    """Age within the stage (0..1). Rescales models with age scales (the
    chick, CS2 ScaleSets age_min/age_max); False for all others."""
    from .ops import spawn as S
    return S.set_age(chicken, age) if utils.is_chicken(chicken) else False


def remove(chicken):
    from .ops import spawn as S
    if utils.is_chicken(chicken):
        S.delete_chicken(chicken)
        return True
    return False


# ---------------------------------------------------------------------------
# Providers and handlers
# ---------------------------------------------------------------------------

def register_provider(kind, provider):
    if kind not in _providers:
        raise ValueError(f"unknown provider kind {kind!r}, expected one of {PROVIDER_KINDS}")
    if provider not in _providers[kind]:
        _providers[kind].append(provider)


def unregister_provider(kind, provider):
    if provider in _providers.get(kind, ()):
        _providers[kind].remove(provider)


def providers(kind, chicken=None):
    out = []
    for p in _providers.get(kind, ()):
        poll = getattr(p, "poll", None)
        try:
            if chicken is None or poll is None or poll(chicken):
                out.append(p)
        except Exception as exc:  # a broken partner must not break the panel
            utils.log.warning("cs.chicken: provider %r failed: %s", p, exc)
    return out


def register_spawn_handler(fn):
    if fn not in _spawn_handlers:
        _spawn_handlers.append(fn)


def unregister_spawn_handler(fn):
    if fn in _spawn_handlers:
        _spawn_handlers.remove(fn)


def notify_spawned(chicken):
    for fn in list(_spawn_handlers):
        try:
            fn(chicken)
        except Exception as exc:
            utils.log.warning("cs.chicken: spawn handler %r failed: %s", fn, exc)
