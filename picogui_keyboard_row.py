# picogui_keyboard_row: a ONE-ROW keyboard (opt-in) for small and round displays, and for rotary input.
#
# Everything lives in a single horizontal strip you scroll through (Apple-TV style): letters, digits,
# symbols, plus three control keys - `^` shift (toggle case), `<` delete, `>` done (save + close). Move
# the cursor with LEFT/RIGHT (or the rotary, which arrives as UP/DOWN) - it wraps - and pick the
# highlighted key with OK / the encoder press. B cancels without saving. Because it needs only
# move + pick, it maps cleanly onto a rotary encoder (rotate = move along the alphabet, press = pick) and
# fits a 128x64 OLED or a round GC9A01 where the grid `picogui_keyboard` can't. Edits a Text field's
# value in place; swap it in with `Text.keyboard = RowKeyboard` (or per field: `fld.keyboard = ...`).
from picogui import View, _font_cw


class RowKeyboard(View):
    """One-row scrolling keyboard. L/R (or rotary U/D) move; A / press pick; B cancels. Controls in the
    strip: `^` shift, `<` delete, `>` done. Customise the typed glyphs via the `chars` argument."""
    CONTROLS = ("^", "<", ">")                        # shift / delete / done - always appended to the strip

    def __init__(self, field, chars=None):
        self.field = field
        # default: lowercase letters, digits, a few config-friendly symbols, and a space (shown as "_")
        self.chars = chars or ("abcdefghijklmnopqrstuvwxyz0123456789 .,-@:/#")
        self.keys = list(self.chars) + list(self.CONTROLS)
        self.buf = field.value
        self.cursor = 0
        self._shift = False

    def focused_adjustable(self):
        return False                                  # so the encoder press() picks (ok), never enters edit

    # -- helpers --------------------------------------------------------------------------------
    def _cased(self, ch):
        return ch.upper() if self._shift and "a" <= ch <= "z" else ch

    def _disp(self, key):                             # the glyph shown for a key
        if key == " ":
            return "_"                                # visible stand-in for space
        if key in self.CONTROLS:
            return key
        return self._cased(key)

    def _label(self, key):                            # descriptive hint for the highlighted key
        if key == "^":
            return "SHIFT (-> abc)" if self._shift else "SHIFT (-> ABC)"
        if key == "<":
            return "delete"
        if key == ">":
            return "done"
        if key == " ":
            return "space"
        return ""

    # -- input ----------------------------------------------------------------------------------
    def key(self, app, k):
        n = len(self.keys)
        if k in ("L", "U"):                           # U/D too: a rotary arrives as UP/DOWN
            self.cursor = (self.cursor - 1) % n
            return True
        if k in ("R", "D"):
            self.cursor = (self.cursor + 1) % n
            return True
        if k == "B":
            return app.pop()                          # cancel, no save
        if k == "A":
            cur = self.keys[self.cursor]
            if cur == "^":
                self._shift = not self._shift
                return True
            if cur == "<":
                if not self.buf:
                    return False                      # backspace on empty: no change
                self.buf = self.buf[:-1]
                return True
            if cur == ">":
                self.field.value = self.buf           # done: commit + close
                if self.field.on_change:
                    self.field.on_change(self.buf)
                app.pop()
                return True
            if len(self.buf) >= self.field.maxlen:    # a typed char, at maxlen: no change
                return False
            self.buf += self._cased(cur)
            return True
        return False

    # -- geometry / draw ------------------------------------------------------------------------
    def _geom(self, th, cw, W, H):
        """A compact block (label + buffer + key strip + hint), VERTICALLY CENTRED so it fits a 64px
        OLED yet also sits mid-face on a round display. Returns (cx, strip-centre-y, slot, box-h, half,
        top). Shared by draw() and hit() so the tap targets match the drawn slots."""
        fh = th.font.get_bounding_box()[1]
        row = fh + 3
        sbox = fh + 6
        top = max(0, (H - (row * 3 + sbox)) // 2)
        cy = top + row * 2 + sbox // 2
        slot = cw + 6
        half = max(1, (W - 4) // slot) // 2
        return W // 2, cy, slot, sbox, half, top, fh, row

    def draw(self, p, W, H):
        th = p.th
        cw = p.cw
        cx, cy, slot, sbox, half, top, fh, row = self._geom(th, cw, W, H)
        p.fill(0, 0, W, H, th.bg)
        # edit buffer (label + value with caret), tail-truncated to the width
        shown = self.buf + "_"
        maxc = max(1, (W - 2 * th.pad) // cw)
        if len(shown) > maxc:
            shown = shown[-maxc:]
        p.ctext(cx, top, self.field.label, th.dim)
        p.ctext(cx, top + row, shown, th.fg)
        # the horizontal key strip: a window of slots centred on the cursor (wraps)
        n = len(self.keys)
        gtop = cy - fh // 2
        for off in range(-half, half + 1):
            idx = (self.cursor + off) % n
            sx = cx + off * slot
            g = self._disp(self.keys[idx])
            if off == 0:                              # highlighted key
                p.fill(sx - slot // 2, cy - sbox // 2, slot, sbox, th.sel_bg)
                p.ctext(sx, gtop, g, th.sel_fg)
            else:                                     # neighbours fade with distance
                p.ctext(sx, gtop, g, th.fg if abs(off) <= 3 else th.dim)
        # a one-line hint: the highlighted control's name, else the standard keys
        lab = self._label(self.keys[self.cursor])
        hint = lab if lab else "<>: move   A: pick   B: cancel"
        p.ctext(cx, top + row * 2 + sbox, hint, th.accent if lab else th.dim)

    def hit(self, app, x, y, W, H):
        # tap a slot in the strip: move the cursor there (pick if it's already the highlighted one)
        th = app.th
        cx, cy, slot, sbox, half, top, fh, row = self._geom(th, _font_cw(th.font), W, H)
        if not (cy - sbox // 2 <= y < cy + sbox // 2):
            return False
        off = int(round((x - cx) / slot))
        if abs(off) > half:
            return False
        if off == 0:                                  # tap the highlighted key = pick it
            return self.key(app, "A")
        self.cursor = (self.cursor + off) % len(self.keys)   # tap a neighbour = move there
        return True
