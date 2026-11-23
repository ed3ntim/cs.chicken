# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""csgo_character.vfx -> node group inputs. Pure Python (no bpy).

Texture roles come from the decompiled .vmat (``TextureColor`` ...), where
Source2Viewer already writes every map on its own (e.g. the roughness that
the compiled normal map carries in a channel). One compiled texture is used
directly: ``g_tAnisoGloss`` of materials with ``F_ANISOTROPIC_GLOSS`` (all
grown chickens). Its red channel is the roughness (feathers rough, eyes
glossy); the decompiled ``TextureRoughness`` of those materials is black.

Textures that a .vmat gives as a constant (``"[0.73 0.73 0.73 1]"``) set
the matching group input instead.
"""

from . import catalog as C

NODE_MAIN = "CHICKEN_MAIN"
NODE_DETAIL_UV = "CHICKEN_DETAIL_UV"

# vmat texture key -> (role, colorspace)
TEXTURE_ROLES = {
    "TextureColor": ("COLOR", "sRGB"),
    "TextureNormal": ("NORMAL", "Non-Color"),
    "TextureRoughness": ("ROUGHNESS", "Non-Color"),
    "g_tAnisoGloss": ("ANISO", "Non-Color"),
    "TextureAmbientOcclusion": ("AO", "Non-Color"),
    "TextureTintMask": ("TINT", "Non-Color"),
    "TextureDetail": ("DETAIL", "sRGB"),
    "TextureIridescentMask": ("IRIDESCENCE", "Non-Color"),
    # Source2Viewer writes the alpha of TextureColor into its own file when
    # it decompiles a material with F_ALPHA_TEST (chick fluff: *_trans.png).
    "TextureTranslucency": ("ALPHA", "Non-Color"),
}

# Constant textures -> group input (first component for float inputs).
CONSTANT_INPUTS = {
    "TextureColor": ("Color", "COLOR"),
    "TextureRoughness": ("Roughness", "FLOAT"),
    "TextureAmbientOcclusion": ("Ambient Occlusion", "FLOAT"),
    "TextureTintMask": ("Tint Mask", "FLOAT"),
    "TextureIridescentMask": ("Iridescence Mask", "FLOAT"),
}

# Scalar params -> main group input.
FLOAT_INPUTS = {
    "g_fHueShift": "Hue Shift",
    "g_fSaturation": "Saturation",
    "g_fBrightness": "Brightness",
    "g_fContrast": "Contrast",
    "g_flModelTintAmount": "Tint Amount",
    "g_fDetailBlendFactor": "Detail Blend",
    "g_nMaskDetailTextureByTintMask": "Detail Mask Mode",
    "g_fDetailHueShift": "Detail Hue Shift",
    "g_fDetailSaturation": "Detail Saturation",
    "g_fDetailBrightness": "Detail Brightness",
    "g_fDetailContrast": "Detail Contrast",
    "g_fTextureRoughnessBrightness": "Roughness Brightness",
    "g_fTextureRoughnessContrast": "Roughness Contrast",
    "g_bMaskRoughnessAdjustmentsByTintMask": "Roughness By Tint Mask",
    "g_flIridescentStrength": "Iridescence",
    "g_flIridescentHueShift": "Iridescence Hue",
    "g_flIridescentFresnelStrength": "Iridescence Fresnel",
    "g_flSheenScale": "Sheen",
    "g_flAlphaTestReference": "Alpha Clip",
}

COLOR_INPUTS = {
    "g_vColorTint": "Color Tint",
    "g_flSheenTintColor": "Sheen Tint",
}

# Flags that switch a feature on (input = 1) or leave it at 0.
FLAG_INPUTS = {
    "F_IRIDESCENCE": "Use Iridescence",
    "F_CLOTH_SHADING": "Use Sheen",
    "F_ALPHA_TEST": "Use Alpha Clip",
    "F_ANISOTROPIC_GLOSS": "Use Aniso Gloss",
    "F_TINT_MASK": "Use Tint Mask",
    "F_DO_NOT_CAST_SHADOWS": "No Shadows",
    "F_DONT_FLIP_BACKFACE_NORMALS": "Keep Backface Normals",
}

# Defaults where a param is missing from the material.
FLAG_DEFAULTS = {name: 0.0 for name in FLAG_INPUTS.values()}


def _first(value):
    if isinstance(value, (list, tuple)):
        return float(value[0]) if value else 0.0
    return float(value)


def _color(value):
    if isinstance(value, (list, tuple)):
        vals = [float(v) for v in value[:3]] + [0.0] * (3 - min(3, len(value)))
        return (vals[0], vals[1], vals[2], 1.0)
    v = float(value)
    return (v, v, v, 1.0)


def node_values(spec, env=None):
    """{(node name, input name): value} for a material spec with its
    appearance inputs ``env`` ({"$egg_hue": 0.3, ...}) evaluated; ``env``
    None for the original material without DynamicParams."""
    params = C.evaluate_params(spec, env)
    out = {(NODE_MAIN, name): value for name, value in FLAG_DEFAULTS.items()}
    for flag, name in FLAG_INPUTS.items():
        if spec.flag(flag) or (flag in params and _first(params[flag]) != 0):
            out[(NODE_MAIN, name)] = 1.0
    for key, name in FLOAT_INPUTS.items():
        if key in params:
            try:
                out[(NODE_MAIN, name)] = _first(params[key])
            except (TypeError, ValueError):
                pass
    for key, name in COLOR_INPUTS.items():
        if key in params:
            try:
                out[(NODE_MAIN, name)] = _color(params[key])
            except (TypeError, ValueError):
                pass
    for key, (name, kind) in CONSTANT_INPUTS.items():
        if key in spec.constants and key not in spec.textures:
            value = spec.constants[key]
            out[(NODE_MAIN, name)] = _color(value) if kind == "COLOR" else _first(value)
    # Detail UV transform
    scale = params.get("g_vDetailTexCoordScale")
    offset = params.get("g_vDetailTexCoordOffset")
    if isinstance(scale, (list, tuple)) and len(scale) >= 2:
        out[(NODE_DETAIL_UV, "Scale X")] = float(scale[0])
        out[(NODE_DETAIL_UV, "Scale Y")] = float(scale[1])
    if isinstance(offset, (list, tuple)) and len(offset) >= 2:
        out[(NODE_DETAIL_UV, "Offset X")] = float(offset[0])
        out[(NODE_DETAIL_UV, "Offset Y")] = float(offset[1])
    if "g_flDetailTexCoordRotation" in params:
        out[(NODE_DETAIL_UV, "Rotation")] = _first(params["g_flDetailTexCoordRotation"])
    return out


def texture_role(key):
    return TEXTURE_ROLES.get(key)


def parse_constant(text):
    """'[0.5 0.5 0.5 0]' -> [0.5, 0.5, 0.5, 0.0], else None."""
    text = str(text).strip()
    if not (text.startswith("[") and text.endswith("]")):
        return None
    try:
        return [float(x) for x in text[1:-1].split()]
    except ValueError:
        return None
