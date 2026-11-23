# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Library logic without bpy: catalog, naming, appearance seeds, shader values."""

import os
import unittest

from cs_chicken.library import catalog as C
from cs_chicken.library import expr
from cs_chicken.library import shading as S

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "library")


class NamingTest(unittest.TestCase):
    def test_variant_name(self):
        self.assertEqual(C.variant_name("materials/models/chicken/chicken_catalan_black_with_red_head.vmat"),
                         "Black With Red Head")
        self.assertEqual(C.variant_name("materials\\models\\chicken\\chicken_polish_white_color.vmat"), "White")
        self.assertEqual(C.variant_name("egg_brown.vmat"), "Brown")
        self.assertEqual(C.variant_name("chicken.vmat"), "Chicken")

    def test_breed(self):
        self.assertEqual(C.breed_of("chicken_catalana_01"), "Catalana")
        self.assertEqual(C.breed_of("chicken_silkie_02"), "Silkie")
        self.assertEqual(C.breed_of("chicken_egg_01"), "")
        self.assertEqual(C.breed_of("chicken_chick_01"), "")
        self.assertEqual(C.breed_of(""), "")

    def test_display_name(self):
        self.assertEqual(C.display_name("Pet Chicken"), "Chicken")
        self.assertEqual(C.display_name("pet chick"), "chick")
        self.assertEqual(C.display_name("Pet"), "Pet")
        self.assertEqual(C.display_name("Chicken Egg"), "Chicken Egg")
        self.assertEqual(C.display_name("Petunia Hen"), "Petunia Hen")
        chicken = C.Chicken("x", C.display_name("Pet Chicken"), breed="Catalana", variant="Tan")
        self.assertEqual(chicken.label, "Chicken (Catalana) | Tan")

    def test_ids(self):
        self.assertEqual(C.make_id("Black / White Head"), "black_white_head")
        self.assertEqual(C.make_id("***"), "chicken")


class AppearanceTest(unittest.TestCase):
    def test_inputs_from_dynamic(self):
        dyn = {"g_fHueShift": "return lerp(-12,165,$egg_hue*$egg_hue);",
               "g_fBrightness": "return lerp(.8,1.2,$egg_brightness);"}
        self.assertEqual(C.dynamic_inputs(dyn), ["$egg_brightness", "$egg_hue"])
        self.assertEqual(C.dynamic_inputs({"x": "return ((;"}), [])

    def test_seed_values_deterministic(self):
        a = C.appearance_from_seed(42, ["$egg_hue", "$egg_brightness"])
        b = C.appearance_from_seed(42, ["$egg_hue", "$egg_brightness"])
        self.assertEqual(a, b)
        self.assertNotEqual(a["$egg_hue"], a["$egg_brightness"])
        self.assertNotEqual(a, C.appearance_from_seed(43, ["$egg_hue", "$egg_brightness"]))
        for v in a.values():
            self.assertTrue(0.0 <= v <= 1.0)
        self.assertEqual(C.appearance_from_seed(C.NEUTRAL_SEED, ["$a", "$b"]), {"$a": 0.5, "$b": 0.5})

    def test_evaluate_params(self):
        spec = C.MaterialSpec("k", C.CHARACTER_SHADER, params={"g_fHueShift": 0.0, "g_fBrightness": 1.0},
                              dynamic={"g_fHueShift": "return lerp(-12,165,$egg_hue*$egg_hue);",
                                       "g_fBrightness": "return ((;"})
        params = C.evaluate_params(spec, {"$egg_hue": 1.0})
        self.assertAlmostEqual(params["g_fHueShift"], 165.0)
        self.assertEqual(params["g_fBrightness"], 1.0, "broken expression keeps the static value")
        self.assertAlmostEqual(C.evaluate_params(spec, {"$egg_hue": 0.0})["g_fHueShift"], -12.0)
        # unknown input -> default 0.5
        self.assertAlmostEqual(C.evaluate_params(spec, {})["g_fHueShift"], -12 + 177 * 0.25)

    def test_original_material(self):
        spec = C.MaterialSpec("k", C.CHARACTER_SHADER, params={"g_fSaturation": 1.0},
                              dynamic={"g_fSaturation": "return lerp(.4,1,$ChickenSaturation);"})
        self.assertEqual(C.evaluate_params(spec, None)["g_fSaturation"], 1.0, "seed 0: authored value")
        self.assertAlmostEqual(C.evaluate_params(spec, {})["g_fSaturation"], 0.7)
        self.assertEqual(S.node_values(spec, None)[(S.NODE_MAIN, "Saturation")], 1.0)

    def test_expr_ternary(self):
        self.assertEqual(expr.evaluate("return exists($a) ? 2 : 3;", {"$a": 1}), 2)
        self.assertEqual(expr.evaluate("return exists($a) ? 2 : 3;", {}), 3)


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.cat, self.errors = C.load([FIXTURES])

    def test_load(self):
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.cat), 4)
        self.assertEqual(self.cat.breeds(), ["Demo"])
        hen = self.cat.get("demo_hen_black")
        self.assertEqual(hen.label, "Demo Hen | Black")
        self.assertTrue(hen.complete)
        self.assertEqual(set(hen.materials), {"hen_body_white", "hen_comb"})
        self.assertTrue(os.path.isabs(hen.model))
        self.assertTrue(all(os.path.isabs(p) for p in hen.materials["hen_comb"].textures.values()))

    def test_age_scale(self):
        hen = self.cat.get("demo_hen_white")
        self.assertEqual(hen.age_scale, (0.3, 0.5))
        self.assertAlmostEqual(hen.scale_at(0.0), 0.3)
        self.assertAlmostEqual(hen.scale_at(1.0), 0.5)
        self.assertAlmostEqual(hen.scale_at(C.DEFAULT_AGE), 0.4)
        self.assertAlmostEqual(hen.scale_at(5.0), 0.5, msg="clamped")
        egg = self.cat.get("demo_egg")
        self.assertIsNone(egg.age_scale)
        self.assertEqual(egg.scale_at(0.0), 1.0)
        self.assertIsNone(C.Chicken("x", "x", age_scale=["a", 1]).age_scale)
        self.assertIsNone(C.Chicken("x", "x", age_scale=[0, 1]).age_scale)

    def test_preview(self):
        import tempfile
        hen = self.cat.get("demo_hen_black")
        self.assertEqual(hen.preview, os.path.join(FIXTURES, C.PREVIEW_DIR, "demo_hen_black.png"))
        self.assertEqual(hen.preview_image, "", "no preview rendered, no icon")
        with tempfile.TemporaryDirectory() as tmp:
            icon = os.path.join(tmp, "icon.png")
            open(icon, "wb").close()
            hen.icon = icon
            self.assertEqual(hen.preview_image, icon, "falls back to the game icon")
            hen.preview = os.path.join(tmp, "preview.png")
            open(hen.preview, "wb").close()
            self.assertEqual(hen.preview_image, hen.preview, "rendered preview first")

    def test_inputs_and_missing(self):
        self.assertEqual(self.cat.get("demo_egg").inputs, ["$egg_brightness", "$egg_hue"])
        self.assertEqual(self.cat.get("demo_hen_white").inputs, [])
        self.assertFalse(self.cat.get("demo_missing").complete)

    def test_search(self):
        egg = self.cat.get("demo_egg")
        self.assertTrue(egg.matches("egg"))
        self.assertTrue(egg.matches("chicken_egg"))
        self.assertFalse(egg.matches("hen"))
        self.assertTrue(self.cat.get("demo_hen_white").matches("demo white"))

    def test_broken_catalog(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, C.CATALOG_FILE), "w") as fh:
                fh.write("{broken")
            cat, errors = C.load([tmp, FIXTURES])
            self.assertEqual(len(errors), 1)
            self.assertEqual(len(cat), 4)


class ShadingTest(unittest.TestCase):
    def test_node_values(self):
        spec = C.MaterialSpec("k", C.CHARACTER_SHADER,
                              params={"F_TINT_MASK": 1, "g_fBrightness": 1.2, "g_vColorTint": [1, 0.5, 0.25, 0],
                                      "g_vDetailTexCoordScale": [2, 3], "g_flDetailTexCoordRotation": 45},
                              dynamic={"g_fHueShift": "return lerp(0,100,$egg_hue);"},
                              constants={"TextureRoughness": [0.7, 0.7, 0.7, 1.0]})
        values = S.node_values(spec, {"$egg_hue": 0.5})
        self.assertEqual(values[(S.NODE_MAIN, S.FLAG_INPUTS["F_TINT_MASK"])], 1.0)
        self.assertEqual(values[(S.NODE_MAIN, S.FLAG_INPUTS["F_IRIDESCENCE"])], 0.0)
        self.assertAlmostEqual(values[(S.NODE_MAIN, S.FLOAT_INPUTS["g_fHueShift"])], 50.0)
        self.assertAlmostEqual(values[(S.NODE_MAIN, S.FLOAT_INPUTS["g_fBrightness"])], 1.2)
        self.assertEqual(values[(S.NODE_MAIN, S.COLOR_INPUTS["g_vColorTint"])], (1.0, 0.5, 0.25, 1.0))
        self.assertEqual(values[(S.NODE_DETAIL_UV, "Scale Y")], 3.0)
        self.assertEqual(values[(S.NODE_DETAIL_UV, "Rotation")], 45.0)
        self.assertIn((S.NODE_MAIN, S.CONSTANT_INPUTS["TextureRoughness"][0]), values)
        self.assertEqual(values[(S.NODE_MAIN, S.FLAG_INPUTS["F_DO_NOT_CAST_SHADOWS"])], 0.0)
        fur = C.MaterialSpec("f", C.CHARACTER_SHADER, params={"F_DO_NOT_CAST_SHADOWS": 1, "F_ALPHA_TEST": 1})
        fur_values = S.node_values(fur)
        self.assertEqual(fur_values[(S.NODE_MAIN, "No Shadows")], 1.0)
        self.assertEqual(fur_values[(S.NODE_MAIN, "Use Alpha Clip")], 1.0)

    def test_constant_ignored_with_texture(self):
        spec = C.MaterialSpec("k", C.CHARACTER_SHADER, textures={"TextureRoughness": "x.png"},
                              constants={"TextureRoughness": [0.7, 0.7, 0.7, 1.0]})
        self.assertNotIn((S.NODE_MAIN, S.CONSTANT_INPUTS["TextureRoughness"][0]), S.node_values(spec))

    def test_parse_constant(self):
        self.assertEqual(S.parse_constant("[0.5 0.5 0.5 1.0]"), [0.5, 0.5, 0.5, 1.0])
        self.assertIsNone(S.parse_constant("materials/x.png"))

    def test_texture_roles(self):
        self.assertIsNotNone(S.texture_role("TextureColor"))
        self.assertIsNone(S.texture_role("TextureFoo"))


if __name__ == "__main__":
    unittest.main()
