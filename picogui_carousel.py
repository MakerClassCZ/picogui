# picogui_carousel: a round-display list View (opt-in). The focused item sits at the centre of the face;
# neighbours fan out above/below and each row's width tapers to the circle, so nothing is clipped by the
# round bezel and the value hugs the edge. Rotating / U-D scrolls (the focus stays centred), and the
# focus/active model + touch work as on Screen. Meant for a square/round panel - it uses min(W,H) as the
# diameter and centres on (W/2, H/2). Pair it with the picogui_rgb backend (no viewport needed).
from picogui import View, _next_focusable, derive

VISIBLE = 5                                          # rows to spread across the face (focus + neighbours)


class Carousel(View):
    def __init__(self, title, widgets, show_title=True):
        self.title = title
        self.widgets = widgets
        self.show_title = show_title
        self.sel = -1
        self._dimbase = None                          # cached base of the edge-fade dim theme
        self._dimth = None
        for i, w in enumerate(widgets):
            if w.focusable:
                self.sel = i
                break

    def _move(self, d):
        self.sel, changed = _next_focusable(self.widgets, self.sel, d)
        return changed

    def focused_adjustable(self):
        return 0 <= self.sel < len(self.widgets) and self.widgets[self.sel].adjustable

    def _geom(self, W, H, th):
        r = min(W, H) // 2
        gap = max(th.row_h + 2, (2 * r) // (VISIBLE + 1))   # row-centre spacing (bigger than a flat list)
        return W // 2, H // 2, r, gap

    def _mark_center(self, app):                     # the centred item is double-height, centred on cy
        cx, cy, r, gap = self._geom(app.W, app.H, app.th)
        app.mark(cy - app.th.row_h, cy + app.th.row_h)

    def _row_half(self, r, dymax):
        """Half-width of a row whose farthest edge is `dymax` from the centre, kept inside radius `r`
        (with a small bezel margin). Shared by draw() and hit() so the drawn width == the touch width."""
        inner = r * r - dymax * dymax
        return (int(inner ** 0.5) - 4) if inner > 0 else 0

    def key(self, app, k):
        if k == "B":
            return app.pop()
        if self.sel < 0:
            return False
        if k in ("U", "D"):
            if not self._move(-1 if k == "U" else 1):
                return False
            app.invalidate()                         # every row repositions -> full repaint
            return True
        if self.widgets[self.sel].key(app, k):       # value change: only the centred item redraws
            self._mark_center(app)
            return True
        return False

    def char(self, app, ch):
        if 0 <= self.sel < len(self.widgets) and self.widgets[self.sel].char(app, ch):
            self._mark_center(app)
            return True
        return False

    def _dim_theme(self, base):                      # foreground -> base.dim, so outer rows recede
        if self._dimbase is not base:
            self._dimbase = base
            self._dimth = derive(base, fg=base.dim, accent=base.dim, border=base.dim, bar_fg=base.dim)
        return self._dimth

    def draw(self, p, W, H):
        th = p.th
        p.fill(0, 0, W, H, th.bg)
        cx, cy, r, gap = self._geom(W, H, th)
        rh = th.row_h
        n = len(self.widgets)
        reach = VISIBLE // 2
        dimth = self._dim_theme(th)
        for off in range(-reach, reach + 1):
            i = self.sel + off
            if not (0 <= i < n):
                continue
            yc = cy + off * gap                      # row centre
            rowh = rh * 2 if off == 0 else rh        # focused item is double height
            top = yc - rowh // 2
            # width is limited by the row EDGE farthest from the centre, so the whole row height (not
            # just its middle) stays inside the circle - otherwise the top/bottom rows poke out the rim.
            dymax = max(abs(top - cy), abs(top + rowh - cy))
            half = self._row_half(r, dymax)
            if half < 30 or not p.visible(top, rowh):
                continue
            p.th = dimth if abs(off) == reach else th   # dim the OUTERMOST rows so they recede
            if off == 0:
                self.widgets[i].draw_big(p, cx - half, top, 2 * half, True)
            else:
                self.widgets[i].draw(p, cx - half, top, 2 * half, False)
        p.th = th                                    # restore the base theme for the title + later draws
        if self.show_title:
            p.ctext(cx, r // 8, self.title, th.dim)  # small title, tucked below the top of the circle

    def hit(self, app, x, y, W, H):
        th = app.th
        rh = th.row_h
        cx, cy, r, gap = self._geom(W, H, th)
        off = int(round((y - cy) / gap))
        i = self.sel + off
        if not (0 <= i < len(self.widgets)) or not self.widgets[i].focusable:
            return False
        # require the tap INSIDE the row's actual drawn (tapered) rectangle, not just its Y band - a
        # background / bezel tap must not move focus or nudge a widget. Geometry mirrors draw().
        rowh = rh * 2 if off == 0 else rh            # centred item is double height
        top = cy + off * gap - rowh // 2
        dymax = max(abs(top - cy), abs(top + rowh - cy))
        half = self._row_half(r, dymax)
        if half < 30 or not (cx - half <= x < cx + half and top <= y < top + rowh):
            return False
        if i != self.sel:                            # tap a neighbour -> bring it to the centre
            self.sel = i
            app.invalidate()
            return True
        acted = self.widgets[i].touch_big(app, x - (cx - half), y - (cy - rh), 2 * half)
        if acted:
            self._mark_center(app)                   # only the centred item changed
        return acted
