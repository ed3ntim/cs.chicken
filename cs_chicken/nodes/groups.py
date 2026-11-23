# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""Shader node groups for CS2 chicken and egg materials.

* ``CS2 Chicken Character``  csgo_character.vfx as the pets use it
* ``CS2 Chicken UV``         UV transform for the detail texture

Groups take *texture samples* as inputs, material.py creates the image
nodes. Input names match library/shading.py.

csgo_character.vfx as implemented here (approximation, Valve does not
document the shader):

* color adjustments (hue in degrees, saturation, brightness, contrast)
  apply inside the tint mask (everywhere without F_TINT_MASK)
* the detail texture (face details, egg speckles) gets its own
  adjustments and is multiplied in by ``g_fDetailBlendFactor``; mode
  ``g_nMaskDetailTextureByTintMask``: 0 everywhere, 1 inside the tint
  mask, 2 outside of it
* roughness: decompiled roughness map, or with F_ANISOTROPIC_GLOSS the
  mean of R and G of ``g_tAnisoGloss`` (roughness along/across the
  feathers), then brightness/contrast
* iridescence (feather sheen of the grown chickens): thin film inside the
  iridescence mask
* cloth shading (chick fluff): Principled sheen
* alpha test (fluff cards): cut against ``g_flAlphaTestReference`` with a
  soft edge of ``Alpha Softness`` (CS2 smooths the cut with MSAA/alpha to
  coverage; a hard cut looks stair-stepped in renders)
* F_DO_NOT_CAST_SHADOWS (fluff cards): transparent for shadow rays
* ``Shadow Bias``: surfaces closer than that do not shadow (CS2 shadow bias)
* F_DONT_FLIP_BACKFACE_NORMALS (fluff cards): back faces keep the normal
* alpha-tested cards also get ``Card Translucency`` (Translucent BSDF)
"""

import bpy

from .builder import GroupBuilder, principled, set_bsdf

# Bump when group contents change; outdated groups are renamed (existing
# materials keep working) and rebuilt.
GROUP_VERSION = 9
VERSION_KEY = "cs_chicken_version"

CHARACTER_GROUP = "CS2 Chicken Character"
UV_GROUP = "CS2 Chicken UV"

FLAT_NORMAL = (0.5, 0.5, 1.0, 1.0)
# Principled sheen weight per unit of g_flSheenScale (chick: 3 -> 0.3).
# Higher values wash the chick's yellow out with the mint sheen tint.
SHEEN_PER_SCALE = 0.1
# Shadow bias in model units (scaled with the object). The chick's fluff
# card roots lie up to ~5 units * 1e-3 under the skin; a wing or head
# shadow spans centimeters. 0.025 = 1 cm on a just hatched chick.
SHADOW_BIAS = 0.025
WHITE = (1.0, 1.0, 1.0, 1.0)


def _hue_shift(b, color, degrees, saturation=1.0, x=None, y=0):
    """Hue/Saturation node with the hue given in degrees (wraps around)."""
    hue = b.math("FRACT", b.math("ADD", b.math("DIVIDE", degrees, 360.0, x=x, y=y), 0.5, x=x, y=y), x=x, y=y)
    n = b.node("ShaderNodeHueSaturation", x, y)
    b.set_or_link(n, "Hue", hue)
    b.set_or_link(n, "Saturation", saturation)
    b.set_or_link(n, "Value", 1.0)
    b.set_or_link(n, "Fac", 1.0)
    b.set_or_link(n, "Color", color)
    return n.outputs["Color"]


# Interference colors over the "thickness" (Newton series, one period):
# frontal teal, then towards thinner film (grazing view) blue and violet.
IRIDESCENCE_RAMP = (
    (0.00, (0.05, 0.62, 0.55)),   # teal
    (0.15, (0.45, 0.72, 0.10)),   # yellow green
    (0.30, (0.85, 0.55, 0.10)),   # gold
    (0.45, (0.75, 0.12, 0.45)),   # magenta
    (0.60, (0.40, 0.18, 0.80)),   # violet
    (0.78, (0.10, 0.30, 0.85)),   # blue
    (1.00, (0.05, 0.62, 0.55)),   # teal (wraps)
)


IRIDESCENCE_GAIN = 0.6         # amount per strength * mask * (1 - luminance)^3
IRIDESCENCE_BRIGHTNESS = 4.5   # interference color = ramp * min(1, luminance * this)


def _iridescence(b, col, strength, mask, hue, fresnel, use, y=1500):
    """CS2 feather iridescence (approximation, the shader is not public).

    In the game it recolors the feathers themselves (Polish Blue: teal
    body, yellow-green neck, violet edges), so it blends into the base
    color instead of only tinting the specular like a thin film:

    * phase = frac(g_flIridescentHueShift - g_flIridescentFresnelStrength * facing)
      through an interference ramp (teal frontal, violet at grazing angles)
    * amount = 0.6 * strength * mask * (1 - luminance)^3: structural color
      shows on dark feathers, hardly on white ones (Silkie White)
    * the ramp color is scaled by the base luminance, so the feather
      drawing (dark scale outlines) stays
    """
    b.column(-300)
    weight = b.node("ShaderNodeLayerWeight", y=y)
    b.set_or_link(weight, "Blend", 0.5)
    phase = b.math("FRACT", b.math("SUBTRACT", hue, b.math("MULTIPLY", fresnel, (weight, "Facing"), y=y),
                                   y=y), y=y)
    b.column(-150)
    ramp = b.node("ShaderNodeValToRGB", y=y)
    elements = ramp.color_ramp.elements
    while len(elements) > 1:
        elements.remove(elements[-1])
    elements[0].position, elements[0].color = IRIDESCENCE_RAMP[0][0], (*IRIDESCENCE_RAMP[0][1], 1.0)
    for pos, rgb in IRIDESCENCE_RAMP[1:]:
        el = elements.new(pos)
        el.color = (*rgb, 1.0)
    b.set_or_link(ramp, "Fac", phase)
    lum = b.node("ShaderNodeRGBToBW", y=y - 200)
    b.set_or_link(lum, "Color", col)
    dark = b.math("SUBTRACT", 1.0, lum.outputs[0], y=y - 250)
    amount = b.math("MULTIPLY", b.math("MULTIPLY", strength, mask, y=y - 200),
                    b.math("POWER", dark, 3.0, y=y - 250), y=y - 200)
    amount = b.math("MULTIPLY", b.math("MULTIPLY", amount, IRIDESCENCE_GAIN, y=y - 200), use, y=y - 200, clamp=True)
    # keep the feather drawing: the interference color follows the base
    # brightness (dark scale outlines stay dark)
    shade = b.math("MULTIPLY", lum.outputs[0], IRIDESCENCE_BRIGHTNESS, y=y - 300, clamp=True)
    tinted = b.vmath("SCALE", ramp.outputs["Color"], y=y - 100, scale=shade)
    b.column(50)
    return b.mix("RGBA", amount, col, tinted, y=y)


def _contrast(b, value, contrast, kind="FLOAT", x=None, y=0):
    """(value - 0.5) * contrast + 0.5 for floats or colors."""
    if kind == "FLOAT":
        return b.math("ADD", b.math("MULTIPLY", b.math("SUBTRACT", value, 0.5, x=x, y=y), contrast, x=x, y=y),
                      0.5, x=x, y=y)
    centered = b.vmath("SUBTRACT", value, (0.5, 0.5, 0.5), x=x, y=y)
    return b.vmath("ADD", b.vmath("SCALE", centered, scale=contrast, x=x, y=y), (0.5, 0.5, 0.5), x=x, y=y)


def _adjust(b, color, hue, sat, bright, contrast, y=0):
    """CS2 color adjustments: hue/saturation, brightness, contrast."""
    shifted = _hue_shift(b, color, hue, saturation=sat, y=y)
    brightened = b.vmath("SCALE", shifted, scale=bright, y=y)
    return _contrast(b, brightened, contrast, kind="COLOR", y=y)


# ---------------------------------------------------------------------------
# UV helper
# ---------------------------------------------------------------------------

def _build_uv(tree):
    b = GroupBuilder(tree)
    uv = b.input("UV", "VECTOR", hide_value=True, description="Texture coordinates (UV map)")
    sx = b.input("Scale X", default=1.0)
    sy = b.input("Scale Y", default=1.0)
    ox = b.input("Offset X", default=0.0)
    oy = b.input("Offset Y", default=0.0)
    rot = b.input("Rotation", default=0.0, description="Rotation around the UV center in degrees")
    out = b.output("Vector", "VECTOR")

    # CS2 texture coordinates run V downwards, Blender's (glTF import) upwards:
    # transform in CS2 space, (u, v) -> (u, 1 - v) before and after.
    b.column(-1150)
    centered = b.vmath("MULTIPLY", b.vmath("SUBTRACT", uv, (0.5, 0.5, 0.0)), (1.0, -1.0, 1.0))
    b.column(-650)
    rotate = b.node("ShaderNodeVectorRotate", rotation_type="Z_AXIS")
    b.set_or_link(rotate, "Vector", centered)
    b.set_or_link(rotate, "Angle", b.math("RADIANS", rot))
    b.column(-400)
    scaled = b.vmath("MULTIPLY", rotate.outputs[0], b.combine(sx, sy, 1.0))
    b.column(-150)
    shifted = b.vmath("ADD", scaled, b.combine(b.math("ADD", ox, 0.5), b.math("ADD", oy, 0.5), 0.0))
    b.column(100)
    back = b.vmath("ADD", b.vmath("MULTIPLY", shifted, (1.0, -1.0, 1.0)), (0.0, 1.0, 0.0))
    b.link(back, out)


# ---------------------------------------------------------------------------
# csgo_character.vfx
# ---------------------------------------------------------------------------

def _build_character(tree):
    b = GroupBuilder(tree)
    # Texture samples (or constants)
    color = b.input("Color", "COLOR", default=(0.8, 0.8, 0.8, 1.0), description="TextureColor")
    alpha = b.input("Alpha", default=1.0, lo=0.0, hi=1.0, factor=True, description="TextureColor alpha")
    normal = b.input("Normal Map", "COLOR", default=FLAT_NORMAL, description="TextureNormal (tangent space)")
    rough_tex = b.input("Roughness", default=0.6, lo=0.0, hi=1.0, factor=True, description="TextureRoughness")
    aniso = b.input("Aniso Gloss", "COLOR", default=(0.6, 0.5, 0.5, 1.0),
                    description="g_tAnisoGloss: mean of R and G as roughness")
    ao = b.input("Ambient Occlusion", default=1.0, lo=0.0, hi=1.0, factor=True)
    tint = b.input("Tint Mask", default=1.0, lo=0.0, hi=1.0, factor=True,
                   description="Where the color adjustments apply")
    detail = b.input("Detail", "COLOR", default=WHITE, description="TextureDetail, multiplied into the color")
    irid_mask = b.input("Iridescence Mask", default=0.0, lo=0.0, hi=1.0, factor=True,
                        description="TextureIridescentMask")
    # Switches
    use_tint = b.input("Use Tint Mask", default=0.0, lo=0.0, hi=1.0, factor=True, description="F_TINT_MASK")
    use_aniso = b.input("Use Aniso Gloss", default=0.0, lo=0.0, hi=1.0, factor=True,
                        description="F_ANISOTROPIC_GLOSS: roughness from Aniso Gloss")
    use_irid = b.input("Use Iridescence", default=0.0, lo=0.0, hi=1.0, factor=True, description="F_IRIDESCENCE")
    use_sheen = b.input("Use Sheen", default=0.0, lo=0.0, hi=1.0, factor=True, description="F_CLOTH_SHADING")
    use_clip = b.input("Use Alpha Clip", default=0.0, lo=0.0, hi=1.0, factor=True, description="F_ALPHA_TEST")
    keep_back = b.input("Keep Backface Normals", default=0.0, lo=0.0, hi=1.0, factor=True,
                        description="F_DONT_FLIP_BACKFACE_NORMALS: back faces shade with the front normal")
    no_shadow = b.input("No Shadows", default=0.0, lo=0.0, hi=1.0, factor=True,
                        description="F_DO_NOT_CAST_SHADOWS: transparent for shadow rays")
    # Parameters
    hue = b.input("Hue Shift", default=0.0, lo=-3600.0, hi=3600.0, description="g_fHueShift in degrees")
    sat = b.input("Saturation", default=1.0, lo=0.0, hi=10.0, description="g_fSaturation")
    bright = b.input("Brightness", default=1.0, lo=0.0, hi=10.0, description="g_fBrightness")
    contrast = b.input("Contrast", default=1.0, lo=0.0, hi=10.0, description="g_fContrast")
    color_tint = b.input("Color Tint", "COLOR", default=WHITE, description="g_vColorTint")
    tint_amount = b.input("Tint Amount", default=1.0, lo=0.0, hi=1.0, factor=True,
                          description="g_flModelTintAmount")
    d_blend = b.input("Detail Blend", default=0.0, lo=0.0, hi=1.0, factor=True,
                      description="g_fDetailBlendFactor")
    d_mode = b.input("Detail Mask Mode", default=0.0, lo=0.0, hi=2.0,
                     description="g_nMaskDetailTextureByTintMask: 0 everywhere, 1 inside, 2 outside the tint mask")
    d_hue = b.input("Detail Hue Shift", default=0.0, lo=-3600.0, hi=3600.0, description="g_fDetailHueShift")
    d_sat = b.input("Detail Saturation", default=1.0, lo=0.0, hi=10.0, description="g_fDetailSaturation")
    d_bright = b.input("Detail Brightness", default=1.0, lo=0.0, hi=10.0, description="g_fDetailBrightness")
    d_contrast = b.input("Detail Contrast", default=1.0, lo=0.0, hi=10.0, description="g_fDetailContrast")
    r_bright = b.input("Roughness Brightness", default=1.0, lo=0.0, hi=10.0,
                       description="g_fTextureRoughnessBrightness")
    r_contrast = b.input("Roughness Contrast", default=1.0, lo=0.0, hi=10.0,
                         description="g_fTextureRoughnessContrast")
    r_by_tint = b.input("Roughness By Tint Mask", default=0.0, lo=0.0, hi=1.0, factor=True,
                        description="g_bMaskRoughnessAdjustmentsByTintMask")
    irid = b.input("Iridescence", default=0.0, lo=0.0, hi=4.0, description="g_flIridescentStrength")
    irid_hue = b.input("Iridescence Hue", default=0.5, lo=-4.0, hi=4.0, description="g_flIridescentHueShift")
    irid_fresnel = b.input("Iridescence Fresnel", default=1.0, lo=0.0, hi=10.0,
                           description="g_flIridescentFresnelStrength")
    sheen = b.input("Sheen", default=1.0, lo=0.0, hi=10.0, description="g_flSheenScale")
    sheen_tint = b.input("Sheen Tint", "COLOR", default=WHITE, description="g_flSheenTintColor")
    clip = b.input("Alpha Clip", default=0.5, lo=0.0, hi=1.0, factor=True, description="g_flAlphaTestReference")
    card_trans = b.input("Card Translucency", default=0.5, lo=0.0, hi=1.0, factor=True,
                         description="Share of light through alpha-tested cards (fluff), only with Use Alpha Clip")
    bias = b.input("Shadow Bias", default=SHADOW_BIAS, lo=0.0, hi=1.0, description=(
        "Shadow rays pass the surface closer than this (model units): CS2's shadow bias. "
        "Fluff cards sit a hair under the skin and would be shadowed by it in Cycles"))
    soft = b.input("Alpha Softness", default=0.15, lo=0.0, hi=1.0, factor=True,
                   description="Width of the soft edge around Alpha Clip, 0 = hard cut")
    ao_strength = b.input("AO Strength", default=1.0, lo=0.0, hi=1.0, factor=True)
    n_strength = b.input("Normal Strength", default=1.0, lo=0.0, hi=10.0)
    out = b.output("Shader")

    # -- color -------------------------------------------------------------------
    b.column(-1000)
    mask = b.mix("FLOAT", use_tint, 1.0, tint, y=600)
    b.column(-800)
    adjusted = _adjust(b, color, hue, sat, bright, contrast, y=300)
    b.column(-500)
    col = b.mix("RGBA", mask, color, adjusted, y=300)
    col = b.mix("RGBA", b.math("MULTIPLY", tint_amount, mask, y=150), col, color_tint, blend="MULTIPLY", y=300)

    # Detail: own adjustments, masked by mode 0 / 1 / 2.
    b.column(-800)
    det = _adjust(b, detail, d_hue, d_sat, d_bright, d_contrast, y=0)
    b.column(-600)
    inside = b.math("COMPARE", d_mode, 1.0, y=800)
    outside = b.math("COMPARE", d_mode, 2.0, y=700)
    d_mask = b.math("SUBTRACT", 1.0, b.math("ADD", b.math("MULTIPLY", inside, b.math("SUBTRACT", 1.0, mask, y=900),
                                                           y=850),
                                            b.math("MULTIPLY", outside, mask, y=750), y=800), y=800, clamp=True)
    b.column(-350)
    col = b.mix("RGBA", b.math("MULTIPLY", d_blend, d_mask, y=600), col, det, blend="MULTIPLY", y=300)
    col = b.mix("RGBA", ao_strength, col, ao, blend="MULTIPLY", y=300)
    col = _iridescence(b, col, irid, irid_mask, irid_hue, irid_fresnel, use_irid)

    # -- roughness -----------------------------------------------------------------
    b.column(-900)
    ar, ag, _ab = b.separate_color(aniso, y=-500)
    # R and G are the roughness along and across the feather direction. R
    # alone makes the neck hackles (R low, G high) glossy like plastic;
    # their mean stands in for the anisotropic highlight (isotropic).
    a_rough = b.math("MULTIPLY", b.math("ADD", ar, ag, y=-550), 0.5, y=-550)
    b.column(-700)
    rough = b.mix("FLOAT", use_aniso, rough_tex, a_rough, y=-500)
    r_adj = _contrast(b, b.math("MULTIPLY", rough, r_bright, y=-650), r_contrast, y=-650)
    r_mask = b.mix("FLOAT", r_by_tint, 1.0, mask, y=-800)
    b.column(-400)
    rough = b.math("MINIMUM", b.math("MAXIMUM", b.mix("FLOAT", r_mask, rough, r_adj, y=-600), 0.0, y=-600),
                   1.0, y=-600)

    # -- normal ----------------------------------------------------------------------
    b.column(-300)
    nmap = b.node("ShaderNodeNormalMap", y=-300)
    b.set_or_link(nmap, "Strength", n_strength)
    b.set_or_link(nmap, "Color", normal)
    # F_DONT_FLIP_BACKFACE_NORMALS: Blender flips the normal on back faces,
    # CS2 keeps it. Fluff cards seen from behind would turn dark otherwise.
    geo = b.node("ShaderNodeNewGeometry", y=-450)
    unflip = b.math("MULTIPLY", geo.outputs["Backfacing"], keep_back, y=-450)
    n_sign = b.math("SUBTRACT", 1.0, b.math("MULTIPLY", unflip, 2.0, y=-450), y=-450)
    shading_normal = b.vmath("SCALE", nmap.outputs[0], y=-350, scale=n_sign)

    # -- sheen -------------------------------------------------------------------------
    sheen_w = b.math("MULTIPLY", use_sheen, b.math("MINIMUM", b.math("MULTIPLY", sheen, SHEEN_PER_SCALE, y=-1400), 1.0, y=-1400),
                     y=-1400)

    bsdf = principled(b, x=300, y=0)
    set_bsdf(b, bsdf, Base_Color=col, Metallic=0.0, Roughness=rough, Normal=shading_normal,
             Sheen_Weight=sheen_w, Sheen_Tint=sheen_tint,
             Sheen_Roughness=0.5)

    # -- fluff cards: translucency -------------------------------------------------------
    # Cycles drops light from the geometric back side of a card even when the
    # (custom) shading normal faces it; CS2 rasterizes and does not. Thin
    # cards let light through, so alpha-tested materials mix in a translucent
    # part: no dark patches where the cards turn away from the light.
    # Added, not mixed: a translucent closure only takes light from behind,
    # so front-lit cards keep their full brightness.
    trans = b.node("ShaderNodeBsdfTranslucent", x=300, y=-250)
    b.set_or_link(trans, "Color", b.vmath("SCALE", col, x=150, y=-300,
                                          scale=b.math("MULTIPLY", use_clip, card_trans, x=0, y=-450)))
    b.set_or_link(trans, "Normal", shading_normal)
    lit = b.node("ShaderNodeAddShader", x=450, y=-100)
    b.link(bsdf.outputs[0], lit.inputs[0])
    b.link(trans.outputs[0], lit.inputs[1])

    # -- alpha test ----------------------------------------------------------------------
    b.column(300)
    edge = b.math("DIVIDE", b.math("SUBTRACT", alpha, clip, y=400), b.math("MAXIMUM", soft, 0.0001, y=450), y=400)
    keep = b.math("ADD", edge, 0.5, y=400, clamp=True)
    visible = b.math("MAXIMUM", keep, b.math("SUBTRACT", 1.0, use_clip, y=500), y=400)
    path = b.node("ShaderNodeLightPath", y=800)
    # shadow rays pass everything with F_DO_NOT_CAST_SHADOWS and any surface
    # within the shadow bias (the skin over the fluff cards' roots)
    unit = b.node("ShaderNodeVectorTransform", y=750, vector_type="VECTOR",
                  convert_from="OBJECT", convert_to="WORLD")
    unit.inputs["Vector"].default_value = (1.0, 0.0, 0.0)
    world_bias = b.math("MULTIPLY", bias, b.vmath("LENGTH", unit.outputs[0], y=750), y=700)
    near = b.math("LESS_THAN", path.outputs["Ray Length"], world_bias, y=700)
    shadow_cut = b.math("MULTIPLY", path.outputs["Is Shadow Ray"],
                        b.math("MAXIMUM", no_shadow, near, y=650), y=600)
    visible = b.math("MULTIPLY", visible, b.math("SUBTRACT", 1.0, shadow_cut, y=600), y=500)
    see = b.node("ShaderNodeBsdfTransparent", x=300, y=300)
    b.column(600)
    final = b.node("ShaderNodeMixShader", y=200)
    b.set_or_link(final, 0, visible)
    b.link(see.outputs[0], final.inputs[1])
    b.link(lit.outputs[0], final.inputs[2])
    b.link(final.outputs[0], out)


_BUILDERS = {
    "UV": (UV_GROUP, _build_uv),
    "CHARACTER": (CHARACTER_GROUP, _build_character),
}


def ensure_group(key):
    """Return the node group for ``key``, building or upgrading it if needed."""
    name, build = _BUILDERS[key]
    tree = bpy.data.node_groups.get(name)
    if tree is not None and tree.get(VERSION_KEY) == GROUP_VERSION:
        return tree
    old = tree
    if old is not None:
        old.name = f"{name} (v{old.get(VERSION_KEY, 0)})"
    tree = bpy.data.node_groups.new(name, "ShaderNodeTree")
    try:
        build(tree)
    except Exception:
        # A half-built group must not count as current.
        bpy.data.node_groups.remove(tree)
        if old is not None:
            old.name = name
        raise
    tree[VERSION_KEY] = GROUP_VERSION
    return tree


def ensure_all():
    return [ensure_group(k) for k in _BUILDERS]
