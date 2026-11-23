# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""tools/export_cs2_chickens.py: parsers and library building on synthetic
data (no CS2 or Source2Viewer needed)."""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "library")


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_cs2_chickens",
                                                  os.path.join(ROOT, "tools", "export_cs2_chickens.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


X = _load_exporter()

VMDL = '''<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} -->
{
	rootNode =
	{
		_class = "RootNode"
		children =
		[
			{
				_class = "MaterialGroupList"
				children =
				[
					{
						_class = "DefaultMaterialGroup"
						name = "default"
						remaps = [ ]
					},
					{
						_class = "MaterialGroup"
						name = "black"
						remaps =
						[
							{
								from = "materials/demo/hen_body_white.vmat"
								to = "materials/demo/hen_body_black.vmat"
							},
						]
					},
					{
						_class = "MaterialGroup"
						name = "black_copy"
						remaps =
						[
							{
								from = "materials/demo/hen_body_white.vmat"
								to = "materials/demo/hen_body_black.vmat"
							},
						]
					},
				]
			},
			{
				_class = "ScaleSetList"
				children =
				[
					{
						_class = "ScaleSet"
						name = "age_min"
						root_offset = [ 0.0, 0.0, 0.0 ]
						scales =
						[
							{
								bone = "root_motion"
								scale = 0.3
							},
						]
					},
					{
						_class = "ScaleSet"
						name = "age_max"
						root_offset = [ 0.0, 0.0, 0.0 ]
						scales =
						[
							{
								bone = "root_motion"
								scale = 0.5
							},
						]
					},
				]
			},
			{
				_class = "AnimationList"
				children = [ ]
			},
			{
				_class = "ModelModifierList"
				children =
				[
					{
						_class = "ModelModifier_AnimGraph2"
						filename = "animation/skeletons/demo/demo_hen.vnmskel"
					},
				]
			},
		]
	}
}
'''

VMAT = '''// THIS FILE IS AUTO-GENERATED

Layer0
{
	shader "csgo_character.vfx"

	//---- Color ----
	F_TINT_MASK 1
	g_fHueShift "0.000"
	g_vColorTint "[1.000000 1.000000 1.000000 0.000000]"
	TextureColor "materials/demo/hen_white_color.png"
	TextureRoughness "[0.730000 0.730000 0.730000 0.000000]"
	TextureNormal "materials/default/default_normal.tga"

	DynamicParams
	{
		g_fHueShift "return lerp(-12,165,$egg_hue*$egg_hue);"
	}

	"Compiled Textures"
	{
		g_tColor "materials/demo/hen_white_color_png_abc.vtex"
	}
}
'''

ITEMS_GAME = '''"items_game"
{
	"items"
	{
		"4970"
		{
			"name"		"Chicken Egg"
			"item_class"	"chicken_egg"
			"image_inventory"	"econ/pets/chicken_egg"
		}
	}
	"pet_definitions"
	{
		"1"
		{
			"name"	"chicken_egg_01"
			"loc_name"	"#Pet_Egg"
			"pedestal_display_model"	"models/chicken/egg.vmdl"
		}
		"3"
		{
			"name"	"chicken_demo_01"
			"loc_name"	"#Pet_Demo"
			"pedestal_display_model"	"models\\\\chicken\\\\demo_hen.vmdl"
		}
	}
}
'''


class ParserTest(unittest.TestCase):
    def test_material_groups(self):
        groups = X.parse_material_groups(VMDL)
        self.assertEqual([g[0] for g in groups], ["default", "black", "black_copy"])
        self.assertEqual(groups[0][1], {})
        self.assertEqual(groups[1][1], {"materials/demo/hen_body_white.vmat": "materials/demo/hen_body_black.vmat"})
        self.assertEqual(X.parse_skeleton(VMDL), "animation/skeletons/demo/demo_hen.vnmskel")

    def test_age_scale(self):
        self.assertEqual(X.parse_age_scale(VMDL), [0.3, 0.5])
        self.assertIsNone(X.parse_age_scale(VMDL.replace('"age_max"', '"other"')))
        self.assertIsNone(X.parse_age_scale(""))

    def test_variants_dedup(self):
        slots = {"hen_body_white": "materials/demo/hen_body_white.vmat", "hen_comb": "materials/demo/hen_comb.vmat"}
        variants = X.variants_of(slots, X.parse_material_groups(VMDL))
        self.assertEqual(len(variants), 2, "duplicate group dropped")
        self.assertEqual(variants[0][0], "materials/demo/hen_body_white.vmat")
        self.assertEqual(variants[1][0], "materials/demo/hen_body_black.vmat")
        self.assertEqual(variants[1][1]["hen_comb"], "materials/demo/hen_comb.vmat")
        self.assertEqual(len(X.variants_of(slots, [])), 1)

    def test_vmat(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.vmat")
            with open(path, "w") as fh:
                fh.write(VMAT)
            shader, params, dynamic, textures, constants, compiled = X.parse_vmat(path)
        self.assertEqual(shader, "csgo_character.vfx")
        self.assertEqual(params["F_TINT_MASK"], 1)
        self.assertEqual(params["g_vColorTint"], [1.0, 1.0, 1.0, 0.0])
        self.assertEqual(dynamic, {"g_fHueShift": "return lerp(-12,165,$egg_hue*$egg_hue);"})
        self.assertEqual(textures["TextureColor"], "materials/demo/hen_white_color.png")
        self.assertEqual(constants["TextureRoughness"], [0.73, 0.73, 0.73, 0.0])
        self.assertIn("g_tColor", compiled)

    def test_pets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "items_game.txt")
            with open(path, "w") as fh:
                fh.write(ITEMS_GAME)
            pets, images = X.load_pets(path)
        self.assertEqual(sorted(pets), ["1", "3"])
        self.assertEqual(images, {"chicken_egg": "econ/pets/chicken_egg"})
        entries = X.model_entries(pets)
        kinds = {e[0]: e[2] for e in entries}
        self.assertEqual(kinds["pet1"], "EGG")
        self.assertEqual(kinds["pet3"], "CHICKEN")
        self.assertEqual(entries[1][1], "models/chicken/demo_hen.vmdl")
        self.assertEqual(len(entries), 2 + len(X.EXTRA_MODELS))


class BuildLibraryTest(unittest.TestCase):
    """build_library on a fake raw export made from the fixtures."""

    def test_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "lib")
            raw = os.path.join(out, X.RAW_DIR)
            vmdl_raw = os.path.join(raw, X.VMDL_DIR)
            os.makedirs(os.path.join(raw, "models", "chicken"))
            os.makedirs(os.path.join(vmdl_raw, "models", "chicken"))
            os.makedirs(os.path.join(raw, "materials", "demo"))
            shutil.copy(os.path.join(FIXTURES, "models", "demo_hen.glb"),
                        os.path.join(raw, "models", "chicken", "demo_hen.glb"))
            with open(os.path.join(vmdl_raw, "models", "chicken", "demo_hen.vmdl"), "w") as fh:
                fh.write(VMDL)
            for name in ("hen_body_white", "hen_body_black", "hen_comb"):
                with open(os.path.join(raw, "materials", "demo", name + ".vmat"), "w") as fh:
                    fh.write(VMAT.replace("hen_white_color", name))
                shutil.copy(os.path.join(FIXTURES, "textures", "demo_comb.png"),
                            os.path.join(raw, "materials", "demo", name + ".png"))
            # the glb has no CS2 material extras: patch slots via a stub
            slots = {"hen_body_white": "materials/demo/hen_body_white.vmat",
                     "hen_comb": "materials/demo/hen_comb.vmat"}
            old = X.model_slots
            X.model_slots = lambda _path: dict(slots)
            try:
                pets = {"3": {"name": "chicken_demo_01", "loc_name": "#Pet_Demo",
                              "pedestal_display_model": "models/chicken/demo_hen.vmdl"}}
                chickens, warnings = X.build_library(out, raw, vmdl_raw, pets, {"pet_demo": "Pet Chicken"}, {})
            finally:
                X.model_slots = old
            with open(os.path.join(out, "catalog.json"), encoding="utf-8") as fh:
                catalog = json.load(fh)
            self.assertEqual(len(chickens), 2)
            ids = [c["id"] for c in chickens]
            self.assertEqual(ids, ["cs2_pet3_chicken_demo_01_hen_body_white", "cs2_pet3_chicken_demo_01_hen_body_black"])
            self.assertEqual(chickens[0]["name"], "Pet Chicken")
            self.assertEqual(chickens[0]["breed"], "Demo")
            self.assertEqual(chickens[1]["variant"], "Hen Body Black")
            self.assertEqual(chickens[0]["skeleton"], "animation/skeletons/demo/demo_hen.vnmskel")
            self.assertEqual(chickens[0]["age_scale"], [0.3, 0.5])
            self.assertTrue(os.path.isfile(os.path.join(out, chickens[0]["model"])))
            self.assertIn("materials/demo/hen_body_black.vmat", catalog["materials"])
            mat = catalog["materials"]["materials/demo/hen_body_black.vmat"]
            self.assertTrue(mat["textures"]["TextureColor"].startswith("textures/"))
            self.assertTrue(os.path.isfile(os.path.join(out, mat["textures"]["TextureColor"])))
            self.assertNotIn("TextureNormal", mat["textures"], "default textures skipped")
            # only the extra models (hatching egg, ...) are missing in this fake export
            self.assertEqual([w for w in warnings if not w.startswith("model not exported")], [])
            self.assertEqual(len(warnings), len(X.EXTRA_MODELS))


if __name__ == "__main__":
    unittest.main()
