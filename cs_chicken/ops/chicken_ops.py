# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Operators: spawn, spawn all variants (demo, not in the UI), remove,
appearance, library, previews."""

import os

import bpy
from bpy.props import BoolProperty, StringProperty
from mathutils import Vector

from .. import utils
from ..library import registry
from . import spawn


def _report_warnings(op, warnings):
    for w in warnings[:5]:
        op.report({"WARNING"}, w)
    if len(warnings) > 5:
        op.report({"WARNING"}, f"... and {len(warnings) - 5} more (see console)")
        for w in warnings[5:]:
            print("cs.chicken:", w)


def _spawn(op, context, chicken, location):
    opts = context.scene.cs_chicken
    seed = spawn.new_seed() if opts.random_seed else opts.seed
    rotation = spawn.random_angle() if opts.random_rotation else 0.0
    try:
        root, warnings = spawn.create_chicken(context, chicken, seed=seed, location=location,
                                              rotation=rotation, scale=opts.scale)
    except RuntimeError as exc:
        op.report({"ERROR"}, str(exc))
        return None
    _report_warnings(op, warnings)
    return root


def _select_only(context, root):
    for obj in context.selected_objects:
        obj.select_set(False)
    root.select_set(True)
    context.view_layer.objects.active = root


class CSCHICKEN_OT_spawn(bpy.types.Operator):
    """Spawn the selected chicken or egg at the 3D cursor"""
    bl_idname = "cs_chicken.spawn"
    bl_label = "Spawn at Cursor"
    bl_options = {"REGISTER", "UNDO"}

    chicken_id: StringProperty(name="Chicken", description="Catalog id; empty = selected in the list",
                               options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        chicken = registry.get(self.chicken_id) if self.chicken_id else context.window_manager.cs_chicken.selected()
        if chicken is None:
            self.report({"WARNING"}, "Select a chicken in the library first")
            return {"CANCELLED"}
        root = _spawn(self, context, chicken, context.scene.cursor.location.copy())
        if root is None:
            return {"CANCELLED"}
        _select_only(context, root)
        return {"FINISHED"}


class CSCHICKEN_OT_spawn_variants(bpy.types.Operator):
    """Spawn every color variant of the selected breed in a row from the 3D cursor
    (demo and test helper, not in the panels: F3 > Spawn All Variants)"""
    bl_idname = "cs_chicken.spawn_variants"
    bl_label = "Spawn All Variants"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and context.window_manager.cs_chicken.selected() is not None

    def execute(self, context):
        current = context.window_manager.cs_chicken.selected()
        variants = [c for c in registry.get_catalog() if c.model == current.model and c.complete]
        start = context.scene.cursor.location.copy()
        step = Vector((context.scene.cs_chicken.spacing, 0.0, 0.0))
        roots = []
        for i, chicken in enumerate(variants):
            root = _spawn(self, context, chicken, start + step * i)
            if root is not None:
                roots.append(root)
        if not roots:
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        for root in roots:
            root.select_set(True)
        context.view_layer.objects.active = roots[0]
        self.report({"INFO"}, f"{len(roots)} variants spawned")
        return {"FINISHED"}


class CSCHICKEN_OT_remove(bpy.types.Operator):
    """Delete the active chicken with its mesh, rig and own materials"""
    bl_idname = "cs_chicken.remove"
    bl_label = "Remove Chicken"
    bl_options = {"REGISTER", "UNDO"}

    all_selected: BoolProperty(name="All Selected", default=False,
                               description="Remove every selected chicken, not only the active one")

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and utils.active_chicken(context) is not None

    def execute(self, context):
        roots = {utils.active_chicken(context)}
        if self.all_selected:
            roots |= {utils.chicken_root(o) for o in context.selected_objects}
        roots.discard(None)
        for root in roots:
            spawn.delete_chicken(root)
        self.report({"INFO"}, f"{len(roots)} removed")
        return {"FINISHED"}


class CSCHICKEN_OT_randomize(bpy.types.Operator):
    """New random seed for the active chicken (egg and chick: hue, brightness, speckles)"""
    bl_idname = "cs_chicken.randomize"
    bl_label = "Randomize Appearance"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        root = utils.active_chicken(context)
        return root is not None and len(root.cs_chicken.inputs) > 0

    def execute(self, context):
        root = utils.active_chicken(context)
        root.cs_chicken.seed = spawn.new_seed()  # update callback reseeds
        return {"FINISHED"}


class CSCHICKEN_OT_refresh_library(bpy.types.Operator):
    """Read the chicken library folders again"""
    bl_idname = "cs_chicken.refresh_library"
    bl_label = "Refresh Library"

    def execute(self, context):
        from .. import properties
        cat = registry.refresh()
        properties.rebuild_list(context.window_manager)
        for err in registry.errors():
            self.report({"WARNING"}, err)
        self.report({"INFO"}, f"{len(cat)} chickens loaded")
        return {"FINISHED"}


class CSCHICKEN_OT_open_user_folder(bpy.types.Operator):
    """Open the chicken library folder in the file browser"""
    bl_idname = "cs_chicken.open_user_folder"
    bl_label = "Open Folder"

    @classmethod
    def poll(cls, context):
        return bool(utils.user_library_dir())

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=utils.user_library_dir())
        return {"FINISHED"}


class CSCHICKEN_OT_clear_templates(bpy.types.Operator):
    """Forget the imported models (they are imported again on the next spawn,
    e.g. after a new export)"""
    bl_idname = "cs_chicken.clear_templates"
    bl_label = "Clear Model Cache"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = spawn.clear_templates()
        self.report({"INFO"}, f"{count} cached models removed")
        return {"FINISHED"}


_job = None  # running preview render (subprocess.Popen)


def preview_job_running():
    return _job is not None and _job.poll() is None


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {"VIEW_3D", "PREFERENCES"}:
                area.tag_redraw()


def _poll_job():
    global _job
    if preview_job_running():
        return 1.0
    code = _job.returncode if _job is not None else None
    _job = None
    registry.clear_previews()
    _redraw()
    if code:
        utils.log.warning("cs.chicken: preview render ended with code %s", code)
    return None


def missing_previews():
    """Complete chickens of the user library without a rendered preview."""
    folder = utils.user_library_dir()
    if not folder:
        return 0
    return sum(1 for c in registry.get_catalog()
               if c.complete and c.preview.startswith(folder) and not os.path.isfile(c.preview))


class CSCHICKEN_OT_render_previews(bpy.types.Operator):
    """Render preview images of the chicken library in the background (about one second
    per chicken); the list shows them once they are done"""
    bl_idname = "cs_chicken.render_previews"
    bl_label = "Render Previews"

    all: BoolProperty(name="All", default=False, description="Render every preview again, not only missing ones",
                      options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return bool(utils.user_library_dir()) and not preview_job_running()

    def execute(self, context):
        global _job
        from .. import preview_render
        try:
            _job = preview_render.start(utils.user_library_dir(), missing_only=not self.all)
        except OSError as exc:
            self.report({"ERROR"}, f"Could not start Blender for the previews: {exc}")
            return {"CANCELLED"}
        bpy.app.timers.register(_poll_job, first_interval=1.0)
        self.report({"INFO"}, "Rendering previews in the background")
        return {"FINISHED"}


class CSCHICKEN_OT_select_in_library(bpy.types.Operator):
    """Select the active chicken in the library list"""
    bl_idname = "cs_chicken.select_in_library"
    bl_label = "Show in Library"

    @classmethod
    def poll(cls, context):
        root = utils.active_chicken(context)
        return root is not None and registry.get(root.cs_chicken.chicken_id) is not None

    def execute(self, context):
        from .. import properties
        chicken_id = utils.active_chicken(context).cs_chicken.chicken_id
        state = context.window_manager.cs_chicken
        for i, item in enumerate(state.items):
            if item.chicken_id == chicken_id:
                state.index = i
                return {"FINISHED"}
        state.search = ""
        state.kind = "ALL"
        state.breed = "ALL"
        properties.rebuild_list(context.window_manager)
        state.index = next((i for i, it in enumerate(state.items) if it.chicken_id == chicken_id), state.index)
        return {"FINISHED"}


classes = (CSCHICKEN_OT_spawn, CSCHICKEN_OT_spawn_variants, CSCHICKEN_OT_remove, CSCHICKEN_OT_randomize,
           CSCHICKEN_OT_refresh_library, CSCHICKEN_OT_open_user_folder, CSCHICKEN_OT_clear_templates,
           CSCHICKEN_OT_render_previews, CSCHICKEN_OT_select_in_library)


def model_exists(chicken):
    return chicken is not None and os.path.isfile(chicken.model)
