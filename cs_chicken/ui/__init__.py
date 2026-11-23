# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Sidebar UI."""

import bpy

from . import panels


def register():
    for cls in panels.classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(panels.classes):
        bpy.utils.unregister_class(cls)
