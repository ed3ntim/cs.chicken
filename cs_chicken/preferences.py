# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Settings (chicken library) and the add-on preferences.

The settings live in a PropertyGroup (CSCHICKEN_PG_settings). Standalone,
the AddonPreferences point to it and add the uninstall button. Under a host
add-on (cs.blend, register(host)) the host keeps the settings and draws
them through draw_prefs(); no AddonPreferences, no uninstall button.
"""

import bpy
from bpy.props import BoolProperty, PointerProperty, StringProperty

from . import utils


def install_location(context):
    """Where the add-on is installed: ("EXTENSION", repo_index, pkg_id),
    ("SYSTEM", repo_index, pkg_id) for a read-only system repo, or
    ("LEGACY", None, module) for an add-on outside the extension system."""
    parts = utils.ADDON_ID.split(".")
    if len(parts) == 3 and parts[0] == "bl_ext":
        for i, repo in enumerate(context.preferences.extensions.repos):
            if repo.module == parts[1]:
                kind = "SYSTEM" if getattr(repo, "source", "") == "SYSTEM" else "EXTENSION"
                return kind, i, parts[2]
        return None
    return "LEGACY", None, utils.ADDON_ID


def _uninstall(location):
    """Run Blender's uninstall once our operator has returned: the add-on
    unregisters itself, so it must not happen inside its own operator."""
    kind, repo_index, pkg = location
    wm = bpy.context.window_manager
    window = wm.windows[0] if wm.windows else None
    with bpy.context.temp_override(window=window):
        if kind == "EXTENSION":
            bpy.ops.extensions.package_uninstall(repo_index=repo_index, pkg_id=pkg)
        else:
            bpy.ops.preferences.addon_remove(module=pkg)
    return None  # one-shot timer


class CSCHICKEN_OT_uninstall(bpy.types.Operator):
    """Disable cs.chicken and delete it from disk. Chickens already placed in
    your files stay as they are; your exported chicken library is kept"""
    bl_idname = "cs_chicken.uninstall"
    bl_label = "Uninstall cs.chicken"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        loc = install_location(context)
        return loc is not None and loc[0] != "SYSTEM"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title="Uninstall cs.chicken?",
            message="The add-on is disabled and its files are deleted.",
            confirm_text="Uninstall", icon="WARNING")

    def execute(self, context):
        location = install_location(context)
        bpy.app.timers.register(lambda: _uninstall(location), first_interval=0.1)
        return {"FINISHED"}


def _on_path_change(self, context):
    from .library import registry
    registry.refresh()


class CSCHICKEN_PG_settings(bpy.types.PropertyGroup):
    user_path: StringProperty(
        name="Chicken Library Folder",
        description="Folder made by tools/export_cs2_chickens.py (catalog.json, models, textures)",
        subtype="DIR_PATH",
        update=_on_path_change,
    )
    include_incomplete: BoolProperty(
        name="List Incomplete Chickens", default=True,
        description="Also list chickens whose model or textures are missing (shown with a warning icon)",
    )


def draw_prefs(layout, settings):
    """Settings UI, for the AddonPreferences and for a host add-on."""
    layout.prop(settings, "user_path")
    row = layout.row(align=True)
    row.operator("cs_chicken.refresh_library", icon="FILE_REFRESH")
    row.operator("cs_chicken.open_user_folder", icon="FILEBROWSER")
    layout.prop(settings, "include_incomplete")
    from .library import registry
    from .ops import chicken_ops
    layout.label(text=registry.status_text(), icon="INFO")
    row = layout.row(align=True)
    if chicken_ops.preview_job_running():
        row.label(text="Rendering previews in the background ...", icon="RENDER_STILL")
    else:
        missing = chicken_ops.missing_previews()
        row.operator("cs_chicken.render_previews", icon="RENDER_STILL",
                     text=f"Render Previews ({missing} missing)" if missing else "Render Previews")
        row.operator("cs_chicken.render_previews", text="Render All Again", icon="FILE_REFRESH").all = True
    col = layout.column(align=True)
    col.label(text="Export the CS2 chickens from your own game install:", icon="INFO")
    col.label(text="  python tools/export_cs2_chickens.py --out <folder> --download-s2v")


class CSCHICKEN_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = utils.ADDON_ID

    settings: PointerProperty(type=CSCHICKEN_PG_settings)

    def draw(self, context):
        layout = self.layout
        draw_prefs(layout, self.settings)
        layout.separator()
        row = layout.row()
        row.alert = True
        row.operator("cs_chicken.uninstall", icon="TRASH")
        loc = install_location(context)
        if loc is not None and loc[0] == "SYSTEM":
            layout.label(text="Installed in a system repository, remove it there.", icon="INFO")


_standalone = False


def register(host=None):
    global _standalone
    bpy.utils.register_class(CSCHICKEN_PG_settings)
    _standalone = host is None
    if not _standalone:
        return
    bpy.utils.register_class(CSCHICKEN_OT_uninstall)
    bpy.utils.register_class(CSCHICKEN_AP_preferences)


def unregister():
    global _standalone
    if _standalone:
        bpy.utils.unregister_class(CSCHICKEN_AP_preferences)
        bpy.utils.unregister_class(CSCHICKEN_OT_uninstall)
        _standalone = False
    bpy.utils.unregister_class(CSCHICKEN_PG_settings)
