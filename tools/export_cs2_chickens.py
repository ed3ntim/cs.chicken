# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Export all CS2 chickens and eggs (pets) from your own game installation
into a cs.chicken library (catalog.json + glTF models + textures), using
Source2Viewer-CLI.

    python tools/export_cs2_chickens.py --out D:/cs2_chickens --download-s2v
    python tools/export_cs2_chickens.py --out D:/cs2_chickens --s2v C:/tools/Source2Viewer-CLI.exe

Then point the add-on's "Chicken Library Folder" at --out, or build a
personal add-on zip with everything included:

    python tools/build_zip.py --with-chickens D:/cs2_chickens

What it does:
1. reads ``pet_definitions`` from scripts/items/items_game.txt (egg, chick,
   the breeds) plus a few other chicken models (hatching egg, roasted
   chicken, the dead chicken prop), names from the localization,
2. exports each model as .glb with skeleton and materials,
3. decompiles the models for their material groups (the color variants of
   a breed: "chicken_catalan_tan" -> "chicken_catalan_black", ...) and
   skeleton, and the materials for their parameters, DynamicParams and
   source textures,
4. exports ``g_tAnisoGloss`` (roughness of the grown chickens) and the
   egg's inventory image, writes catalog.json: one entry per pet and
   color variant.

Requirements: CS2 installed via Steam, Source2Viewer-CLI
(https://github.com/ValveResourceFormat/ValveResourceFormat/releases,
asset "cli-windows-x64.zip"; --download-s2v fetches it). Python 3.9+, no
other packages. After a CS2 update simply run it again.

The models and textures are Valve's copyrighted game assets: export them
for your own use only and do not redistribute them.
"""

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import types
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(ROOT, "cs_chicken", "library")

S2V_RELEASES = "https://api.github.com/repos/ValveResourceFormat/ValveResourceFormat/releases/latest"
S2V_ASSET = "cli-windows-x64.zip"
S2V_NAMES = ("Source2Viewer-CLI.exe", "Source2Viewer-CLI")

ITEMS_GAME = "scripts/items/items_game.txt"
ICON_ROOT = "panorama/images/"
RAW_DIR = "_raw"
VMDL_DIR = "_vmdl"       # decompiled .vmdl text (own folder: the glb export writes next to the models)
BATCH = 80               # file filters per Source2Viewer call (Windows command line limit)
NO_ANIMATIONS = "__cs_chicken_none__"  # animation filter that matches nothing: skin without clips
GLTF_FLAGS = ("--gltf_export_format", "glb", "--gltf_export_materials", "--gltf_textures_adapt",
              "--gltf_export_animations", "--gltf_animation_list", NO_ANIMATIONS)

# Chicken models that are not pets: (vmdl, kind, name)
EXTRA_MODELS = (
    ("models/chicken/chicknegg.vmdl", "HATCHING", "Hatching Egg"),
    ("models/chicken/chicken_roasted.vmdl", "ROASTED", "Roasted Chicken"),
    ("models/props/cs_italy/dead_chicken.vmdl", "PROP", "Dead Chicken"),
)
PET_KINDS = {"egg": "EGG", "chick": "CHICK"}


# ---------------------------------------------------------------------------
# Library modules (loaded without bpy / the add-on package __init__)
# ---------------------------------------------------------------------------

def _load_library():
    """Import cs_chicken/library/{expr,gltf,catalog,shading}.py as a
    stand-alone package so the shared code runs outside Blender."""
    pkg = types.ModuleType("cklib")
    pkg.__path__ = [LIB_DIR]
    sys.modules["cklib"] = pkg
    mods = {}
    for name in ("expr", "gltf", "catalog", "shading"):
        spec = importlib.util.spec_from_file_location(f"cklib.{name}", os.path.join(LIB_DIR, f"{name}.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        mods[name] = mod
    return mods["gltf"], mods["catalog"], mods["shading"]


G, C, S = _load_library()


# ---------------------------------------------------------------------------
# Locating CS2 and Source2Viewer
# ---------------------------------------------------------------------------

def _steam_roots():
    roots = []
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        for value in ("SteamPath", "InstallPath"):
                            try:
                                roots.append(winreg.QueryValueEx(k, value)[0])
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        roots += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    else:
        home = os.path.expanduser("~")
        roots += [os.path.join(home, ".steam", "steam"), os.path.join(home, ".local", "share", "Steam"),
                  os.path.join(home, "Library", "Application Support", "Steam")]
    return [os.path.normpath(r) for r in roots if r and os.path.isdir(r)]


def find_cs2(explicit=""):
    """Path to game/csgo (the folder holding pak01_dir.vpk)."""
    candidates = []
    if explicit:
        candidates += [explicit, os.path.join(explicit, "game", "csgo")]
    for steam in _steam_roots():
        libraries = [steam]
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            with open(vdf, encoding="utf-8", errors="replace") as fh:
                libraries += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', fh.read())]
        for lib in libraries:
            candidates.append(os.path.join(lib, "steamapps", "common", "Counter-Strike Global Offensive", "game", "csgo"))
    for c in candidates:
        if os.path.isfile(os.path.join(c, "pak01_dir.vpk")):
            return os.path.normpath(c)
    raise SystemExit("CS2 not found. Pass --cs2 <...>/Counter-Strike Global Offensive")


def download_s2v(dest):
    print("downloading Source2Viewer-CLI (latest release) ...")
    req = urllib.request.Request(S2V_RELEASES, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        release = json.load(resp)
    asset = next((a for a in release.get("assets", []) if a["name"] == S2V_ASSET), None)
    if asset is None:
        raise SystemExit(f"release {release.get('tag_name')} has no {S2V_ASSET}")
    os.makedirs(dest, exist_ok=True)
    zpath = os.path.join(dest, S2V_ASSET)
    urllib.request.urlretrieve(asset["browser_download_url"], zpath)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(dest)
    print(f"Source2Viewer-CLI {release.get('tag_name')} -> {dest}")


def find_s2v(explicit, tools_dir, download):
    candidates = [explicit] if explicit else []
    candidates += [os.path.join(tools_dir, n) for n in S2V_NAMES]
    candidates += [shutil.which(n) or "" for n in S2V_NAMES]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    if download:
        download_s2v(tools_dir)
        return find_s2v("", tools_dir, False)
    raise SystemExit("Source2Viewer-CLI not found. Pass --s2v <path> or use --download-s2v")


def run_s2v(exe, vpk, out, filters, extensions=None, decompile=True, threads=8, extra=()):
    """Run Source2Viewer-CLI over ``filters`` (paths or folder prefixes) in batches."""
    filters = sorted(set(filters))
    started, written = time.time(), 0
    for i in range(0, len(filters), BATCH):
        cmd = [exe, "-i", vpk, "-o", out, "-f", ",".join(filters[i:i + BATCH]), "--threads", str(threads)]
        if extensions:
            cmd += ["-e", extensions]
        if decompile:
            cmd.append("-d")
        cmd += list(extra)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace")
        for line in proc.stdout:
            if "Dump written" in line or "written to" in line:
                written += 1
            elif re.search(r"\berror\b|exception", line, re.I):
                print("  " + line.rstrip())
        if proc.wait() != 0:
            raise SystemExit(f"Source2Viewer-CLI failed (exit {proc.returncode})")
    print(f"  done: {written} files in {time.time() - started:.0f}s")


# ---------------------------------------------------------------------------
# KeyValues (items_game.txt, localization, decompiled .vmat) and KV3 (.vmdl)
# ---------------------------------------------------------------------------

_KV_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*|([^\s{}"]+)')


def parse_kv(text):
    """Parse KeyValues1 into nested lists of (key, value) pairs; values are
    strings or lists. Keeps duplicate keys (items_game has several blocks)."""
    stack = [[]]
    key = None
    for m in _KV_TOKEN.finditer(text):
        quoted, brace, bare = m.groups()
        if brace == "{":
            block = []
            stack[-1].append((key, block))
            stack.append(block)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif quoted is not None or bare is not None:
            tok = quoted if quoted is not None else bare
            if key is None:
                key = tok
            else:
                stack[-1].append((key, tok))
                key = None
    return stack[0]


def find_blocks(pairs, name):
    for key, value in pairs:
        if isinstance(value, list):
            if key and key.lower() == name:
                yield value
            else:
                yield from find_blocks(value, name)


def _to_dict(block):
    out = {}
    for key, value in block:
        if key is not None and key not in out:
            out[key] = _to_dict(value) if isinstance(value, list) else value
    return out


def load_tokens(path):
    """Localization tokens, lower-cased keys."""
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        data = parse_kv(fh.read())
    tokens = {}
    for block in find_blocks(data, "tokens"):
        for key, value in block:
            if isinstance(value, str) and key:
                tokens.setdefault(key.lower(), value)
    return tokens


def load_pets(path):
    """(pet definitions by index, egg item image) from items_game.txt."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        data = parse_kv(fh.read())
    pets = {}
    for block in find_blocks(data, "pet_definitions"):
        for index, fields in block:
            if isinstance(fields, list):
                pets[index] = _to_dict(fields)
    images = {}
    for block in find_blocks(data, "items"):
        for _index, fields in block:
            if isinstance(fields, list):
                item = _to_dict(fields)
                if item.get("item_class") in ("chicken_egg",) and item.get("image_inventory"):
                    images[item["item_class"]] = item["image_inventory"]
    return pets, images


def parse_material_groups(text):
    """Material groups of a decompiled .vmdl (KV3 text):
    [(group name, {from vmat: to vmat})], default group first with {}."""
    groups = []
    for m in re.finditer(r'_class\s*=\s*"(DefaultMaterialGroup|MaterialGroup)"\s*name\s*=\s*"([^"]*)"', text):
        start = m.end()
        nxt = re.search(r'_class\s*=\s*"(?:DefaultMaterialGroup|MaterialGroup|[A-Za-z]+List)"', text[start:])
        body = text[start:start + nxt.start()] if nxt else text[start:]
        remaps = dict(re.findall(r'from\s*=\s*"([^"]+)"\s*to\s*=\s*"([^"]+)"', body))
        groups.append((m.group(2), {k.replace("\\", "/"): v.replace("\\", "/") for k, v in remaps.items()}))
    return groups


def parse_skeleton(text):
    m = re.search(r'filename\s*=\s*"([^"]+\.vnmskel)"', text)
    return m.group(1).replace("\\", "/") if m else ""


def parse_age_scale(text):
    """[min, max] model scale of the ScaleSets ``age_min`` / ``age_max`` of a
    decompiled .vmdl (chick: 0.3 just hatched, 0.5 before the pullet stage),
    None if the model has none. Uses the first bone scale of each set (the
    root bone)."""
    found = {}
    for m in re.finditer(r'_class\s*=\s*"ScaleSet"\s*name\s*=\s*"(age_min|age_max)"', text):
        body = text[m.end():]
        nxt = re.search(r'_class\s*=\s*"ScaleSet"', body)
        body = body[:nxt.start()] if nxt else body
        sm = re.search(r'scale\s*=\s*([-0-9.eE]+)', body)
        if sm:
            found[m.group(1)] = float(sm.group(1))
    if "age_min" in found and "age_max" in found:
        return [found["age_min"], found["age_max"]]
    return None


def parse_vmat(path):
    """Decompiled .vmat -> (shader, params, dynamic, textures, constants, compiled)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        data = parse_kv(fh.read())
    layer = next(iter(find_blocks(data, "layer0")), None) or data
    shader, params, dynamic, textures, constants, compiled = "", {}, {}, {}, {}, {}
    for key, value in layer:
        if key is None:
            continue
        if isinstance(value, list):
            low = key.lower()
            if low == "compiled textures":
                compiled = {k: v.replace("\\", "/") for k, v in value if isinstance(v, str)}
            elif low == "dynamicparams":
                dynamic = {k: v.replace("\\n", "\n") for k, v in value if isinstance(v, str)}
            continue
        if key == "shader":
            shader = value
        elif key.startswith("Texture"):
            const = S.parse_constant(value)
            if const is not None:
                constants[key] = const
            elif value:
                textures[key] = value.replace("\\", "/")
        elif key.startswith(("g_", "F_")):
            num = _number(value)
            if num is not None:
                params[key] = num
    return shader, params, dynamic, textures, constants, compiled


def _number(text):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            return [float(x) for x in text[1:-1].split()]
        except ValueError:
            return None
    try:
        value = float(text)
    except ValueError:
        return None
    return int(value) if value.is_integer() and "." not in text else value


# ---------------------------------------------------------------------------
# Building the library
# ---------------------------------------------------------------------------

def _strip_c(path):
    path = path.replace("\\", "/")
    return path[:-2] if path.endswith("_c") else path


def _raw_path(raw, vpk_path, ext):
    """raw/<vpk path without extension>.<ext>"""
    stem = os.path.splitext(_strip_c(vpk_path))[0]
    return os.path.join(raw, *stem.split("/")) + ext


def model_entries(pets):
    """[(key, vmdl, kind, name token or name, pet name, def index)] for all exported models."""
    out = []
    for index, pet in sorted(pets.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 0):
        vmdl = re.sub(r"[\\/]+", "/", pet.get("pedestal_display_model", ""))
        if not vmdl:
            continue
        name = pet.get("name", "")
        kind = next((k for part, k in PET_KINDS.items() if f"_{part}_" in f"_{name}_"), "CHICKEN")
        out.append((f"pet{index}", vmdl, kind, pet.get("loc_name", ""), name, int(index)
                    if str(index).isdigit() else 0))
    for vmdl, kind, name in EXTRA_MODELS:
        out.append((C.make_id(os.path.splitext(os.path.basename(vmdl))[0]), vmdl, kind, name, "", 0))
    return out


def model_slots(glb_path):
    """{glTF material name: vmat path} of an exported model."""
    data = G.read_json(glb_path)
    return {name: (vmat or {}).get("Name", "").replace("\\", "/") for name, vmat in G.material_extras(data)}


def variants_of(slots, groups):
    """[(variant vmat of the main slot, {slot: vmat})] per distinct material group."""
    out, seen = [], set()
    for _name, remaps in groups or [("default", {})]:
        mapping = {slot: remaps.get(vmat, vmat) for slot, vmat in slots.items()}
        key = tuple(sorted(mapping.items()))
        if key in seen:
            continue
        seen.add(key)
        changed = [v for s, v in mapping.items() if v != slots[s]]
        out.append((changed[0] if changed else next(iter(slots.values()), ""), mapping))
    return out


def build_library(out, raw, vmdl_raw, pets, tokens, images, move=False):
    """Write out/catalog.json, copy models and textures.
    Returns (chickens, warnings)."""
    chickens, materials, warnings = [], {}, []
    copied = {}

    def place(src, dst_rel):
        key = os.path.normcase(os.path.abspath(src))
        if key not in copied:
            dst = os.path.join(out, *dst_rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            (shutil.move if move else shutil.copy2)(src, dst)
            copied[key] = dst_rel
        return copied[key]

    def texture_rel(vpk_path):
        rel = vpk_path.replace("\\", "/")
        if rel.startswith("materials/"):
            rel = rel[len("materials/"):]
        if rel.startswith("models/"):
            rel = rel[len("models/"):]
        return "textures/" + rel

    def material(vmat_path):
        if vmat_path in materials:
            return materials[vmat_path]
        vmat_file = _raw_path(raw, vmat_path, ".vmat")
        if not os.path.isfile(vmat_file):
            warnings.append(f"material not exported: {vmat_path}")
            materials[vmat_path] = None
            return None
        shader, params, dynamic, textures, constants, compiled = parse_vmat(vmat_file)
        spec = {"shader": shader, "params": params, "dynamic": dynamic, "textures": {}, "constants": constants}
        for key, rel in textures.items():
            if S.texture_role(key) is None:
                continue
            src = os.path.join(raw, *rel.split("/"))
            if os.path.isfile(src):
                spec["textures"][key] = place(src, texture_rel(rel))
            elif not rel.startswith("materials/default/"):
                warnings.append(f"{os.path.basename(vmat_path)}: missing {key} {rel}")
        aniso = compiled.get("g_tAnisoGloss")
        if aniso and params.get("F_ANISOTROPIC_GLOSS"):
            src = _raw_path(raw, aniso, ".png")
            if os.path.isfile(src):
                spec["textures"]["g_tAnisoGloss"] = place(src, texture_rel(_strip_c(aniso)[:-5] + ".png"))
            else:
                warnings.append(f"{os.path.basename(vmat_path)}: missing g_tAnisoGloss {aniso}")
        materials[vmat_path] = spec
        return spec

    for key, vmdl, kind, name_token, pet_name, def_index in model_entries(pets):
        glb = _raw_path(raw, vmdl, ".glb")
        if not os.path.isfile(glb):
            warnings.append(f"model not exported: {vmdl}")
            continue
        vmdl_text = ""
        vmdl_file = _raw_path(vmdl_raw, vmdl, ".vmdl")
        if os.path.isfile(vmdl_file):
            with open(vmdl_file, encoding="utf-8", errors="replace") as fh:
                vmdl_text = fh.read()
        groups = parse_material_groups(vmdl_text)
        skeleton = parse_skeleton(vmdl_text) if G.has_skin(G.read_json(glb)) else ""
        age_scale = parse_age_scale(vmdl_text)
        name = tokens.get(name_token.lstrip("#").lower(), "") if name_token.startswith("#") else name_token
        name = name or C.pretty_name(pet_name or key)
        breed = C.breed_of(pet_name)
        model_rel = "models/" + os.path.basename(glb)
        if os.path.normcase(os.path.abspath(glb)) not in copied:
            for uri in G.image_uris(G.read_json(glb)):
                src = os.path.join(os.path.dirname(glb), uri)
                if os.path.isfile(src):
                    place(src, "models/" + uri)
        model_rel = place(glb, model_rel)
        slots = model_slots(os.path.join(out, *model_rel.split("/")))
        icon = ""
        if kind == "EGG" and images.get("chicken_egg"):
            src = os.path.join(raw, *(ICON_ROOT + images["chicken_egg"]).split("/")) + "_png.png"
            if os.path.isfile(src):
                icon = place(src, "icons/" + os.path.basename(src))
        variants, seen = [], set()
        for main_vmat, mapping in variants_of(slots, groups):
            used = {}
            for slot, vmat in mapping.items():
                spec = material(vmat) if vmat else None
                if spec is not None and spec["shader"].lower() in C.SUPPORTED_SHADERS:
                    used[slot] = vmat
            # Groups that only differ in materials cs.chicken does not rebuild
            # (roasted chicken) look the same: one entry.
            if tuple(sorted(used.items())) not in seen:
                seen.add(tuple(sorted(used.items())))
                variants.append((main_vmat, used))
        many = len(variants) > 1
        for main_vmat, used in variants:
            variant = C.variant_name(main_vmat) if many or kind == "CHICKEN" else ""
            chickens.append({
                "id": f"cs2_{key}_{C.make_id(pet_name or key)}" + (f"_{C.make_id(variant)}" if variant else ""),
                "name": name, "kind": kind, "breed": breed, "variant": variant,
                "model": model_rel, "icon": icon, "slots": used, "def_index": def_index,
                "tags": [t for t in (pet_name, os.path.basename(main_vmat)) if t],
                "skeleton": skeleton,
                **({"age_scale": age_scale} if age_scale else {}),
            })

    catalog = {
        "version": C.CATALOG_VERSION,
        "generator": "cs.chicken tools/export_cs2_chickens.py",
        "note": "Valve game assets exported from a local CS2 install. Personal use only.",
        "chickens": chickens,
        "materials": {k: v for k, v in materials.items() if v is not None},
    }
    with open(os.path.join(out, C.CATALOG_FILE), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(catalog, fh, indent=1, ensure_ascii=False)
    return chickens, warnings


def needed_vmats(raw, vmdl_raw, pets):
    """All materials of the models and their material groups."""
    out = set()
    for _key, vmdl, *_rest in model_entries(pets):
        glb = _raw_path(raw, vmdl, ".glb")
        if os.path.isfile(glb):
            out.update(v for v in model_slots(glb).values() if v)
        vmdl_file = _raw_path(vmdl_raw, vmdl, ".vmdl")
        if os.path.isfile(vmdl_file):
            with open(vmdl_file, encoding="utf-8", errors="replace") as fh:
                for _name, remaps in parse_material_groups(fh.read()):
                    out.update(remaps.values())
    return {v + "_c" for v in out}


def needed_aniso(raw, vmats):
    out = set()
    for vmat in vmats:
        path = _raw_path(raw, vmat, ".vmat")
        if os.path.isfile(path):
            _s, params, _d, _t, _c, compiled = parse_vmat(path)
            if params.get("F_ANISOTROPIC_GLOSS") and compiled.get("g_tAnisoGloss"):
                out.add(compiled["g_tAnisoGloss"] + "_c")
    return out


def find_blender(path=""):
    """Blender executable: ``path``, ``blender`` on PATH, or the newest one in
    the default install folders ('' if none)."""
    if path:
        return path if os.path.isfile(path) else ""
    found = shutil.which("blender")
    if found:
        return found
    candidates = []
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), "/Applications", "/usr/bin"):
        root = os.path.join(base, "Blender Foundation")
        if os.path.isdir(root):
            for name in os.listdir(root):
                exe = os.path.join(root, name, "blender.exe")
                if os.path.isfile(exe):
                    candidates.append((_version_key(name), exe))
        mac = os.path.join(base, "Blender.app", "Contents", "MacOS", "Blender")
        if os.path.isfile(mac):
            candidates.append(((0,), mac))
    return max(candidates)[1] if candidates else ""


def _version_key(name):
    return tuple(int(n) for n in re.findall(r"\d+", name)) or (0,)


def render_previews(out, blender):
    """Render <out>/previews/<id>.png with the add-on in a background Blender."""
    script = os.path.join(ROOT, "cs_chicken", "preview_render.py")
    cmd = [blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python", script, "--", out]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    lines = [line for line in result.stdout.splitlines() if line.startswith("cs.chicken previews:")]
    print("\n".join("  " + line for line in lines[-1:]))
    if result.returncode:
        print(f"  warning: preview render failed (code {result.returncode}), "
              "render them later in the add-on preferences")


def main():
    ap = argparse.ArgumentParser(description="Export CS2 chickens and eggs into a cs.chicken library.")
    ap.add_argument("--out", required=True, help="library folder to create/update")
    ap.add_argument("--cs2", default="", help="CS2 install folder (auto-detected via Steam)")
    ap.add_argument("--s2v", default="", help="path to Source2Viewer-CLI(.exe)")
    ap.add_argument("--download-s2v", action="store_true", help="download Source2Viewer-CLI if not found")
    ap.add_argument("--language", default="english", help="localization for names (default english)")
    ap.add_argument("--threads", type=int, default=max(2, (os.cpu_count() or 4) - 1))
    ap.add_argument("--keep-raw", action="store_true", help="keep the raw Source2Viewer export in <out>/_raw")
    ap.add_argument("--skip-export", action="store_true", help="reuse an existing <out>/_raw export")
    ap.add_argument("--blender", default="", help="Blender executable for the preview images (auto-detected)")
    ap.add_argument("--no-previews", action="store_true", help="do not render the preview images")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    raw = os.path.join(out, RAW_DIR)
    vmdl_raw = os.path.join(out, RAW_DIR, VMDL_DIR)
    os.makedirs(raw, exist_ok=True)
    loc_file = f"resource/csgo_{args.language}.txt"
    items_game = os.path.join(raw, *ITEMS_GAME.split("/"))
    loc_path = os.path.join(raw, *loc_file.split("/"))

    exe = vpk = None
    if not args.skip_export:
        game = find_cs2(args.cs2)
        vpk = os.path.join(game, "pak01_dir.vpk")
        exe = find_s2v(args.s2v, os.path.join(out, "_tools"), args.download_s2v)
        print(f"CS2: {game}\nSource2Viewer: {exe}")
        print("1/6 metadata")
        run_s2v(exe, vpk, raw, [ITEMS_GAME, loc_file], decompile=False, threads=1)
    if not os.path.isfile(items_game):
        raise SystemExit(f"missing {items_game}: run without --skip-export")
    pets, images = load_pets(items_game)
    tokens = load_tokens(loc_path) if os.path.isfile(loc_path) else {}
    entries = model_entries(pets)
    print(f"{len(pets)} pet definitions, {len(entries)} models")

    if not args.skip_export:
        models = {vmdl + "_c" for _k, vmdl, *_r in entries}
        print(f"2/6 models ({len(models)}, glTF with skeleton and materials)")
        run_s2v(exe, vpk, raw, models, extensions="vmdl_c", threads=args.threads, extra=GLTF_FLAGS)
        print("3/6 model definitions (material groups)")
        run_s2v(exe, vpk, vmdl_raw, models, extensions="vmdl_c", threads=args.threads)
        vmats = needed_vmats(raw, vmdl_raw, pets)
        print(f"4/6 materials ({len(vmats)}, parameters and source textures)")
        run_s2v(exe, vpk, raw, vmats, extensions="vmat_c", threads=args.threads)
        aniso = needed_aniso(raw, {v[:-2] for v in vmats})
        icons = {ICON_ROOT + img + "_png.vtex_c" for img in images.values()}
        print(f"5/6 textures ({len(aniso)} gloss maps, {len(icons)} icons)")
        if aniso or icons:
            run_s2v(exe, vpk, raw, aniso | icons, extensions="vtex_c", threads=args.threads)

    print("6/6 library")
    # Rebuilt from raw every time, keeps the library in sync.
    for name in os.listdir(out):
        path = os.path.join(out, name)
        if os.path.isdir(path) and not name.startswith("_"):
            shutil.rmtree(path)
    chickens, warnings = build_library(out, raw, vmdl_raw, pets, tokens, images, move=not args.keep_raw)
    if not args.keep_raw:
        shutil.rmtree(raw, ignore_errors=True)

    for w in warnings:
        print("  warning: " + w)
    by_kind = {}
    for c in chickens:
        label = c["breed"] or C.KIND_LABELS.get(c["kind"], c["kind"])
        by_kind[label] = by_kind.get(label, 0) + 1
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(out)
               for f in fs if not os.path.relpath(d, out).startswith("_"))
    print(f"\n{len(chickens)} chickens and eggs -> {os.path.join(out, C.CATALOG_FILE)} ({size / 2**20:.0f} MiB)")
    for name, count in sorted(by_kind.items()):
        print(f"  {name}: {count}")
    if not args.no_previews:
        blender = find_blender(args.blender)
        if blender:
            print(f"previews ({blender})")
            render_previews(out, blender)
        else:
            print("previews: Blender not found (--blender), render them in the add-on preferences")
    print("Reminder: these are Valve's assets. Personal use only, do not redistribute.")


if __name__ == "__main__":
    main()
