# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Chicken library: catalog (pure Python), glTF reader, shader table, registry."""

from . import catalog, expr, gltf, registry, shading  # noqa: F401


def register():
    registry.register()
    registry.refresh()


def unregister():
    registry.unregister()
