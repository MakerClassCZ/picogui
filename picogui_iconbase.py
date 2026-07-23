# picogui_iconbase: just the lightweight Icon type. Kept separate from the built-in catalogue
# (picogui_icons) so a module that only needs to *accept* an Icon (e.g. picogui_grid) can import the
# type without constructing the whole pictogram dictionary into RAM.


class Icon:
    """A small pictogram: a mask (rows of '#'/'.') drawn in the theme colour, or a backend bitmap
    blitted as-is. Replace a built-in: ICONS["memo"] = Icon(mask=[...]) or Icon(bitmap=bmp)."""
    def __init__(self, mask=None, bitmap=None):
        self.bitmap = bitmap
        if mask:
            self.w = len(mask[0])
            self.h = len(mask)
            # one int bitmask per row (MSB = x 0), so a mask costs h small ints, not w*h tuples
            self.rows = tuple(int(row.replace(".", "0").replace("#", "1"), 2) for row in mask)
        else:
            self.w = bitmap.width if bitmap is not None else 0   # so callers can lay a bitmap Icon out
            self.h = bitmap.height if bitmap is not None else 0
            self.rows = ()

    def draw(self, p, x, y, color):
        if self.bitmap is not None:
            p.blit(self.bitmap, x, y)
            return
        top = self.w - 1
        for dy, bits in enumerate(self.rows):
            if bits:
                for dx in range(self.w):
                    if bits & (1 << (top - dx)):
                        p.pixel(x + dx, y + dy, color)
