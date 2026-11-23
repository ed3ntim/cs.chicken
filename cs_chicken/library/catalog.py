# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Chicken library: catalog format, appearance inputs, naming. Pure Python
(no bpy), shared with tools/export_cs2_chickens.py and the tests.

A library is a folder with ``catalog.json``::

    {
      "version": 1,
      "chickens": [
        {"id": "cs2_pet3_chicken_catalana_01_v2", "name": "Pet Chicken (Catalana)",
         "kind": "CHICKEN", "breed": "Catalana", "variant": "Black White Head",
         "model": "models/chicken.glb", "icon": "",
         "slots": {"chicken_catalan_tan": "materials/models/chicken/chicken_catalan_black_white_head.vmat"},
         "def_index": 3, "tags": ["chicken_catalana_01"],
         "skeleton": "animation/skeletons/characters/chicken/chicken.vnmskel",
         "age_scale": [0.3, 0.5]}
      ],
      "materials": {
        "materials/models/chicken/chicken_catalan_black_white_head.vmat": {
          "shader": "csgo_character.vfx",
          "params": {"g_fBrightness": 1.0, "F_TINT_MASK": 1, ...},
          "dynamic": {"g_fHueShift": "return lerp(-12,165,$egg_hue*$egg_hue);"},
          "textures": {"TextureColor": "textures/...png", ...},
          "constants": {"TextureRoughness": [0.73, 0.73, 0.73, 1.0]}
        }
      }
    }

``slots`` maps the glTF material name of the model to a material key. One
entry per pet and color variant (CS2 material group); all variants of a
breed share the model. Materials of shaders cs.chicken does not rebuild
(``csgo_complex.vfx`` of the roasted chicken, map props) are left out of
``slots``: the model keeps the material of its glTF import.

Appearance inputs: CS2 computes some parameters of the egg and the chick
per pet (``DynamicParams`` with ``$egg_hue``, ``$chick_brightness``, ...).
Their values come from the pet's seed in the game and are not documented;
here every input is 0..1, set from a seed (``appearance_from_seed``, seed 0
= neutral, all 0.5) and adjustable by hand.
"""

import json
import os
import re
import zlib

from . import expr

CATALOG_FILE = "catalog.json"
CATALOG_VERSION = 1

KINDS = ("EGG", "CHICK", "CHICKEN", "HATCHING", "ROASTED", "PROP")
KIND_LABELS = {
    "EGG": "Egg", "CHICK": "Chick", "CHICKEN": "Chicken", "HATCHING": "Hatching Egg",
    "ROASTED": "Roasted", "PROP": "Prop",
}

CHARACTER_SHADER = "csgo_character.vfx"
SUPPORTED_SHADERS = (CHARACTER_SHADER,)

# Material file prefixes of the breeds, removed for the variant name.
_VARIANT_PREFIXES = ("chicken_catalana_", "chicken_catalan_", "chicken_polish_", "chicken_silkie_",
                     "chick_", "chicken_", "egg_")


def make_id(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "chicken"


def pretty_name(text):
    """'black_white_head' -> 'Black White Head'."""
    words = [w for w in re.split(r"[_\s]+", str(text)) if w]
    return " ".join(w if w.isupper() else w.capitalize() for w in words)


def variant_name(material_path):
    """'materials/models/chicken/chicken_catalan_black_with_red_head.vmat'
    -> 'Black With Red Head'. The '_color' suffix of a few CS2 material
    names is dropped."""
    stem = os.path.splitext(os.path.basename(str(material_path).replace("\\", "/")))[0].lower()
    for prefix in _VARIANT_PREFIXES:
        if stem.startswith(prefix) and len(stem) > len(prefix):
            stem = stem[len(prefix):]
            break
    if stem.endswith("_color"):
        stem = stem[:-6]
    return pretty_name(stem)


def breed_of(pet_name):
    """'chicken_catalana_01' -> 'Catalana', 'chicken_chick_01' -> ''."""
    m = re.match(r"^chicken_([a-z]+)_\d+$", str(pet_name).lower())
    if not m or m.group(1) in ("egg", "chick"):
        return ""
    return pretty_name(m.group(1))


# ---------------------------------------------------------------------------
# Appearance inputs ($egg_hue ...)
# ---------------------------------------------------------------------------

def dynamic_inputs(dynamic):
    """Sorted ``$names`` used by a material's DynamicParams."""
    names = set()
    for text in (dynamic or {}).values():
        try:
            names.update(expr.variables_used(text))
        except expr.ExprError:
            pass
    return sorted(n for n in names if n.startswith("$"))


NEUTRAL_SEED = 0
# Default age within a stage (only models with age scales, the chick).
DEFAULT_AGE = 0.5


def seed_value(seed, name):
    """Deterministic 0..1 value of one appearance input for a seed. Seed 0
    gives 0.5 everywhere; it is not evaluated though: seed 0 shows the
    original material (see ``evaluate_params`` with env None)."""
    if int(seed) == NEUTRAL_SEED:
        return 0.5
    h = zlib.crc32(f"{int(seed)}:{name}".encode("utf-8")) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


def appearance_from_seed(seed, names):
    return {n: seed_value(seed, n) for n in names}


def evaluate_params(spec, env):
    """Static params of ``spec`` with its DynamicParams evaluated in ``env``
    ({"$egg_hue": 0.3, ...}) on top. Broken expressions keep the static value.
    ``env`` None: the original material (static params only, no
    DynamicParams), what seed 0 shows."""
    params = dict(spec.params)
    if env is None:
        return params
    for key, text in spec.dynamic.items():
        try:
            params[key] = expr.evaluate(text, env, default=0.5)
        except (expr.ExprError, ZeroDivisionError, OverflowError, ValueError):
            pass
    return params


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class MaterialSpec:
    __slots__ = ("key", "shader", "params", "dynamic", "textures", "constants")

    def __init__(self, key, shader="", params=None, dynamic=None, textures=None, constants=None):
        self.key = key
        self.shader = shader
        self.params = dict(params or {})
        self.dynamic = dict(dynamic or {})
        self.textures = dict(textures or {})
        self.constants = dict(constants or {})

    @classmethod
    def from_dict(cls, key, data, root=""):
        textures = {}
        for slot, path in (data.get("textures") or {}).items():
            if isinstance(path, str) and path:
                textures[slot] = path if os.path.isabs(path) or not root else os.path.normpath(
                    os.path.join(root, path))
        constants = {k: [float(x) for x in v] for k, v in (data.get("constants") or {}).items()
                     if isinstance(v, (list, tuple))}
        params = {k: v for k, v in (data.get("params") or {}).items() if isinstance(v, (int, float, list))}
        dynamic = {k: v for k, v in (data.get("dynamic") or {}).items() if isinstance(v, str)}
        return cls(key, str(data.get("shader", "")), params, dynamic, textures, constants)

    def to_dict(self):
        return {"shader": self.shader, "params": self.params, "dynamic": self.dynamic,
                "textures": self.textures, "constants": self.constants}

    @property
    def supported(self):
        return self.shader.lower() in SUPPORTED_SHADERS

    def flag(self, name):
        try:
            return bool(int(self.params.get(name, 0)))
        except (TypeError, ValueError):
            return False

    @property
    def inputs(self):
        return dynamic_inputs(self.dynamic)


def _scale_pair(value):
    try:
        lo, hi = (float(v) for v in value)
    except (TypeError, ValueError):
        return None
    return (lo, hi) if lo > 0 and hi > 0 else None


PREVIEW_DIR = "previews"  # <library>/previews/<id>.png, made by preview_render.py


def display_name(name):
    """Name without the item prefix: 'Pet Chicken' -> 'Chicken'."""
    name = str(name).strip()
    head, _, rest = name.partition(" ")
    return rest.strip() if head.lower() == "pet" and rest.strip() else name


def preview_path(folder, chicken_id):
    return os.path.join(folder, PREVIEW_DIR, f"{chicken_id}.png")


class Chicken:
    __slots__ = ("id", "name", "kind", "breed", "variant", "model", "icon", "preview", "slots", "def_index",
                 "tags", "skeleton", "age_scale", "materials", "missing")

    def __init__(self, id, name, kind="CHICKEN", breed="", variant="", model="", icon="", slots=None,
                 def_index=0, tags=None, skeleton="", age_scale=None):
        self.id = id
        self.name = name
        self.kind = kind if kind in KINDS else "PROP"
        self.breed = breed
        self.variant = variant
        self.model = model
        self.icon = icon
        self.preview = ""  # rendered preview image, '' if none (see preview_image)
        self.slots = dict(slots or {})
        self.def_index = def_index
        self.tags = list(tags or [])
        self.skeleton = skeleton  # CS2 skeleton (.vnmskel) of the model, '' if unrigged
        # (min, max) model scale over the age of the stage (vmdl ScaleSets
        # age_min/age_max, only the chick), None for a fixed size
        self.age_scale = _scale_pair(age_scale)
        self.materials = {}   # slot -> MaterialSpec (resolved by Catalog)
        self.missing = []     # missing files (model, textures)

    @property
    def label(self):
        """Display name: 'Chicken (Catalana) | Black White Head'."""
        name = self.name
        if self.breed and self.breed.lower() not in name.lower():
            name = f"{name} ({self.breed})"
        return f"{name} | {self.variant}" if self.variant else name

    @property
    def inputs(self):
        """Appearance inputs of all its materials."""
        names = set()
        for spec in self.materials.values():
            names.update(spec.inputs)
        return sorted(names)

    @property
    def preview_image(self):
        """Image for the UI: the rendered preview, else the game's inventory icon."""
        for path in (self.preview, self.icon):
            if path and os.path.isfile(path):
                return path
        return ""

    def scale_at(self, age):
        """Model scale at ``age`` (0 = start of the stage, 1 = end), 1.0 without age scales."""
        if not self.age_scale:
            return 1.0
        lo, hi = self.age_scale
        age = min(max(float(age), 0.0), 1.0)
        return lo + (hi - lo) * age

    @property
    def complete(self):
        return not self.missing

    def matches(self, text):
        if not text:
            return True
        hay = " ".join([self.label, self.kind, KIND_LABELS.get(self.kind, ""), *self.tags]).lower()
        return all(word in hay for word in text.lower().split())


class Catalog:
    """All chickens of one or more library folders, by id."""

    def __init__(self):
        self.chickens = {}
        self.order = []
        self.sources = []

    def __len__(self):
        return len(self.order)

    def __iter__(self):
        return (self.chickens[i] for i in self.order)

    def get(self, chicken_id):
        return self.chickens.get(chicken_id)

    def add(self, chicken):
        if chicken.id not in self.chickens:
            self.order.append(chicken.id)
        self.chickens[chicken.id] = chicken

    def breeds(self):
        return sorted({c.breed for c in self if c.breed})

    def load_folder(self, folder):
        """Read ``folder/catalog.json``. Returns the number of chickens added
        (0 if there is no catalog). Raises ValueError for broken files."""
        path = os.path.join(folder, CATALOG_FILE)
        if not os.path.isfile(path):
            return 0
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}: {exc}") from None
        specs = {key: MaterialSpec.from_dict(key, value, folder)
                 for key, value in (data.get("materials") or {}).items() if isinstance(value, dict)}
        count = 0
        for raw in data.get("chickens") or []:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            model = raw.get("model", "")
            icon = raw.get("icon", "")
            chicken = Chicken(
                id=str(raw["id"]), name=display_name(raw.get("name") or pretty_name(raw["id"])),
                kind=str(raw.get("kind", "CHICKEN")), breed=str(raw.get("breed", "")),
                variant=str(raw.get("variant", "")),
                model=os.path.normpath(os.path.join(folder, model)) if model else "",
                icon=os.path.normpath(os.path.join(folder, icon)) if icon else "",
                slots=raw.get("slots") or {}, def_index=int(raw.get("def_index", 0) or 0),
                tags=raw.get("tags") or [], skeleton=str(raw.get("skeleton", "")),
                age_scale=raw.get("age_scale"))
            chicken.preview = preview_path(folder, chicken.id)
            for slot, key in chicken.slots.items():
                spec = specs.get(key)
                if spec is not None:
                    chicken.materials[slot] = spec
            if not chicken.model or not os.path.isfile(chicken.model):
                chicken.missing.append(model or "model")
            for spec in chicken.materials.values():
                chicken.missing += [os.path.basename(p) for p in spec.textures.values() if not os.path.isfile(p)]
            self.add(chicken)
            count += 1
        self.sources.append(folder)
        return count


def load(folders):
    """Catalog from several folders; later folders override ids of earlier
    ones. Returns (catalog, errors)."""
    cat, errors = Catalog(), []
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        try:
            cat.load_folder(folder)
        except ValueError as exc:
            errors.append(str(exc))
    return cat, errors
