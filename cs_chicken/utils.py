# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Small shared helpers: add-on id, paths, preference access, logging."""

import logging
import os

import bpy

# Package name as Blender sees it ("cs_chicken" for legacy installs,
# "bl_ext.<repo>.cs_chicken" for extensions). Used as AddonPreferences id.
ADDON_ID = __package__
# Name of the module towards a host add-on (cs.blend), whatever the package path.
MODULE_ID = "cs_chicken"

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
# Only present in personal builds (tools/build_zip.py --with-chickens).
BUNDLED_LIBRARY_DIR = os.path.join(ADDON_DIR, "chickens", "bundled")
# Extra library folder loaded before all others. Nothing ships there; the
# tests point it at tests/fixtures/library.
CORE_LIBRARY_DIR = ""

# Custom property keys.
PROP_CHICKEN_ID = "cs_chicken_id"            # on chicken roots
PROP_MODEL = "cs_chicken_model"              # on chicken roots: model file
PROP_PART = "cs_chicken_part"                # on the meshes of a chicken
PROP_TEMPLATE = "cs_chicken_template"        # on template collections
PROP_TEMPLATE_ROOT = "cs_chicken_template_root"
PROP_MATERIAL_KEY = "cs_chicken_material"    # on chicken materials
PROP_MATERIAL_SPEC = "cs_chicken_spec"       # JSON copy of the spec
PROP_OWNER = "cs_chicken_owner"              # on per-chicken materials: root name
PROP_COLLECTION = "cs_chicken_collection"    # on the per-scene chicken collections

CHICKEN_COLLECTION_NAME = "CS Chickens"

log = logging.getLogger("cs_chicken")


# Host add-on (cs.blend) when registered as its sub-module, else None.
# The host provides settings(module_id) and user_path(module_id, sub, create).
_host = None


def set_host(host):
    global _host
    _host = host


def get_host():
    return _host


def prefs():
    """The settings (preferences.CSCHICKEN_PG_settings) or None, e.g. while
    not registered. Standalone they hang off the add-on preferences, in host
    mode the host keeps them."""
    if _host is not None:
        return _host.settings(MODULE_ID)
    addon = bpy.context.preferences.addons.get(ADDON_ID)
    return getattr(addon.preferences, "settings", None) if addon else None


def user_path(sub="", create=True):
    """Folder for the add-on's own user data, or '' if there is none
    (legacy install without host)."""
    try:
        if _host is not None:
            return _host.user_path(MODULE_ID, sub, create=create) or ""
        getter = getattr(bpy.utils, "extension_path_user", None)
        if getter is not None and ADDON_ID.startswith("bl_ext."):
            return getter(ADDON_ID, path=sub, create=create)
    except (ValueError, RuntimeError, OSError):
        pass
    return ""


def user_library_dir():
    """Absolute user library path from the preferences, or '' if unset/invalid."""
    settings = prefs()
    if settings is None or not settings.user_path:
        return ""
    path = bpy.path.abspath(settings.user_path)
    return path if os.path.isdir(path) else ""


def library_dirs():
    """Library folders in load order (later ones win on equal ids)."""
    return [d for d in (CORE_LIBRARY_DIR, BUNDLED_LIBRARY_DIR, user_library_dir()) if d and os.path.isdir(d)]


def is_chicken(obj):
    return obj is not None and PROP_CHICKEN_ID in obj


def chicken_root(obj):
    """The chicken an object belongs to (its root), or None."""
    while obj is not None:
        if is_chicken(obj):
            return obj
        obj = obj.parent
    return None


def chicken_parts(root):
    """Mesh objects of a chicken."""
    if root is None:
        return []
    return [o for o in root.children_recursive if o.type == "MESH" and PROP_PART in o]


def chicken_collection(context):
    """Get (or create) the collection that holds the chickens of this scene.
    Every scene gets its own (a collection linked into two scenes shows the
    same objects in both)."""
    scene = context.scene
    for coll in scene.collection.children_recursive:
        if PROP_COLLECTION in coll:
            return coll
    coll = bpy.data.collections.new(CHICKEN_COLLECTION_NAME)
    coll[PROP_COLLECTION] = True
    scene.collection.children.link(coll)
    return coll


def active_chicken(context):
    return chicken_root(context.active_object)
