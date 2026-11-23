# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Sidebar panels (3D Viewport > N > cs.chicken) and the library list."""

import bpy

from .. import api, utils
from ..library import catalog as C
from ..library import registry
from ..ops import chicken_ops

CATEGORY = "cs.chicken"

_KIND_ICONS = {"EGG": "MESH_UVSPHERE", "CHICK": "OUTLINER_OB_ARMATURE", "CHICKEN": "OUTLINER_OB_ARMATURE",
               "HATCHING": "MOD_EXPLODE", "ROASTED": "OUTLINER_OB_MESH", "PROP": "OUTLINER_OB_MESH"}


class CSCHICKEN_UL_library(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        row = layout.row(align=True)
        icon_id = registry.preview_icon(registry.get(item.chicken_id)) if item.complete else 0
        if icon_id:
            row.label(text=item.label, icon_value=icon_id)
        else:
            row.label(text=item.label, icon=_KIND_ICONS.get(item.kind, "DOT") if item.complete else "ERROR")

    def filter_items(self, context, data, propname):
        return [], []  # filtering happens in properties.rebuild_list


class _Panel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY


def _draw_selected(layout, state, chicken):
    """Info box of the chicken selected in the list, with its preview."""
    box = layout.box()
    col = box.column(align=True)
    col.label(text=chicken.label, icon=_KIND_ICONS.get(chicken.kind, "DOT"))
    info = C.KIND_LABELS.get(chicken.kind, chicken.kind) + (f", {chicken.breed}" if chicken.breed else "")
    col.label(text=info, icon="INFO")
    if chicken.age_scale:
        col.label(text="Grows with Age", icon="SORTTIME")
    if chicken.missing:
        col.label(text=f"Missing: {', '.join(chicken.missing[:2])}", icon="ERROR")
    box.prop(state, "show_preview", icon="TRIA_DOWN" if state.show_preview else "TRIA_RIGHT", emboss=False)
    if not state.show_preview:
        return
    icon_id = registry.preview_icon(chicken)
    if icon_id:
        box.template_icon(icon_value=icon_id, scale=8.0)
    elif chicken_ops.preview_job_running():
        box.label(text="Rendering previews ...", icon="RENDER_STILL")
    else:
        box.label(text="No preview image", icon="IMAGE_DATA")
        if utils.user_library_dir():
            box.operator("cs_chicken.render_previews", icon="RENDER_STILL")


class CSCHICKEN_PT_library(_Panel, bpy.types.Panel):
    bl_label = "Library"
    bl_idname = "CSCHICKEN_PT_library"

    def draw(self, context):
        layout = self.layout
        state = context.window_manager.cs_chicken
        cat = registry.get_catalog()
        if not len(cat):
            col = layout.column(align=True)
            col.label(text="No chickens loaded.", icon="INFO")
            col.label(text="Set the library folder in the preferences")
            col.label(text="(tools/export_cs2_chickens.py).")
            layout.operator("cs_chicken.refresh_library", icon="FILE_REFRESH")
            return
        if not state.items and not state.search and state.kind == "ALL":
            from .. import properties
            # First draw after loading: lists can not be filled in draw(), ask a timer.
            bpy.app.timers.register(lambda: properties.rebuild_list(bpy.context.window_manager) and None,
                                    first_interval=0.0)
        layout.prop(state, "search", text="", icon="VIEWZOOM")
        row = layout.row(align=True)
        row.prop(state, "kind", text="")
        row.prop(state, "breed", text="")
        layout.template_list("CSCHICKEN_UL_library", "", state, "items", state, "index", rows=6)
        row = layout.row(align=True)
        row.label(text=f"{len(state.items)} of {len(cat)}")
        row.operator("cs_chicken.refresh_library", text="", icon="FILE_REFRESH")
        chicken = state.selected()
        if chicken is not None:
            _draw_selected(layout, state, chicken)


class CSCHICKEN_PT_placement(_Panel, bpy.types.Panel):
    bl_label = "Placement"
    bl_idname = "CSCHICKEN_PT_placement"

    def draw(self, context):
        layout = self.layout
        opts = context.scene.cs_chicken
        layout.prop(opts, "scale")
        layout.prop(opts, "random_rotation")
        row = layout.row(align=True)
        row.prop(opts, "random_seed")
        sub = row.row(align=True)
        sub.enabled = not opts.random_seed
        sub.prop(opts, "seed")
        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator("cs_chicken.spawn", icon="PIVOT_CURSOR")


class CSCHICKEN_PT_active(_Panel, bpy.types.Panel):
    bl_label = "Active Chicken"
    bl_idname = "CSCHICKEN_PT_active"

    @classmethod
    def poll(cls, context):
        return utils.active_chicken(context) is not None

    def draw(self, context):
        layout = self.layout
        root = utils.active_chicken(context)
        state = root.cs_chicken
        chicken = registry.get(state.chicken_id)
        row = layout.row(align=True)
        row.prop(root, "name", text="")
        row.operator("cs_chicken.select_in_library", text="", icon="VIEWZOOM")
        if chicken is None:
            layout.label(text="Not in the loaded library", icon="ERROR")
        else:
            layout.label(text=f"{C.KIND_LABELS.get(chicken.kind, chicken.kind)}"
                              + (f", {chicken.breed}" if chicken.breed else ""), icon="INFO")
            layout.prop(state, "variant")
            if chicken.age_scale:
                layout.prop(state, "age", slider=True)
        if state.inputs:
            box = layout.box()
            row = box.row(align=True)
            row.prop(state, "seed")
            row.operator("cs_chicken.randomize", text="", icon="FILE_REFRESH")
            col = box.column(align=True)
            if state.seed == C.NEUTRAL_SEED:
                col.label(text="Seed 0: original material", icon="INFO")
                col.enabled = False
            for item in state.inputs:
                col.prop(item, "value", text=C.pretty_name(item.name.lstrip("$")), slider=True)
        if root.type == "ARMATURE":
            layout.label(text=f"Rig: {len(root.data.bones)} bones", icon="ARMATURE_DATA")
        layout.separator()
        row = layout.row()
        row.alert = True
        row.operator("cs_chicken.remove", icon="TRASH")


class CSCHICKEN_PT_integrations(_Panel, bpy.types.Panel):
    bl_label = "Integrations"
    bl_idname = "CSCHICKEN_PT_integrations"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return utils.active_chicken(context) is not None

    def draw(self, context):
        layout = self.layout
        root = utils.active_chicken(context)
        found = api.providers("animation", root)
        for provider in found:
            box = layout.box()
            box.label(text=provider.label)
            try:
                provider.draw(box, context, root)
            except Exception as exc:  # a broken partner must not break the panel
                box.label(text=str(exc), icon="ERROR")
        if not found:
            col = layout.column()
            col.enabled = False
            col.label(text="Animation: install cs.anim", icon="ARMATURE_DATA")


classes = (CSCHICKEN_UL_library, CSCHICKEN_PT_library, CSCHICKEN_PT_placement, CSCHICKEN_PT_active,
           CSCHICKEN_PT_integrations)
