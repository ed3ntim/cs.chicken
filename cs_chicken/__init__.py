# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""cs.chicken - spawn the CS2 chickens and eggs (pets) with their materials.

Works both as a Blender 4.5+ extension (blender_manifest.toml) and as a
legacy add-on (bl_info). Sub-packages:

    library/  chicken database: catalog, shader table, DynamicParams evaluator
    nodes/    node groups and material assembly (csgo_character.vfx)
    ops/      operators: spawning, variants, appearance, removal
    ui/       sidebar panels and the library list
    api.py    API for partner add-ons (cs.anim)
    preview_render.py  preview images, run in a background Blender

Host mode (cs.blend): a host add-on registers the package as a sub-module
with ``register(host)``. It then registers SETTINGS (after register), keeps
one instance per module and provides ``host.settings(MODULE_ID)`` and
``host.user_path(MODULE_ID, sub, create)``; it draws the settings with
``draw_prefs(layout, settings)``. Standalone (host None) nothing changes.
"""

bl_info = {
    "name": "cs.chicken",
    "author": "ed3n",
    "version": (0, 4, 0),
    "blender": (4, 5, 0),
    "location": "3D Viewport > Sidebar > cs.chicken",
    "description": "Spawn the CS2 chickens and eggs with their materials",
    "category": "Object",
    "support": "COMMUNITY",
}

# Support "Reload Scripts": re-import submodules if already loaded.
if "bpy" in locals():
    import importlib

    for _mod in (utils, preferences, properties, library, nodes, ops, ui, api):  # noqa: F821
        importlib.reload(_mod)

import bpy  # noqa: E402,F401

from . import utils, preferences, properties, library, nodes, ops, ui, api  # noqa: E402

# Registration order matters: property groups before anything that points to them.
_modules = (properties, library, ops, ui)

MODULE_ID = utils.MODULE_ID
SETTINGS = preferences.CSCHICKEN_PG_settings
draw_prefs = preferences.draw_prefs


def register(host=None):
    utils.set_host(host)
    preferences.register(host)
    for mod in _modules:
        mod.register()


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
    preferences.unregister()
    utils.set_host(None)
