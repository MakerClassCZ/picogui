# picogui_keyboard: the on-screen keyboard, split out so the core doesn't carry it. Text lazily
# imports this only when a field is opened on-screen, so a board with a real/QWERTY keyboard (the
# char() path) never loads it. Ship picogui_keyboard alongside picogui if you use on-screen text
# entry. Swap it for your own layout by replacing this module.
from picogui import View


class Keyboard(View):
    """On-screen keyboard (D-pad picks a cell, A types it). Edits a Text field's value in place."""
    LAYOUT = ("ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ0123",
              "456789 .,-", ("[_]", "DEL", "OK"))

    def __init__(self, field):
        self.field = field
        self.title = "Edit: " + field.label
        self.buf = field.value
        self.cx = 0
        self.cy = 0
        self.sel = -1

    _COLS = 10                                       # widest row (ABCDEFGHIJ); grid is sized to fit it

    def _cell(self):
        row = self.LAYOUT[self.cy]
        return row[min(self.cx, len(row) - 1)]

    _EDIT_H = 16                                      # height of the edit-buffer box drawn above the grid

    def _grid(self, th, W, H):
        """Cell grid geometry (gy, cw, ch), derived from the display so the whole grid - all 10 columns
        AND all rows - stays on-screen at any width/height. Shared by draw() and hit() so they never
        diverge. ch fills the remaining height (no fixed floor that could overflow a short panel)."""
        gy = self._top_h(th) + 6 + self._EDIT_H + 2   # just below the edit-buffer box
        cw = (W - 2 * th.pad) // self._COLS
        avail = H - gy - self._bot_h(th)
        ch = max(1, avail // len(self.LAYOUT))        # fit the rows into avail (never spill off-screen)
        return gy, cw, ch

    def key(self, app, k):
        if k == "B":
            app.pop()
            return True
        if k == "U":
            self.cy = (self.cy - 1) % len(self.LAYOUT)
            self.cx = min(self.cx, len(self.LAYOUT[self.cy]) - 1)
        elif k == "D":
            self.cy = (self.cy + 1) % len(self.LAYOUT)
            self.cx = min(self.cx, len(self.LAYOUT[self.cy]) - 1)
        elif k == "L":
            self.cx = (self.cx - 1) % len(self.LAYOUT[self.cy])
        elif k == "R":
            self.cx = (self.cx + 1) % len(self.LAYOUT[self.cy])
        elif k == "A":
            c = self._cell()
            if c == "OK":
                self.field.value = self.buf
                if self.field.on_change:
                    self.field.on_change(self.buf)
                app.pop()
                return True
            old = self.buf
            if c == "DEL":
                self.buf = self.buf[:-1]
            elif c == "[_]":
                if len(self.buf) < self.field.maxlen:
                    self.buf += " "
            elif len(self.buf) < self.field.maxlen:
                self.buf += c
            return self.buf != old               # DEL on empty / typing at maxlen = no change
        else:
            return False
        return True

    def draw(self, p, W, H):
        th = p.th
        top = self._top_h(th)
        p.fill(0, 0, W, H, th.bg)
        self._titlebar(p, W, self.title)
        # buffer with caret (drawn as a separate glyph, no per-frame concat)
        p.frame(th.pad, top + 6, W - 2 * th.pad, self._EDIT_H, th.border)
        p.text(th.pad + 4, top + 10, self.buf, th.fg)
        p.text(th.pad + 4 + len(self.buf) * p.cw, top + 10, "_", th.fg)
        # key grid
        gy, cw, ch = self._grid(th, W, H)
        for ry, row in enumerate(self.LAYOUT):
            for cxi, cell in enumerate(row):
                x = th.pad + cxi * cw
                y = gy + ry * ch
                focus = (ry == self.cy and cxi == min(self.cx, len(row) - 1))
                span = cw - 2                            # highlight = one cell wide (matches hit's cw grid)
                if focus:
                    p.fill(x, y, span, ch - 1, th.sel_bg)
                p.text(x + 3, y + th.text_dy, cell, th.sel_fg if focus else th.fg)
        self._softbar(p, W, H, "A: type", "B: cancel")

    def hit(self, app, x, y, W, H):
        if self._softbar_back(app, x, y, W, H):      # tap 'B: cancel' area
            return True
        th = app.th
        gy, cw, ch = self._grid(th, W, H)            # same grid as draw()
        ry = (y - gy) // ch
        cxi = (x - th.pad) // cw
        if 0 <= ry < len(self.LAYOUT):
            row = self.LAYOUT[ry]
            if 0 <= cxi < len(row):
                moved = (self.cy, self.cx) != (ry, cxi)
                self.cy = ry
                self.cx = cxi                        # focus the tapped cell...
                return self.key(app, "A") or moved   # ...and type it (no-op DEL/maxlen -> only 'moved')
        return False
