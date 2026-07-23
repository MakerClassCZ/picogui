# picogui_tabs: Tabs - a horizontal tab bar over N pages (opt-in).
from picogui import View, _next_focusable


class Tabs(View):
    """A horizontal tab bar over N pages, each a flat widget list. The tab bar is the top focus row:
    when focused L/R switches tab and DOWN enters the content; in the content U/D moves and UP from the
    first widget returns to the bar. Uses only the 6 logical keys. See the README for the key table."""
    def __init__(self, title, tabs):
        tabs = [(lbl, list(ws)) for lbl, ws in tabs]
        if not tabs:
            raise ValueError("Tabs needs at least one tab")
        self.title = title
        self.tabs = tabs
        self.active = 0
        self.bar_focused = True            # focus starts on the tab bar
        self.top = 0
        self.sel = -1
        self._reset_sel()

    def _widgets(self):
        return self.tabs[self.active][1]

    def _first_focusable(self):
        for i, w in enumerate(self._widgets()):
            if w.focusable:
                return i
        return -1

    def _reset_sel(self):
        self.top = 0
        self.sel = self._first_focusable()

    def _move(self, d):
        self.sel, changed = _next_focusable(self._widgets(), self.sel, d)
        return changed

    def _geom(self, th, H):
        """Content geometry (tab-strip top, its bottom, first content row y, visible row count), honouring
        title_bar/soft_bar via _top_h/_bot_h. Shared by draw/hit/mark so they never disagree."""
        ty = self._top_h(th) + 1                      # tab strip sits just under the (optional) title bar
        strip_bottom = ty + th.bar_h
        y0 = strip_bottom + 3
        rows = max(1, (H - strip_bottom - self._bot_h(th) - 3) // th.row_h)
        return ty, strip_bottom, y0, rows

    def _mark_row(self, app, i):                      # mark content row i if it is on-screen
        _, _, y0, rows = self._geom(app.th, app.H)
        if self.top <= i < self.top + rows:
            y = y0 + (i - self.top) * app.th.row_h
            app.mark(y, y + app.th.row_h)

    def focused_adjustable(self):
        # Encoder: on the bar the switch enters content (not an edit); in content it edits a value widget.
        # Switching tabs is 2D (L/R) - a single encoder can't reach it; use touch or a d-pad for that.
        if self.bar_focused:
            return False
        ws = self._widgets()
        return 0 <= self.sel < len(ws) and ws[self.sel].adjustable

    def key(self, app, k):
        if k == "B":
            return app.pop()
        if self.bar_focused:
            if k in ("L", "R"):
                if len(self.tabs) < 2:               # only one tab: nothing to switch to
                    return False
                self.active = (self.active + (1 if k == "R" else -1)) % len(self.tabs)
                self._reset_sel()
                return True
            if k in ("D", "A") and self.sel >= 0:    # DOWN or the encoder switch (A) enters the content
                self.bar_focused = False
                return True
            return False
        # content focused
        if k in ("U", "D"):
            if k == "U" and self.sel <= self._first_focusable():   # at the top row -> back to the bar
                self.bar_focused = True                # bar highlight + content focus both change -> full
                return True
            old = self.sel
            if not self._move(-1 if k == "U" else 1):
                return False
            _, _, _, rows = self._geom(app.th, app.H)
            ws = self._widgets()
            if self.top <= old < self.top + rows and self.top <= self.sel < self.top + rows:
                self._mark_row(app, old)              # no scroll: repaint the two rows...
                self._mark_row(app, self.sel)
                if ws[old].hint() != ws[self.sel].hint():   # ...+ softbar ONLY if the hint changed
                    app.mark(app.H - self._bot_h(app.th), app.H)   # (keeps the dirty region contiguous)
            else:
                app.invalidate()                      # scrolled -> full repaint
            return True
        if 0 <= self.sel < len(self._widgets()):
            if self._widgets()[self.sel].key(app, k):  # value change on the focused widget: just its row
                self._mark_row(app, self.sel)
                return True
        return False

    def char(self, app, ch):
        if not self.bar_focused:
            ws = self._widgets()
            if 0 <= self.sel < len(ws) and ws[self.sel].char(app, ch):
                self._mark_row(app, self.sel)         # a consumed char repaints just its row
                return True
        return False

    def draw(self, p, W, H):
        th = p.th
        p.fill(0, 0, W, H, th.bg)
        self._titlebar(p, W, self.title)
        ty, strip_bottom, y0, rows = self._geom(th, H)
        # tab strip beneath the (optional) title bar
        n = len(self.tabs)
        tw = W // n
        for i in range(n):
            tx = i * tw
            w = (W - tx) if i == n - 1 else tw
            active = (i == self.active)
            if active:
                p.fill(tx, ty, w, th.bar_h, th.sel_bg if self.bar_focused else th.bar_bg)
            p.frame(tx, ty, w, th.bar_h, th.sel_fg if (active and self.bar_focused) else th.border)
            if active and self.bar_focused:
                fg = th.sel_fg
            elif active:
                fg = th.fg
            else:
                fg = th.dim
            p.ctext(tx + w // 2, ty + th.text_dy, self.tabs[i][0], fg)
        p.hline(0, strip_bottom, W, th.border)
        # content rows
        ws = self._widgets()
        if not self.bar_focused and self.sel >= 0:
            if self.sel < self.top:
                self.top = self.sel
            elif self.sel >= self.top + rows:
                self.top = self.sel - rows + 1
        y = y0
        for i in range(self.top, min(len(ws), self.top + rows)):
            if p.visible(y, th.row_h):                   # skip rows outside the current band
                ws[i].draw(p, 0, y, W, (not self.bar_focused) and i == self.sel)
            y += th.row_h
        if self.top > 0:
            p.rtext(W - 2, y0 - 1, "^", th.dim)
        if self.top + rows < len(ws):
            p.rtext(W - 2, H - self._bot_h(th) - 8, "v", th.dim)
        # softkey hint depends on where focus is
        if self.bar_focused:
            left = "<>: tab   v: enter" if self.sel >= 0 else "<>: tab"
        else:
            left = ws[self.sel].hint() if 0 <= self.sel < len(ws) else ""
        self._softbar(p, W, H, left, "B: back")

    def hit(self, app, x, y, W, H):
        if self._softbar_back(app, x, y, W, H):
            return True
        th = app.th
        ty, strip_bottom, y0, rows = self._geom(th, H)
        if ty <= y < ty + th.bar_h:                  # tap the tab strip = switch active tab
            n = len(self.tabs)
            self.active = min(n - 1, max(0, x // (W // n)))
            self.bar_focused = True
            self._reset_sel()
            return True
        if y0 <= y < y0 + rows * th.row_h:           # tap a content row = enter it + act
            ws = self._widgets()
            i = self.top + (y - y0) // th.row_h
            if 0 <= i < len(ws) and ws[i].focusable:
                moved = self.bar_focused or self.sel != i   # entering content / moving focus is visible
                self.bar_focused = False
                self.sel = i
                acted = ws[i].touch(app, x, y - (y0 + (i - self.top) * th.row_h), W)
                return acted or moved
        return False
