# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Add-on preferences: uninstall button, host mode (cs.blend)."""

import os
import sys
import tempfile
import types
import unittest

import bpy

from cs_chicken import preferences as P
from cs_chicken import utils

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class UninstallTest(unittest.TestCase):
    def test_legacy_location(self):
        self.assertEqual(P.install_location(bpy.context), ("LEGACY", None, "cs_chicken"))

    def test_operator_available(self):
        self.assertTrue(hasattr(bpy.ops.cs_chicken, "uninstall"))
        self.assertTrue(bpy.ops.cs_chicken.uninstall.poll())

    def test_extension_location(self):
        repos = bpy.context.preferences.extensions.repos
        index = next(i for i, r in enumerate(repos) if r.module == "user_default")
        old = utils.ADDON_ID
        try:
            utils.ADDON_ID = "bl_ext.user_default.cs_chicken"
            self.assertEqual(P.install_location(bpy.context), ("EXTENSION", index, "cs_chicken"))
            utils.ADDON_ID = "bl_ext.no_such_repo.cs_chicken"
            self.assertIsNone(P.install_location(bpy.context))
        finally:
            utils.ADDON_ID = old

    def test_settings_standalone(self):
        self.assertIsNotNone(utils.prefs())
        self.assertEqual(utils.prefs(), bpy.context.preferences.addons[utils.ADDON_ID].preferences.settings)


class FakeHost:
    """Minimal cs.blend host: one settings instance per module on the
    window manager, user folders in a temp dir."""

    def __init__(self, folder):
        self.folder = folder

    def add(self, module):
        bpy.types.WindowManager.fake_host_cs_chicken = bpy.props.PointerProperty(type=module.SETTINGS)

    def settings(self, module_id):
        if module_id != "cs_chicken":
            return None
        return getattr(bpy.context.window_manager, "fake_host_cs_chicken", None)

    def user_path(self, module_id, sub="", create=True):
        path = os.path.join(self.folder, module_id, sub)
        if create:
            os.makedirs(path, exist_ok=True)
        return path


class HostModeTest(unittest.TestCase):
    """The package as sub-module of a host package (fakehost.modules), with
    the standalone add-on disabled meanwhile (same operator names)."""

    def setUp(self):
        import addon_utils
        addon_utils.disable("cs_chicken", default_set=True)
        pkg = types.ModuleType("fakehost")
        pkg.__path__ = []
        mods = types.ModuleType("fakehost.modules")
        mods.__path__ = [ROOT]
        sys.modules["fakehost"], sys.modules["fakehost.modules"] = pkg, mods
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        import addon_utils
        for key in [k for k in sys.modules if k == "fakehost" or k.startswith("fakehost.")]:
            del sys.modules[key]
        if hasattr(bpy.types.WindowManager, "fake_host_cs_chicken"):
            del bpy.types.WindowManager.fake_host_cs_chicken
        addon_utils.enable("cs_chicken", default_set=True)
        # enable() may import the package afresh: the fixtures again
        sys.modules["cs_chicken.utils"].CORE_LIBRARY_DIR = utils.CORE_LIBRARY_DIR
        sys.modules["cs_chicken.library.registry"].refresh()
        self.tmp.cleanup()

    def test_register_twice_under_a_host(self):
        import importlib
        mod = importlib.import_module("fakehost.modules.cs_chicken")
        hutils = importlib.import_module("fakehost.modules.cs_chicken.utils")
        hapi = importlib.import_module("fakehost.modules.cs_chicken.api")
        self.assertEqual(hutils.ADDON_ID, "fakehost.modules.cs_chicken")
        self.assertEqual(mod.MODULE_ID, "cs_chicken")
        for _ in range(2):
            host = FakeHost(self.tmp.name)
            mod.register(host)
            host.add(mod)
            try:
                bpy.ops.cs_chicken.spawn.get_rna_type()
                with self.assertRaises(KeyError):  # no uninstall button under a host
                    bpy.ops.cs_chicken.uninstall.get_rna_type()
                self.assertIsNone(bpy.context.preferences.addons.get(hutils.ADDON_ID))
                settings = hutils.prefs()
                self.assertEqual(settings, bpy.context.window_manager.fake_host_cs_chicken)
                settings["user_path"] = self.tmp.name
                self.assertEqual(hutils.user_library_dir(), self.tmp.name)
                folder = hutils.user_path("cache")
                self.assertTrue(os.path.isdir(folder))
                self.assertTrue(folder.startswith(self.tmp.name))
                self.assertTrue(callable(mod.draw_prefs))
                self.assertGreaterEqual(hapi.API_VERSION, 1)
            finally:
                del bpy.types.WindowManager.fake_host_cs_chicken
                mod.unregister()
            self.assertIsNone(hutils.get_host())
            with self.assertRaises(KeyError):
                bpy.ops.cs_chicken.spawn.get_rna_type()


if __name__ == "__main__":
    unittest.main()
