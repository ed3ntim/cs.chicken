# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 ed3n
"""The loaded catalog (lazy, cached), the filtered view for the UI list and
the preview icons."""

from .. import utils
from . import catalog as C

_catalog = None
_errors = []
_view = []          # ids shown in the UI list (filtered)
_view_key = None
_previews = None    # bpy.utils.previews collection, keyed by chicken id


def get_catalog():
    global _catalog, _errors
    if _catalog is None:
        _catalog, _errors = C.load(utils.library_dirs())
        for err in _errors:
            utils.log.warning("cs.chicken: %s", err)
    return _catalog


def refresh(context=None):
    """Forget the loaded catalog; the next access reads the folders again."""
    global _catalog, _view_key
    _catalog = None
    _view_key = None
    clear_previews()
    return get_catalog()


def errors():
    get_catalog()
    return list(_errors)


def status_text():
    cat = get_catalog()
    if not len(cat):
        return "No chickens loaded: set the library folder (see below)"
    incomplete = sum(1 for c in cat if not c.complete)
    text = f"{len(cat)} chickens and eggs loaded"
    return text + (f", {incomplete} incomplete" if incomplete else "")


def view(search="", kind="ALL", breed="ALL", include_incomplete=True):
    """Ids matching the filters, catalog order (cached per filter state)."""
    global _view, _view_key
    cat = get_catalog()
    key = (id(cat), search, kind, breed, include_incomplete)
    if key != _view_key:
        _view = [c.id for c in cat
                 if (kind == "ALL" or c.kind == kind)
                 and (breed == "ALL" or c.breed == breed)
                 and (include_incomplete or c.complete)
                 and c.matches(search)]
        _view_key = key
    return _view


def get(chicken_id):
    return get_catalog().get(chicken_id)


# ---------------------------------------------------------------------------
# Preview icons
# ---------------------------------------------------------------------------

def preview_icon(chicken):
    """icon_id of the chicken's preview image (0 if none)."""
    if _previews is None or chicken is None:
        return 0
    path = chicken.preview_image
    if not path:
        return 0
    if chicken.id not in _previews:
        try:
            _previews.load(chicken.id, path, "IMAGE")
        except (OSError, KeyError, RuntimeError):
            return 0
    return _previews[chicken.id].icon_id


def clear_previews():
    """Forget the loaded icons (after new previews were rendered)."""
    if _previews is not None:
        _previews.clear()


def register():
    global _previews
    import bpy.utils.previews
    _previews = bpy.utils.previews.new()


def unregister():
    global _previews
    if _previews is not None:
        import bpy.utils.previews
        bpy.utils.previews.remove(_previews)
        _previews = None
