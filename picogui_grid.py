# picogui_grid: MenuGrid - the Casio-organizer icon-grid home menu (opt-in).
from picogui import View
from picogui_iconbase import Icon                    # the type only - not the built-in catalogue


class MenuGrid(View):
    """App-launcher home screen (the Casio organizer main menu): a D-pad cursor over
    a grid of cells, A opens. Items = (label, glyph, open) where open(app) returns a
    Screen to push (or None if it acted itself). Chosen over an L/R tab bar because
    L/R already belongs to the focused value widgets (Choice/IntField/Slider)."""
    def __init__(self, title, items, cell_w=70, cell_h=44):
        if not items:                                # like Choice/Tabs/RadioGroup: an empty grid is a bug
            raise ValueError("MenuGrid needs at least one item")
        self.title = title
        self.items = items
        self.cell_w = cell_w
        self.cell_h = cell_h
        self.sel = 0
        self.top = 0

    def _cols(self, W, pad):
        return max(1, (W - 2 * pad) // self.cell_w)

    def key(self, app, k):
        n = len(self.items)
        cols = self._cols(app.W, app.th.pad)
        old = self.sel
        if k == "L":
            self.sel = (self.sel - 1) % n
        elif k == "R":
            self.sel = (self.sel + 1) % n
        elif k == "U":
            self.sel = (self.sel - cols) % n
        elif k == "D":
            self.sel = (self.sel + cols) % n
        elif k == "A":
            scr = self.items[self.sel][2](app)
            if scr:
                app.push(scr)
            return True
        elif k == "B":
            return app.pop()
        else:
            return False
        return self.sel != old                       # single-cell grid: a wrap onto self is no change

    def draw(self, p, W, H):
        th = p.th
        p.fill(0, 0, W, H, th.bg)
        self._titlebar(p, W, self.title, self.items[self.sel][0])
        cols = self._cols(W, th.pad)
        x0 = (W - cols * self.cell_w) // 2
        y0 = self._top_h(th) + 4
        rows_vis = max(1, (H - self._top_h(th) - self._bot_h(th) - 8) // self.cell_h)
        row_sel = self.sel // cols
        if row_sel < self.top:
            self.top = row_sel
        elif row_sel >= self.top + rows_vis:
            self.top = row_sel - rows_vis + 1
        for i in range(len(self.items)):
            r = i // cols - self.top
            c = i % cols
            if r < 0 or r >= rows_vis:
                continue
            x = x0 + c * self.cell_w + 2
            y = y0 + r * self.cell_h + 2
            cw = self.cell_w - 4
            ch = self.cell_h - 4
            if not p.visible(y, ch):                 # skip cells outside the current band
                continue
            focus = (i == self.sel)
            if focus:
                p.fill(x, y, cw, ch, th.sel_bg)
            p.frame(x, y, cw, ch, th.sel_fg if focus else th.border)
            fg = th.sel_fg if focus else th.fg
            gx = x + cw // 2
            ic = self.items[i][1]                    # icon name (in ICONS), an Icon, or a 1-char badge
            icon = ic if isinstance(ic, Icon) else None      # glyph is an Icon instance, else a badge char
            icol = th.sel_fg if focus else th.accent
            if icon is not None:
                icon.draw(p, gx - icon.w // 2, y + 5, icol)
            else:
                p.frame(gx - 7, y + 5, 14, 13, fg)
                p.ctext(gx, y + 8, str(ic), icol)
            p.ctext(gx, y + ch - 13, self.items[i][0], fg)
        self._softbar(p, W, H, "A: open", "B: back")

    def hit(self, app, x, y, W, H):
        if self._softbar_back(app, x, y, W, H):
            return True
        th = app.th
        cols = self._cols(W, th.pad)
        x0 = (W - cols * self.cell_w) // 2
        y0 = self._top_h(th) + 4
        rows_vis = max(1, (H - self._top_h(th) - self._bot_h(th) - 8) // self.cell_h)
        for i in range(len(self.items)):             # same cell layout as draw (self.top from last draw)
            r = i // cols - self.top
            c = i % cols
            if r < 0 or r >= rows_vis:
                continue
            cx = x0 + c * self.cell_w
            cy = y0 + r * self.cell_h
            if cx <= x < cx + self.cell_w and cy <= y < cy + self.cell_h:
                self.sel = i                         # tap a cell = select + open it
                scr = self.items[i][2](app)
                if scr:
                    app.push(scr)
                return True
        return False
