# picogui_records: RecordList + NoteView - scrollable text records (the memo/contacts pattern).
from picogui import View


class RecordList(View):
    """Scrollable list of records (the memo/contacts/schedule pattern). Items are
    strings or (text, right) pairs; A calls on_select(app, index), B pops. The item
    list may be mutated between frames (add/delete); selection re-clamps. Shows an
    empty-state message when there are no items."""
    def __init__(self, title, items, on_select=None, empty="(no items)", hint="A: open"):
        self.title = title
        self.items = items
        self.on_select = on_select
        self.empty = empty
        self._hint = hint
        self.sel = 0
        self.top = 0

    def key(self, app, k):
        n = len(self.items)
        if self.sel >= n:
            self.sel = n - 1 if n else 0
        if k in ("U", "D") and n > 1:
            old = self.sel
            self.sel = (self.sel + (1 if k == "D" else -1)) % n
            th = app.th
            rows = self._visible_rows(app.H, th)
            if self.top <= old < self.top + rows and self.top <= self.sel < self.top + rows:
                for i in (old, self.sel):            # no scroll: repaint just the two rows
                    y = self._top_h(th) + 2 + (i - self.top) * th.row_h
                    app.mark(y, y + th.row_h)
            else:
                app.invalidate()
            return True
        if k == "A" and n and self.on_select:
            self.on_select(app, self.sel)            # usually pushes a screen -> full via Session
            return True
        if k == "B":
            return app.pop()
        return False

    def draw(self, p, W, H):
        th = p.th
        p.fill(0, 0, W, H, th.bg)
        self._titlebar(p, W, self.title)
        n = len(self.items)
        if self.sel >= n:
            self.sel = n - 1 if n else 0
        y0 = self._top_h(th) + 2
        rows = self._visible_rows(H, th)
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + rows:
            self.top = self.sel - rows + 1
        if n == 0:
            p.ctext(W // 2, H // 2 - 8, self.empty, th.dim)
        y = y0
        for i in range(self.top, min(n, self.top + rows)):
            if p.visible(y, th.row_h):                       # skip rows outside the current band
                it = self.items[i]
                if isinstance(it, tuple):
                    left, right = it
                else:
                    left, right = it, ""
                focused = (i == self.sel)
                if focused:
                    p.fill(0, y, W, th.row_h, th.sel_bg)
                fg = th.sel_fg if focused else th.fg
                p.text(th.pad, y + th.text_dy, left, fg)
                if right:
                    p.rtext(W - th.pad, y + th.text_dy, right, th.sel_fg if focused else th.dim)
            y += th.row_h
        if self.top > 0:
            p.rtext(W - 2, y0 - 1, "^", th.dim)
        if self.top + rows < n:
            p.rtext(W - 2, H - self._bot_h(th) - 8, "v", th.dim)
        self._softbar(p, W, H, self._hint if n else "", "B: back")

    def hit(self, app, x, y, W, H):
        if self._softbar_back(app, x, y, W, H):
            return True
        th = app.th
        y0 = self._top_h(th) + 2
        rows = self._visible_rows(H, th)
        n = len(self.items)
        if y0 <= y < y0 + rows * th.row_h:
            i = self.top + (y - y0) // th.row_h
            if 0 <= i < n:
                moved = self.sel != i
                self.sel = i                         # tap a record = focus (+ open if wired)
                if self.on_select:
                    self.on_select(app, i)
                    return True
                return moved                         # no callback: only a focus move is a change
        return False


class NoteView(View):
    """Full-screen word-wrapped text viewer (a memo body). U/D scrolls, B pops. Wrapping is cached and
    recomputed only when the column count changes (e.g. a different display width)."""
    LINE_H = 11

    def __init__(self, title, text):
        self.title = title
        self.text = text
        self.lines = None
        self._cols = -1
        self.top = 0
        self.sel = -1

    def _wrap(self, cols):
        out = []
        for para in self.text.split("\n"):
            cur = ""
            for wd in para.split(" "):
                t = wd if not cur else cur + " " + wd
                if len(t) <= cols:
                    cur = t
                else:
                    if cur:
                        out.append(cur)
                    while len(wd) > cols:
                        out.append(wd[:cols])
                        wd = wd[cols:]
                    cur = wd
            out.append(cur)
        return out

    def _vis(self, H, th):
        return max(1, (H - self._top_h(th) - self._bot_h(th) - 8) // self.LINE_H)

    def key(self, app, k):
        if k == "U":
            old = self.top
            self.top = max(0, self.top - 1)
            return self.top != old               # no repaint when already at the top
        if k == "D" and self.lines:
            old = self.top
            self.top = min(max(0, len(self.lines) - self._vis(app.H, app.th)), self.top + 1)
            return self.top != old
        if k == "B":
            return app.pop()
        return False

    def draw(self, p, W, H):
        th = p.th
        cols = (W - 2 * th.pad) // p.cw
        if self.lines is None or cols != self._cols:     # (re)wrap only when geometry changes
            self.lines = self._wrap(cols)
            self._cols = cols
        p.fill(0, 0, W, H, th.bg)
        self._titlebar(p, W, self.title)
        vis = self._vis(H, th)
        y = self._top_h(th) + 5
        for i in range(self.top, min(len(self.lines), self.top + vis)):
            p.text(th.pad, y, self.lines[i], th.fg)
            y += self.LINE_H
        if self.top > 0:
            p.rtext(W - 2, self._top_h(th) + 1, "^", th.dim)
        if self.top + vis < len(self.lines):
            p.rtext(W - 2, H - self._bot_h(th) - 8, "v", th.dim)
        self._softbar(p, W, H, "^v: scroll", "B: back")

    def hit(self, app, x, y, W, H):
        if self._softbar_back(app, x, y, W, H):
            return True
        return self.key(app, "U" if y < H // 2 else "D")   # tap upper half scrolls up, lower half down
