# picogui_widgets: extra widgets (opt-in). Slider, ProgressBar, Swatch (colour chip), and Custom (a
# callback-driven escape-hatch row for hacking without subclassing).
from picogui import Widget, IntField


_BW = 54                                            # value-bar width (Slider + ProgressBar)


def _value_bar(p, x, y, w, value, lo, hi, frame, fill=None):
    """Draw a framed proportional value bar in the row's right edge (shared by Slider + ProgressBar).
    `fill` overrides the bar colour (an rgb565 int); None uses the theme accent."""
    th = p.th
    bx = x + w - th.pad - _BW
    by = y + 4
    bh = th.row_h - 8
    p.frame(bx, by, _BW, bh, frame)
    span = hi - lo or 1
    v = min(max(value, lo), hi)                      # clamp drawn numerator (value may be set directly)
    p.fill(bx + 1, by + 1, (_BW - 2) * (v - lo) // span, bh - 2, th.accent if fill is None else fill)


class Slider(IntField):
    def value_text(self):
        return ""                                   # drawn as a bar instead

    def draw(self, p, x, y, w, focused):
        th = p.th
        active = focused and p.active
        screen = active and th.active_screen
        if focused:
            p.fill(x, y, w, th.row_h, th.active_bg if active else th.sel_bg)
            if screen:
                p.checker(x, y, w, th.row_h, th.active_hatch)
        fg = (th.active_fg if active else th.sel_fg) if focused else th.fg
        halo = th.active_bg if screen else None
        p.text(x + th.pad, y + th.text_dy, self.label, fg, halo)
        _value_bar(p, x, y, w, self.value, self.lo, self.hi, fg if focused else th.border)

    def draw_big(self, p, x, y, w, focused):        # 2x carousel item: 2x label left, a tall bar right
        th = p.th
        active = focused and p.active
        rh2 = th.row_h * 2
        if focused:
            p.fill(x, y, w, rh2, th.active_bg if active else th.sel_bg)
        fg = (th.active_fg if active else th.sel_fg) if focused else th.fg
        p.btext(x + th.pad, y + th.text_dy, self.label, fg, 2)
        bw = w // 3                                 # tall bar on the right, vertically centred
        bx = x + w - th.pad - bw
        bh = th.row_h
        by = y + (rh2 - bh) // 2
        p.frame(bx, by, bw, bh, fg if focused else th.border)
        span = self.hi - self.lo or 1
        v = min(max(self.value, self.lo), self.hi)
        p.fill(bx + 1, by + 1, (bw - 2) * (v - self.lo) // span, bh - 2, th.accent)

    def _set_by_bar(self, lx, bx, bw):
        """Set the value from a tap at row-local `lx` on a bar drawn at [bx, bx+bw). Returns True/False if
        the tap landed on the bar (changed / no change), or None if it missed (caller nudges by step)."""
        if not (bx <= lx < bx + bw):
            return None
        span = self.hi - self.lo
        denom = bw - 1 or 1                          # last drawn pixel bx+bw-1 maps to hi
        raw = self.lo + ((lx - bx) * span + denom // 2) // denom
        v = min(self.hi, max(self.lo, self.lo + ((raw - self.lo + self.step // 2) // self.step) * self.step))
        if v == self.value:
            return False
        self.value = v
        self._emit(self.value)
        return True

    def touch(self, app, lx, ly, w):                 # flat-row bar: _BW wide at the right edge
        r = self._set_by_bar(lx, w - app.th.pad - _BW, _BW)
        return self._touch_lr(app, lx, w) if r is None else r

    def touch_big(self, app, lx, ly, w):             # carousel big bar: w//3 wide (matches draw_big)
        bw = w // 3
        r = self._set_by_bar(lx, w - app.th.pad - bw, bw)
        return self._touch_lr(app, lx, w) if r is None else r


class ProgressBar(Widget):
    focusable = False

    def __init__(self, label, value=0, lo=0, hi=100, color=None):
        """`color` tints the bar fill: None = theme accent; an rgb565 int = fixed colour; a
        callable(value) -> rgb565 = value-driven (e.g. battery/signal/temperature going green->red)."""
        if lo > hi:
            raise ValueError("ProgressBar lo > hi")
        self.label = label
        self.lo = lo
        self.hi = hi
        self.value = min(max(value, lo), hi)         # clamp into range
        self.color = color

    def set_value(self, v):
        self.value = min(max(int(v), self.lo), self.hi)

    def _fill(self):
        c = self.color
        if c is None:
            return None                              # -> theme accent
        return c(self.value) if callable(c) else c   # callable(value) or a fixed rgb565 int

    def draw(self, p, x, y, w, focused):
        p.text(x + p.th.pad, y + p.th.text_dy, self.label, p.th.dim)
        _value_bar(p, x, y, w, self.value, self.lo, self.hi, p.th.border, self._fill())


class Custom(Widget):
    """Escape-hatch row: supply CALLBACKS instead of subclassing. `draw(p, x, y, w, focused)` paints the
    row; optional `key(app, k)`, `touch(app, lx, ly, w)`, `char(app, ch)` handle input and should return
    True when something changed (so the UI repaints). `focusable`/`hint` as usual. For a one-off custom
    row - a mini gauge, a raw drawing, a bespoke control - without defining a class. `draw_big` (carousel)
    falls back to `draw`."""
    def __init__(self, draw, key=None, touch=None, char=None, draw_big=None,
                 focusable=True, hint="A: select"):
        self._draw = draw
        self._key = key
        self._touch = touch
        self._char = char
        self._draw_big = draw_big
        self.focusable = focusable
        self._hint = hint

    def draw(self, p, x, y, w, focused):
        self._draw(p, x, y, w, focused)

    def draw_big(self, p, x, y, w, focused):         # carousel 2x centre item; falls back to draw()
        (self._draw_big or self._draw)(p, x, y, w, focused)

    def hint(self):
        return self._hint

    def key(self, app, k):
        return self._key(app, k) if self._key else False

    def touch(self, app, lx, ly, w):
        if self._touch:
            return self._touch(app, lx, ly, w)
        return Widget.touch(self, app, lx, ly, w)    # default: a tap = key("A")

    def char(self, app, ch):
        return self._char(app, ch) if self._char else False


class Swatch(Widget):
    """A colour-preview chip (display-only, not focusable): `label` on the left, a filled chip of `get()`
    (an rgb565 int) on the right - so a colour value stays visible at ANY value. Compose a colour setting
    from existing widgets: a Choice over a palette + a Swatch, or three R/G/B Sliders + a Swatch."""
    focusable = False
    CHIP_W = 26                                      # chip width (px)

    def __init__(self, label, get):
        self.label = label
        self.get = get                               # callable -> rgb565 int

    def draw(self, p, x, y, w, focused):
        th = p.th
        p.text(x + th.pad, y + th.text_dy, self.label, th.dim)
        cw = self.CHIP_W
        ch = th.row_h - 6
        cx = x + w - th.pad - cw
        cy = y + 3
        p.fill(cx, cy, cw, ch, self.get())
        p.frame(cx, cy, cw, ch, th.border)
