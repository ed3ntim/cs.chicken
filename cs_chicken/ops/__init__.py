# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Operators."""

import bpy

from . import chicken_ops, spawn  # noqa: F401


def register():
    for cls in chicken_ops.classes:
        bpy.utils.register_class(cls)


def unregister():
    if bpy.app.timers.is_registered(chicken_ops._poll_job):
        bpy.app.timers.unregister(chicken_ops._poll_job)
    for cls in reversed(chicken_ops.classes):
        bpy.utils.unregister_class(cls)
