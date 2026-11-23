# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Preview images of the library (``<library>/previews/<id>.png``).

CS2 has an inventory image only for the egg, so the previews are rendered:
every entry at seed 0 (original material), EEVEE, transparent background,
three-quarter view from the front. Runs in a background Blender so the
user's scene is not touched::

    blender -b --factory-startup --python cs_chicken/preview_render.py -- <library> [--all] [--size 256]

The add-on starts it with ``start()`` (button *Render Previews*), the export
tool after an export. Without ``--all`` only missing previews are rendered.
"""

import math
import os
import subprocess
import sys

SIZE = 256
SAMPLES = 32
AZIMUTH = 40.0      # degrees from the front, beak to the left
ELEVATION = 12.0
LENS = 80.0
MARGIN = 1.04


def _engine(scene):
    for name in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):  # 5.x, 4.x
        try:
            scene.render.engine = name
            return name
        except TypeError:
            continue
    scene.render.engine = "CYCLES"
    return "CYCLES"


def setup_scene(scene, size=SIZE):
    """Empty the scene and set up light, camera and output for the previews."""
    import bpy

    for obj in list(scene.objects):
        bpy.data.objects.remove(obj)
    if _engine(scene) == "CYCLES":
        scene.cycles.samples = SAMPLES
    else:
        scene.eevee.taa_render_samples = SAMPLES
    render = scene.render
    render.resolution_x = render.resolution_y = size
    render.resolution_percentage = 100
    render.film_transparent = True
    render.image_settings.file_format = "PNG"
    render.image_settings.color_mode = "RGBA"
    world = bpy.data.worlds.new("cs.chicken preview")
    world.color = (0.45, 0.47, 0.5)
    scene.world = world
    sun = bpy.data.objects.new("Key", bpy.data.lights.new("Key", "SUN"))
    sun.data.energy = 3.5
    sun.data.angle = math.radians(8)
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(-30))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    cam.data.lens = LENS
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam


def frame(cam, objects):
    """Place ``cam`` so the bounding sphere of ``objects`` fills the image."""
    from mathutils import Vector

    corners = [obj.matrix_world @ Vector(c) for obj in objects for c in obj.bound_box]
    if not corners:
        return
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    center = (lo + hi) / 2
    radius = max((c - center).length for c in corners) or 1.0
    fov = 2 * math.atan(cam.data.sensor_width / 2 / cam.data.lens)
    az, el = math.radians(AZIMUTH), math.radians(ELEVATION)
    direction = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    rot = (-direction).to_track_quat("-Z", "Y")
    # fit the bounding box corners as seen from the camera (tighter than the
    # bounding sphere for tall chickens): distance per corner where it just
    # touches the image border, the largest wins
    inv = rot.to_matrix().inverted()
    tan = math.tan(fov / 2)
    dist = 0.0
    for c in corners:
        local = inv @ (c - center)  # camera space, looking down -Z
        dist = max(dist, max(abs(local.x), abs(local.y)) / tan + local.z)
    dist = (dist or radius) * MARGIN
    cam.location = center + direction * dist
    cam.rotation_euler = rot.to_euler()
    cam.data.clip_start = dist / 100
    cam.data.clip_end = dist * 10


def render_all(library, out_dir=None, size=SIZE, missing_only=True, ids=None, log=print):
    """Render the previews of the catalog in ``library`` into ``out_dir``
    (default ``<library>/previews``). Returns the number of images written."""
    import bpy

    from . import utils
    from .library import catalog as C
    from .library import registry
    from .ops import spawn

    out_dir = out_dir or os.path.join(library, C.PREVIEW_DIR)
    cat, errors = C.load([library])
    for err in errors:
        log(f"warning: {err}")
    todo = [c for c in cat if c.complete and (ids is None or c.id in ids)
            and not (missing_only and os.path.isfile(os.path.join(out_dir, f"{c.id}.png")))]
    if not todo:
        return 0
    utils.CORE_LIBRARY_DIR = library
    registry.refresh()
    scene = bpy.context.scene
    cam = setup_scene(scene, size)
    os.makedirs(out_dir, exist_ok=True)
    done = 0
    for i, chicken in enumerate(todo, 1):
        try:
            root, _warnings = spawn.create_chicken(bpy.context, registry.get(chicken.id), seed=0,
                                                   location=(0, 0, 0), rotation=0.0)
        except RuntimeError as exc:
            log(f"[{i}/{len(todo)}] {chicken.id}: {exc}")
            continue
        bpy.context.view_layer.update()
        frame(cam, [o for o in utils.chicken_parts(root) if o.type == "MESH"])
        scene.render.filepath = os.path.join(out_dir, f"{chicken.id}.png")
        bpy.ops.render.render(write_still=True)
        spawn.delete_chicken(root)
        done += 1
        log(f"[{i}/{len(todo)}] {chicken.label}")
    return done


def command(library, missing_only=True, size=SIZE, blender=None):
    """Command line that renders the previews of ``library`` in a background Blender."""
    if blender is None:
        import bpy
        blender = bpy.app.binary_path
    cmd = [blender, "-b", "--factory-startup", "--python-exit-code", "1",
           "--python", os.path.abspath(__file__), "--", library, "--size", str(int(size))]
    if not missing_only:
        cmd.append("--all")
    return cmd


def start(library, missing_only=True):
    """Start the background render, returns the process."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(command(library, missing_only), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=flags)


def main(argv):
    import argparse
    import importlib

    import addon_utils

    ap = argparse.ArgumentParser(prog="preview_render")
    ap.add_argument("library")
    ap.add_argument("--all", action="store_true", help="render every preview, not only missing ones")
    ap.add_argument("--size", type=int, default=SIZE)
    args = ap.parse_args(argv)
    # Run as a script: import the package next to this file under its name.
    package_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(package_dir))
    name = os.path.basename(package_dir)
    addon_utils.enable(name, default_set=False)
    module = importlib.import_module(name + ".preview_render")
    count = module.render_all(os.path.abspath(args.library), size=args.size, missing_only=not args.all,
                              log=lambda text: print("cs.chicken previews:", text, flush=True))
    print(f"cs.chicken previews: {count} rendered", flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
