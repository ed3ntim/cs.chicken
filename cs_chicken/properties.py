# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Property groups.

* ``WindowManager.cs_chicken``  library browser: filters, list, index
* ``Scene.cs_chicken``          spawn options
* ``Object.cs_chicken``         per chicken (on the root): variant, seed and
                                the appearance inputs ($egg_hue ...)
"""

import zlib

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)

from . import utils
from .library import catalog as C
from .library import registry


def _stable(text):
    """Stable enum number: Blender stores the number, not the identifier."""
    return zlib.crc32(text.encode("utf-8")) & 0x7FFFFFFF


# ---------------------------------------------------------------------------
# Library browser
# ---------------------------------------------------------------------------

class CSCHICKEN_PG_item(bpy.types.PropertyGroup):
    chicken_id: StringProperty()
    label: StringProperty()
    kind: StringProperty()
    complete: BoolProperty(default=True)


def _kind_items(self, context):
    return [("ALL", "All", "Every kind", 0)] + [
        (k, C.KIND_LABELS[k], "", i + 1) for i, k in enumerate(C.KINDS)]


_breed_cache = []


def _breed_items(self, context):
    global _breed_cache
    items = [("ALL", "All Breeds", "", 0)]
    for breed in registry.get_catalog().breeds():
        items.append((breed, breed, "", _stable(breed)))
    _breed_cache = items  # Blender needs the strings to stay alive
    return items


def rebuild_list(wm=None):
    """Fill the list with the chickens matching the filters."""
    wm = wm or bpy.context.window_manager
    state = wm.cs_chicken
    settings = utils.prefs()
    incomplete = settings.include_incomplete if settings is not None else True
    try:
        breed = state.breed
    except TypeError:
        breed = "ALL"
    ids = registry.view(state.search, state.kind, breed, incomplete)
    current = state.items[state.index].chicken_id if 0 <= state.index < len(state.items) else ""
    state.items.clear()
    for cid in ids:
        chicken = registry.get(cid)
        item = state.items.add()
        item.chicken_id = cid
        item.label = chicken.label
        item.kind = chicken.kind
        item.complete = chicken.complete
    state.index = next((i for i, it in enumerate(state.items) if it.chicken_id == current), 0 if ids else -1)


def _on_filter(self, context):
    rebuild_list(context.window_manager)


class CSCHICKEN_PG_browser(bpy.types.PropertyGroup):
    search: StringProperty(name="Search", description="Filter by name, breed, color or kind",
                           update=_on_filter, options={"TEXTEDIT_UPDATE"})
    kind: EnumProperty(name="Kind", items=_kind_items, update=_on_filter)
    breed: EnumProperty(name="Breed", items=_breed_items, update=_on_filter)
    items: CollectionProperty(type=CSCHICKEN_PG_item)
    index: IntProperty(default=-1)
    show_preview: BoolProperty(name="Preview", default=True)

    def selected(self):
        if 0 <= self.index < len(self.items):
            return registry.get(self.items[self.index].chicken_id)
        return None


# ---------------------------------------------------------------------------
# Spawn options
# ---------------------------------------------------------------------------

class CSCHICKEN_PG_scene(bpy.types.PropertyGroup):
    scale: FloatProperty(name="Scale", default=1.0, min=0.001, soft_max=100.0,
                         description="1 = game size in meters (the glTF export is in meters)")
    random_seed: BoolProperty(name="Random Appearance", default=False,
                              description="New seed for every spawned chicken (hue, brightness, speckles, ...), "
                                          "like the random pets in the game")
    seed: IntProperty(name="Seed", default=0, min=0,
                      description="Appearance seed when Random Appearance is off. 0 = original "
                                  "material: the colors of the variant as named")
    random_rotation: BoolProperty(name="Random Rotation", default=False,
                                  description="Turn every spawned chicken around its up axis at random")
    spacing: FloatProperty(name="Spacing", default=0.5, min=0.0, unit="LENGTH",
                           description="Distance between chickens of 'Spawn All Variants' (demo operator)")


# ---------------------------------------------------------------------------
# Per chicken
# ---------------------------------------------------------------------------

def _on_input(self, context):
    root = self.id_data
    from .ops import spawn
    spawn.apply_appearance(root)


def _on_seed(self, context):
    root = self.id_data
    from .ops import spawn
    spawn.reseed(root)


def _get_age(self):
    return float(self.get("age", C.DEFAULT_AGE))


def _set_age(self, value):
    from .ops import spawn
    spawn.set_age(self.id_data, value)


class CSCHICKEN_PG_input(bpy.types.PropertyGroup):
    """One appearance input of the CS2 material ($egg_hue ...)."""
    value: FloatProperty(name="Value", min=0.0, max=1.0, subtype="FACTOR", update=_on_input)


_variant_cache = []


def _variant_items(self, context):
    global _variant_cache
    root = self.id_data
    current = registry.get(self.chicken_id)
    items = []
    if current is not None:
        for c in registry.get_catalog():
            if c.model == current.model:
                items.append((c.id, c.variant or c.name, c.label, _stable(c.id)))
    if not items:
        items = [(self.chicken_id or "NONE", root.name, "", 0)]
    _variant_cache = items
    return items


def _get_variant(self):
    for item in _variant_items(self, None):
        if item[0] == self.chicken_id:
            return item[3]
    return 0


def _set_variant(self, value):
    for item in _variant_items(self, None):
        if item[3] == value and item[0] != self.chicken_id:
            from .ops import spawn
            spawn.set_variant(self.id_data, item[0])
            return


class CSCHICKEN_PG_object(bpy.types.PropertyGroup):
    chicken_id: StringProperty(name="Chicken")
    variant: EnumProperty(name="Variant", items=_variant_items, get=_get_variant, set=_set_variant,
                          description="Color variant (CS2 material group) of this breed")
    seed: IntProperty(name="Seed", min=0, update=_on_seed,
                      description="Sets all appearance inputs from one number like the CS2 pet seed. "
                                  "0 = original material (colors as the variant is named)")
    inputs: CollectionProperty(type=CSCHICKEN_PG_input)
    age: FloatProperty(name="Age", min=0.0, max=1.0, subtype="FACTOR", get=_get_age, set=_set_age,
                       description="Age within the stage: scales the model like CS2 (chick: 0.3 just "
                                   "hatched to 0.5 before the pullet stage)")


_classes = (CSCHICKEN_PG_item, CSCHICKEN_PG_browser, CSCHICKEN_PG_scene, CSCHICKEN_PG_input,
            CSCHICKEN_PG_object)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.cs_chicken = PointerProperty(type=CSCHICKEN_PG_browser)
    bpy.types.Scene.cs_chicken = PointerProperty(type=CSCHICKEN_PG_scene)
    bpy.types.Object.cs_chicken = PointerProperty(type=CSCHICKEN_PG_object)


def unregister():
    del bpy.types.Object.cs_chicken
    del bpy.types.Scene.cs_chicken
    del bpy.types.WindowManager.cs_chicken
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
