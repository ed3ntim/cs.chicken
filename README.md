# cs.chicken

Blender add-on that spawns the CS2 chickens and eggs (the pets: egg, chick
and every breed with its color variants) as 3D models with their materials.
Target: Blender 5.2, compatible back to 4.5.

**[⬇ Download cs_chicken.zip (latest release)](https://github.com/ed3ntim/cs.chicken/releases/latest/download/cs_chicken.zip)**
(the add-on only; the CS2 chickens are exported from your own game install,
see [CS2 chickens](#cs2-chickens))

## Installation

1. Download [`cs_chicken.zip`](https://github.com/ed3ntim/cs.chicken/releases/latest/download/cs_chicken.zip)
   (all versions: [Releases](https://github.com/ed3ntim/cs.chicken/releases)).
2. Blender: *Edit > Preferences > Get Extensions > ⌄ > Install from Disk...*
   and pick the zip (drag & drop onto the Blender window works too).
3. 3D Viewport sidebar (`N`), tab **cs.chicken**.

To remove the add-on: *Preferences > Add-ons > cs.chicken > Uninstall
cs.chicken*. Chickens already placed in your files stay as they are.

## CS2 chickens

Valve's models and textures are copyrighted game assets and are not part
of this repository or the release. `tools/export_cs2_chickens.py` exports
them from **your own** CS2 installation with
[Source2Viewer](https://github.com/ValveResourceFormat/ValveResourceFormat):

```
python tools/export_cs2_chickens.py --out D:/cs2_chickens --download-s2v
```

Then set *Preferences > Add-ons > cs.chicken > Chicken Library Folder* to
the `--out` folder. After a CS2 update simply run the export again.

The export also renders a preview image of every entry
(`<out>/previews`) with Blender in the background (found automatically,
or `--blender <path>`, `--no-previews` to skip). CS2 only has an
inventory image of the egg. Missing previews can be rendered later with
*Render Previews* in the preferences or in the Library panel.

What you get (CS2 state 2026-11): the egg, the chick, the Catalana, Silkie
and Polish chickens with all their color variants (39 entries), plus the
hatching egg, the roasted chicken and the dead chicken prop.

## Usage

Sidebar tab **cs.chicken**:

- **Library**: search, filter by kind and breed, pick an entry; the box
  below shows its kind, breed and preview image.
- **Placement**: scale, random rotation, appearance seed and *Spawn at
  Cursor*. Seed 0 is the original material (the variant as Valve
  authored it, the colors it is named after), any other seed rolls hue,
  saturation, brightness, iridescence and feather pattern like the pet
  seed in the game; *Random Appearance* gives every spawn its own seed.
- **Active Chicken**: find it in the library (magnifier), switch the variant, change the seed or each
  appearance input (hue, brightness, speckles ...) by hand, set the
  **Age** of the chick (scales it like CS2 from just hatched to almost a
  pullet), and
  **Remove Chicken** (deletes rig, meshes and its own materials).

The chickens come with their armature (117 bones), in rest pose.
Animation is planned through cs.anim, which uses the add-on's API
(`cs_chicken/api.py`).

The chick's fluff is made of alpha-tested cards. Spawning it raises
Cycles' *Transparent* light-path bounces to 128 (never lowers them), with
the default of 8 the fluff turns dark between the cards.

For demos, `bpy.ops.cs_chicken.spawn_variants()` (F3: *Spawn All
Variants*) lines up every color variant of the selected breed.

## Development

```
blender -b --factory-startup --python tests/run_tests.py
python tools/build_zip.py                                # code-only zip
python tools/build_zip.py --with-chickens D:/cs2_chickens # personal full zip, never share
```

The test library in `tests/fixtures/library` is made from scratch by
`tests/fixtures/generate_fixtures.py` (no game assets).

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md), Copyright 2026 ed3n.
Free for noncommercial use. Any commercial use needs a written agreement,
see [COMMERCIAL.md](COMMERCIAL.md). Contact: contact@ed3n.gallery
