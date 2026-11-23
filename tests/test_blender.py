# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Spawning, variants, appearance, removal and the partner API in Blender."""

import unittest

import bpy

from cs_chicken import api, utils
from cs_chicken.library import registry
from cs_chicken.nodes import groups, material as M
from cs_chicken.ops import spawn


def _clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    spawn.clear_templates()
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


class SpawnTest(unittest.TestCase):
    def setUp(self):
        registry.refresh()
        _clear_scene()
        self.ctx = bpy.context

    def test_library_loaded(self):
        self.assertEqual(len(registry.get_catalog()), 4)
        self.assertEqual(registry.view(kind="EGG"), ["demo_egg"])
        self.assertEqual(registry.view(include_incomplete=False, search="demo"),
                         ["demo_hen_white", "demo_hen_black", "demo_egg"])

    def test_spawn_rigged(self):
        root, warnings = spawn.create_chicken(self.ctx, registry.get("demo_hen_white"), location=(1, 2, 0))
        self.assertEqual(warnings, [])
        self.assertEqual(root.type, "ARMATURE")
        self.assertEqual(tuple(root.location), (1, 2, 0))
        self.assertEqual(root.name, "Demo Hen | White")
        self.assertEqual(sorted(b.name for b in root.data.bones), ["head_0", "neck_0", "pelvis", "spine_0"])
        parts = utils.chicken_parts(root)
        self.assertEqual(len(parts), 1)
        mod = next(m for m in parts[0].modifiers if m.type == "ARMATURE")
        self.assertIs(mod.object, root)
        self.assertIn(root.name, utils.chicken_collection(self.ctx).objects)
        mats = [m.get(utils.PROP_MATERIAL_KEY) for m in parts[0].data.materials]
        self.assertEqual(sorted(mats), ["materials/demo/hen_body_white.vmat", "materials/demo/hen_comb.vmat"])
        main = M.main_node(parts[0].data.materials[0])
        self.assertEqual(main.node_tree.name, groups.CHARACTER_GROUP)

    def test_age_scale(self):
        root, _ = spawn.create_chicken(self.ctx, registry.get("demo_hen_white"), scale=2.0)
        self.assertAlmostEqual(root.scale.x, 2.0 * 0.4, places=5)
        self.assertAlmostEqual(root.cs_chicken.age, 0.5)
        root.cs_chicken.age = 1.0
        self.assertAlmostEqual(root.scale.z, 2.0 * 0.5, places=5, msg="user scale kept")
        self.assertTrue(api.set_age(root, 0.0))
        self.assertAlmostEqual(root.scale.y, 2.0 * 0.3, places=5)
        young, _ = spawn.create_chicken(self.ctx, registry.get("demo_hen_white"), age=1.0)
        self.assertAlmostEqual(young.scale.x, 0.5, places=5)
        egg, _ = spawn.create_chicken(self.ctx, registry.get("demo_egg"))
        self.assertEqual(tuple(egg.scale), (1.0, 1.0, 1.0))
        self.assertFalse(api.set_age(egg, 1.0))
        self.assertEqual(tuple(egg.scale), (1.0, 1.0, 1.0))

    def test_transparent_bounces(self):
        cycles = self.ctx.scene.cycles
        cycles.transparent_max_bounces = 8
        self.assertTrue(spawn.ensure_transparent_bounces(self.ctx.scene))
        self.assertEqual(cycles.transparent_max_bounces, spawn.MIN_TRANSPARENT_BOUNCES)
        cycles.transparent_max_bounces = 500
        self.assertFalse(spawn.ensure_transparent_bounces(self.ctx.scene), "never lowered")
        self.assertEqual(cycles.transparent_max_bounces, 500)

    def test_fur_material(self):
        from cs_chicken.library import shading as S
        main_tree = groups.ensure_group("CHARACTER")
        self.assertEqual(main_tree.get(groups.VERSION_KEY), groups.GROUP_VERSION)
        names = {s.name for s in main_tree.interface.items_tree if getattr(s, "in_out", "") == "INPUT"}
        self.assertTrue({"No Shadows", "Alpha Softness", "Use Alpha Clip", "Keep Backface Normals", "Card Translucency",
                         "Shadow Bias"} <= names)
        path = next(n for n in main_tree.nodes if n.bl_idname == "ShaderNodeLightPath")
        self.assertTrue(path.outputs["Ray Length"].is_linked, "shadow bias")
        self.assertTrue(path.outputs["Is Shadow Ray"].is_linked)
        self.assertIn("No Shadows", S.FLAG_INPUTS.values())
        types = {n.bl_idname for n in main_tree.nodes}
        self.assertTrue({"ShaderNodeBsdfTranslucent", "ShaderNodeAddShader", "ShaderNodeValToRGB",
                         "ShaderNodeLayerWeight"} <= types)
        ramp = next(n for n in main_tree.nodes if n.bl_idname == "ShaderNodeValToRGB")
        self.assertEqual(len(ramp.color_ramp.elements), len(groups.IRIDESCENCE_RAMP))
        # roughness from AnisoGloss uses R and G
        sep = next(n for n in main_tree.nodes if n.bl_idname == "ShaderNodeSeparateColor")
        self.assertTrue(sep.outputs[0].is_linked and sep.outputs[1].is_linked)
        # separate alpha texture (Source2Viewer *_trans.png) feeds Alpha, before or after the color
        import os
        from cs_chicken.library import catalog as C
        folder = os.path.normpath(os.path.join(os.path.dirname(registry.get("demo_egg").model), "..", "textures"))
        files = {"TextureColor": os.path.join(folder, "demo_comb.png"),
                 "TextureTranslucency": os.path.join(folder, "demo_tint.png")}
        for order in (("TextureColor", "TextureTranslucency"), ("TextureTranslucency", "TextureColor")):
            spec = C.MaterialSpec("fur", C.CHARACTER_SHADER, params={"F_ALPHA_TEST": 1},
                                  textures={k: files[k] for k in order})
            mat, warnings = M.build_material(spec, "fur")
            self.assertEqual(warnings, [])
            link = M.main_node(mat).inputs["Alpha"].links[0]
            self.assertEqual(link.from_socket.name, "Color", order)
            self.assertEqual(link.from_node.image.colorspace_settings.name, "Non-Color")

    def test_two_chickens_own_rigs(self):
        a, _ = spawn.create_chicken(self.ctx, registry.get("demo_hen_white"))
        b, _ = spawn.create_chicken(self.ctx, registry.get("demo_hen_white"))
        self.assertIsNot(a.data, b.data)
        mod_b = next(m for m in utils.chicken_parts(b)[0].modifiers if m.type == "ARMATURE")
        self.assertIs(mod_b.object, b)
        # Shared materials: no appearance inputs
        self.assertEqual(set(utils.chicken_parts(a)[0].data.materials),
                         set(utils.chicken_parts(b)[0].data.materials))
        templates = [c for c in bpy.data.collections if utils.PROP_TEMPLATE in c]
        self.assertEqual(len(templates), 1, "model imported once")

    def test_variant_switch(self):
        root, _ = spawn.create_chicken(self.ctx, registry.get("demo_hen_white"))
        self.assertTrue(spawn.set_variant(root, "demo_hen_black"))
        part = utils.chicken_parts(root)[0]
        self.assertIn("materials/demo/hen_body_black.vmat",
                      [m.get(utils.PROP_MATERIAL_KEY) for m in part.data.materials])
        self.assertEqual(root.name, "Demo Hen | Black")
        self.assertEqual(root.cs_chicken.variant, "demo_hen_black")
        self.assertFalse(spawn.set_variant(root, "demo_egg"), "other model")
        root.cs_chicken.variant = "demo_hen_white"
        self.assertEqual(root.cs_chicken.chicken_id, "demo_hen_white")

    def test_egg_appearance(self):
        root, warnings = spawn.create_chicken(self.ctx, registry.get("demo_egg"), seed=7)
        self.assertEqual(warnings, [])
        self.assertEqual(root.type, "EMPTY")
        state = root.cs_chicken
        self.assertEqual(sorted(i.name for i in state.inputs), ["$egg_brightness", "$egg_hue"])
        mat = utils.chicken_parts(root)[0].data.materials[0]
        self.assertEqual(mat.get(utils.PROP_OWNER), root.name)
        hue = M.main_node(mat).inputs["Hue Shift"]
        for item in state.inputs:
            if item.name == "$egg_hue":
                item.value = 1.0
        self.assertAlmostEqual(hue.default_value, 165.0, places=3)
        for item in state.inputs:
            if item.name == "$egg_hue":
                item.value = 0.0
        self.assertAlmostEqual(hue.default_value, -12.0, places=3)
        # second egg gets its own material
        other, _ = spawn.create_chicken(self.ctx, registry.get("demo_egg"), seed=8)
        self.assertIsNot(utils.chicken_parts(other)[0].data.materials[0], mat)

    def test_seed_zero_is_original(self):
        root, _ = spawn.create_chicken(self.ctx, registry.get("demo_egg"), seed=0)
        hue = M.main_node(utils.chicken_parts(root)[0].data.materials[0]).inputs["Hue Shift"]
        static = registry.get("demo_egg").materials["egg_shell"].params.get("g_fHueShift", 0.0)
        self.assertAlmostEqual(hue.default_value, static, places=4)
        self.assertIsNone(spawn.appearance_env(root))
        root.cs_chicken.seed = 3
        self.assertIsNotNone(spawn.appearance_env(root))
        self.assertNotAlmostEqual(hue.default_value, static, places=2)

    def test_reseed(self):
        root, _ = spawn.create_chicken(self.ctx, registry.get("demo_egg"), seed=1)
        before = {i.name: i.value for i in root.cs_chicken.inputs}
        root.cs_chicken.seed = 2
        after = {i.name: i.value for i in root.cs_chicken.inputs}
        self.assertNotEqual(before, after)

    def test_remove(self):
        root, _ = spawn.create_chicken(self.ctx, registry.get("demo_egg"))
        mat = utils.chicken_parts(root)[0].data.materials[0]
        mat_name = mat.name
        spawn.delete_chicken(root)
        self.assertFalse([o for o in bpy.data.objects if utils.is_chicken(o)])
        self.assertNotIn(mat_name, bpy.data.materials, "own material removed")

    def test_operators(self):
        wm = self.ctx.window_manager.cs_chicken
        from cs_chicken import properties
        properties.rebuild_list(self.ctx.window_manager)
        wm.index = [i.chicken_id for i in wm.items].index("demo_hen_black")
        self.assertEqual(bpy.ops.cs_chicken.spawn(), {"FINISHED"})
        root = self.ctx.view_layer.objects.active
        self.assertEqual(root.cs_chicken.chicken_id, "demo_hen_black")
        self.assertEqual(bpy.ops.cs_chicken.spawn_variants(), {"FINISHED"})
        self.assertEqual(len([o for o in bpy.data.objects if utils.is_chicken(o)]), 3)
        self.assertEqual(bpy.ops.cs_chicken.remove(all_selected=True), {"FINISHED"})
        self.assertEqual(len([o for o in bpy.data.objects if utils.is_chicken(o)]), 1)
        self.assertTrue(hasattr(bpy.ops.cs_chicken, "uninstall"))


    def test_select_in_library(self):
        from cs_chicken import properties
        wm = self.ctx.window_manager.cs_chicken
        root, _w = spawn.create_chicken(self.ctx, registry.get("demo_hen_white"), seed=0)
        self.ctx.view_layer.objects.active = root
        wm.search = "egg"  # filters the hen out
        properties.rebuild_list(self.ctx.window_manager)
        self.assertEqual(bpy.ops.cs_chicken.select_in_library(), {"FINISHED"})
        self.assertEqual(wm.search, "")
        self.assertEqual(wm.items[wm.index].chicken_id, "demo_hen_white")

    def test_ui_classes(self):
        self.assertTrue(hasattr(bpy.types, "CSCHICKEN_PT_placement"))
        self.assertFalse(hasattr(bpy.types, "CSCHICKEN_PT_spawn"))
        # no user library in the tests: nothing to render previews for
        self.assertFalse(bpy.ops.cs_chicken.render_previews.poll())


class PreviewTest(unittest.TestCase):
    def test_render_previews(self):
        import os
        import tempfile
        from cs_chicken import preview_render
        _clear_scene()
        library = registry.get_catalog().sources[0]
        complete = [c.id for c in registry.get_catalog() if c.complete]
        with tempfile.TemporaryDirectory() as tmp:
            count = preview_render.render_all(library, out_dir=tmp, size=24, log=lambda _t: None)
            self.assertEqual(count, len(complete))
            self.assertEqual(sorted(os.listdir(tmp)), sorted(f"{cid}.png" for cid in complete))
            self.assertFalse([o for o in bpy.data.objects if utils.is_chicken(o)], "chickens removed")
            self.assertEqual(preview_render.render_all(library, out_dir=tmp, size=24, log=lambda _t: None), 0,
                             "only missing previews")
            hen = registry.get("demo_hen_white")
            hen.preview = os.path.join(tmp, "demo_hen_white.png")
            self.assertEqual(hen.preview_image, hen.preview)
            registry.preview_icon(hen)  # icon ids stay 0 in background mode, must not raise
            self.assertIn(hen.id, registry._previews)
        registry.refresh()
        cmd = preview_render.command("lib", missing_only=False, blender="blender")
        self.assertEqual(cmd[:2], ["blender", "-b"])
        self.assertIn("--all", cmd)
        self.assertEqual(cmd[cmd.index("--") + 1], "lib")


class ApiTest(unittest.TestCase):
    def setUp(self):
        registry.refresh()
        _clear_scene()

    def test_version_and_spawn(self):
        self.assertGreaterEqual(api.API_VERSION, 1)
        self.assertIn("demo_egg", api.catalog_ids("EGG"))
        seen = []
        api.register_spawn_handler(seen.append)
        try:
            root = api.spawn("demo_hen_white", location=(0, 0, 1))
        finally:
            api.unregister_spawn_handler(seen.append)
        self.assertEqual(seen, [root])
        self.assertTrue(api.is_chicken(root))
        self.assertIs(api.chicken_root(api.parts(root)[0]), root)
        self.assertIs(api.armature(root), root)
        self.assertEqual(api.kind(root), "CHICKEN")
        self.assertEqual(api.info(root)["variant"], "White")
        self.assertEqual(api.skeleton(root), "animation/skeletons/demo/demo_hen.vnmskel")
        self.assertEqual(len(api.bone_names(root)), 4)
        self.assertEqual(api.bone_heuristic(root), spawn.BONE_HEURISTIC)
        root.pose.bones["head_0"].location = (0, 0, 1)
        api.rest_pose(root)
        self.assertEqual(tuple(root.pose.bones["head_0"].location), (0, 0, 0))
        self.assertIn(root, api.chickens())
        api.remove(root)
        self.assertEqual(api.chickens(), [])

    def test_providers(self):
        class Provider:
            label = "Test Anim"

            def poll(self, chicken):
                return api.kind(chicken) == "CHICKEN"

            def draw(self, layout, context, chicken):
                pass

        p = Provider()
        api.register_provider("animation", p)
        try:
            hen = api.spawn("demo_hen_white")
            egg = api.spawn("demo_egg")
            self.assertEqual(api.providers("animation", hen), [p])
            self.assertEqual(api.providers("animation", egg), [])
        finally:
            api.unregister_provider("animation", p)
        self.assertEqual(api.providers("animation"), [])


if __name__ == "__main__":
    unittest.main()
