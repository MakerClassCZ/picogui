# picogui_glyph: software glyph rasteriser + bounded cache, shared by the software backends
# (picogui_rgb directly, and picogui_mono + picogui_fb via picogui_dispbase). It lives in its own tiny
# module so a mono build does NOT pull the whole
# RGB565 strip backend just to reach the rasteriser. The picogame backend renders text in C and needs
# none of this.
#
# One flat fw*fh `bytes` (row-major, 1 = foreground) per code point, keyed by code point alone and
# cleared on a font change, so the cache is bounded by the font's set; missing glyphs share one blank
# and are not per-cp cached.
_BBOX = {}                                          # font -> (fw, fh), memoized (avoids per-text tuples)
_GLYPHS = {}
_GLYPH_FONT = None
_BLANK = None                                       # shared blank glyph for missing code points


def _bbox(font):
    b = _BBOX.get(font)
    if b is None:
        bb = font.get_bounding_box()
        b = (bb[0], bb[1])
        _BBOX[font] = b
    return b


def clear_glyph_cache():
    global _GLYPH_FONT, _BLANK
    _GLYPHS.clear()
    _BBOX.clear()                                    # also drop the bbox map: its keys hold font objects
    _GLYPH_FONT = None
    _BLANK = None


def _glyph_flat(font, cp, fw, fh):
    """Flat fw*fh `bytes` (row-major, 1=fg) for code point `cp`; rasterised once then cached."""
    global _GLYPH_FONT, _BLANK
    if font is not _GLYPH_FONT:
        _GLYPHS.clear()
        _BBOX.clear()                                # a font change drops the old cache, blank AND bbox
        _BLANK = None                                # memo, so old font objects aren't pinned
        _GLYPH_FONT = font
    flat = _GLYPHS.get(cp)
    if flat is not None:
        return flat
    g = font.get_glyph(cp)
    if g is None:
        if _BLANK is None:
            _BLANK = bytes(fw * fh)                  # missing glyph: shared blank, not per-cp cached
        return _BLANK
    sheet = g.bitmap
    tiles_per_row = sheet.width // fw
    ti = g.tile_index
    tx = (ti % tiles_per_row) * fw
    ty = (ti // tiles_per_row) * fh
    b = bytearray(fw * fh)
    p = 0
    for gy in range(fh):
        sy = ty + gy
        for gx in range(fw):
            if sheet[tx + gx, sy]:
                b[p] = 1
            p += 1
    flat = bytes(b)
    _GLYPHS[cp] = flat
    return flat
