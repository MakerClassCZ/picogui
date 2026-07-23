# picogui core: backend-neutral immediate-mode UI for small config displays. The minimal core - the
# Label/Toggle/Choice/IntField/Button/Link widgets, the Screen list + View base, Painter and Session -
# renders a settings screen with nothing else imported. Opt into addons only as needed: picogui_themes
# (LcdTheme/MonoTheme), picogui_widgets (Slider/ProgressBar/Swatch/Custom), picogui_text (Text),
# picogui_dialog (Dialog), picogui_form (Form binding), picogui_keyboard (grid keyboard) /
# picogui_keyboard_row (one-row keyboard), picogui_icons (Icon/ICONS), and the richer screens in
# picogui_fields / picogui_records / picogui_grid / picogui_tabs / picogui_carousel (fields+records+grid
# +tabs aggregated by picogui_extras). picogui_full re-exports everything. Pick ONE backend by hardware:
# picogui_picogame (picogame engine) / picogui_rgb (SPI colour panel, small RAM) / picogui_mono (1bpp
# OLED) / picogui_fb (colour framebuffer / DVI, needs PSRAM-class RAM).
import terminalio


def rgb565(r, g, b):
    """A 565 colour int in picogame/panel wire order (bytes swapped: high byte last). displayio writes
    it low byte first; the picogame C engine consumes the same order."""
    c = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


FONT = terminalio.FONT


def _font_cw(font):
    """Glyph advance (px) of a monospace font, for width / right-align / centre maths."""
    return font.get_bounding_box()[0]


_CW = _font_cw(FONT)                                # advance of the default font (Painter uses th.font's)


class Theme:
    def __init__(self):
        self.font = FONT
        self.bg = rgb565(24, 26, 32)
        self.fg = rgb565(228, 230, 236)
        self.dim = rgb565(122, 128, 140)
        self.sel_bg = rgb565(52, 110, 210)       # focused-row highlight
        self.sel_fg = rgb565(255, 255, 255)
        self.active_bg = rgb565(216, 144, 32)    # active/edit highlight (amber - distinct from the blue
        self.active_fg = rgb565(16, 20, 24)      # focus AND from the green `accent` a Slider bar uses)
        self.active_screen = False               # 1bpp themes set True: screen the active row (a 50%
                                                 # checker) + halo the text, since they have no third
                                                 # solid tone; colour themes just use a distinct active_bg
        self.active_hatch = self.bg              # the colour the checker screens toward (if active_screen)
        self.bar_bg = rgb565(40, 44, 54)         # title + softkey bars
        self.bar_fg = rgb565(200, 206, 218)
        self.border = rgb565(76, 82, 96)
        self.accent = rgb565(96, 200, 150)
        self.row_h = 15
        self.pad = 6
        self.bar_h = 15
        self.text_dy = 3         # vertical text baseline within a row/bar (lower it for compact themes)
        self.title_bar = True    # draw the top title bar (turn off to reclaim a row on tiny displays)
        self.soft_bar = True     # draw the bottom softkey bar


class _ThemeProxy:
    """A theme with a few attributes overridden; everything else falls through to the base theme."""
    def __init__(self, base, overrides):
        self._base = base
        self._ov = overrides

    def __getattr__(self, k):                        # only reached for attrs not set on the proxy itself
        ov = self._ov
        return ov[k] if k in ov else getattr(self._base, k)


def derive(theme, **overrides):
    """Return a lightweight THEME PROXY: `overrides` win, every other attribute falls through to
    `theme`. Cheap (no full copy - MicroPython has no `copy`), so build one per screen/row and swap it
    into `p.th` to retint / dim / high-contrast a part of the UI:  `p.th = ui.derive(th, sel_bg=col)`."""
    return _ThemeProxy(theme, overrides)


class Painter:
    """Absolute-coord draw helpers over a `view` (the current strip/surface) at origin (vx, vy). The
    view implements pixel/fill_rect/line/text/blit; colours are rgb565() ints. `by0`/`by1` bound the
    view's vertical extent so callers can skip fully off-band work via visible()."""
    def __init__(self, view, vx, vy, th, vh=0):
        self.reset(view, vx, vy, th, vh)

    def reset(self, view, vx, vy, th, vh=0, active=False):
        self.v = view
        self.ox = vx
        self.oy = vy
        self.th = th
        self.active = active                        # True while the focused row is in encoder edit mode
        self.cw = _CW if th.font is FONT else _font_cw(th.font)   # advance of the active font (default cached)
        self.by0 = vy
        self.by1 = (vy + vh) if vh else (1 << 30)
        return self

    def visible(self, y, h):
        """True if the absolute rows [y, y+h) intersect this view's band (else the caller can skip)."""
        return y < self.by1 and y + h > self.by0

    def text(self, x, y, s, color, halo=None):
        """Draw `s` at (x, y). With `halo` set, first stamp the string at the 8 one-pixel offsets in the
        halo colour (a 1px outline) so it stays legible over a busy/dithered background, then the text."""
        bx = x - self.ox
        by = y - self.oy
        v = self.v
        f = self.th.font
        if halo is not None:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        v.text(bx + dx, by + dy, s, halo, f)
        v.text(bx, by, s, color, f)

    def rtext(self, xr, y, s, color, halo=None):    # right edge at xr
        self.text(xr - len(s) * self.cw, y, s, color, halo)

    def ctext(self, cx, y, s, color):               # centred on cx
        self.v.text(cx - len(s) * self.cw // 2 - self.ox, y - self.oy, s, color, self.th.font)

    def btext(self, x, y, s, color, scale=2):
        """Big text: draw `s` with each glyph pixel blown up to a scale x scale block (nearest-neighbour),
        so the fixed font reads larger. Backend-neutral (uses fill_rect); no glyph cache - meant for a
        few characters (e.g. a carousel's centred item), not bulk text. Consecutive set pixels in a row
        are coalesced into ONE fill_rect (a run), so a solid glyph row costs one primitive, not fw."""
        f = self.th.font
        bb = f.get_bounding_box()
        fw, fh = bb[0], bb[1]
        ox, oy = self.ox, self.oy
        v = self.v
        for ch in s:
            g = f.get_glyph(ord(ch))
            if g is not None:
                sheet = g.bitmap
                tpr = sheet.width // fw
                ti = g.tile_index
                tx = (ti % tpr) * fw
                ty = (ti // tpr) * fh
                for gy in range(fh):
                    sy = ty + gy
                    py = y + gy * scale - oy
                    gx = 0
                    while gx < fw:
                        if sheet[tx + gx, sy]:
                            run = 1                          # extend across adjacent set pixels
                            while gx + run < fw and sheet[tx + gx + run, sy]:
                                run += 1
                            v.fill_rect(x + gx * scale - ox, py, run * scale, scale, color)
                            gx += run
                        else:
                            gx += 1
            x += fw * scale

    def brtext(self, xr, y, s, color, scale=2):     # big text, right edge at xr
        self.btext(xr - len(s) * self.cw * scale, y, s, color, scale)

    def fill(self, x, y, w, h, color):
        self.v.fill_rect(x - self.ox, y - self.oy, w, h, color)

    def hline(self, x, y, w, color):
        self.v.line(x - self.ox, y - self.oy, x + w - 1 - self.ox, y - self.oy, color)

    def frame(self, x, y, w, h, color):
        self.hline(x, y, w, color)
        self.hline(x, y + h - 1, w, color)
        self.v.line(x - self.ox, y - self.oy, x - self.ox, y + h - 1 - self.oy, color)
        self.v.line(x + w - 1 - self.ox, y - self.oy, x + w - 1 - self.ox, y + h - 1 - self.oy, color)

    def checker(self, x, y, w, h, color):
        """Fill a 50% checkerboard of `color` over the rect - the classic 1bpp dither. Per-pixel (heavier
        than hatch); fine for a small area like an active row on a mono surface."""
        for j in range(h):
            ay = y + j
            for i in range((x + ay) & 1, w, 2):      # every other pixel, phase per row -> checkerboard
                self.v.pixel(x + i - self.ox, ay - self.oy, color)

    def pixel(self, x, y, color):
        self.v.pixel(x - self.ox, y - self.oy, color)

    def blit(self, bitmap, x, y):
        self.v.blit(bitmap, x - self.ox, y - self.oy)


# ---------------------------------------------------------------- widgets
class Widget:
    focusable = True
    adjustable = False       # focus/active nav: True = has a value rotate() edits in active mode;
                             # False = an action (button/link/toggle) that press() just fires

    def hint(self):
        return "A: select"

    def draw(self, p, x, y, w, focused):
        pass

    def draw_big(self, p, x, y, w, focused):
        """A double-height rendering for a round carousel's centred item. Default: the normal row (so a
        widget with no big variant still shows). _Field / Slider / Button override it with 2x text."""
        self.draw(p, x, y, w, focused)

    def key(self, app, k):                          # k in U/D/L/R/A/B; True if it changed anything
        return False

    def char(self, app, ch):                        # a typed character; True if consumed
        return False

    def touch(self, app, lx, ly, w):                # a tap at row-local (lx, ly), row width w
        return self.key(app, "A")                   # default: activate; value widgets use the position

    def touch_big(self, app, lx, ly, w):            # a tap on the enlarged (carousel-centred) widget;
        return self.touch(app, lx, ly, w)           # override where big geometry differs (e.g. Slider)

    # Value widgets implement silent get_value()/set_value(); set_value() does not fire on_change.
    def get_value(self):
        return getattr(self, "value", None)

    def set_value(self, v):
        self.value = v


class Label(Widget):
    focusable = False

    def __init__(self, text, dim=False):
        self.text = text
        self.dim = dim

    def draw(self, p, x, y, w, focused):
        p.text(x + p.th.pad, y + p.th.text_dy, self.text, p.th.dim if self.dim else p.th.fg)


class _Field(Widget):
    """label left, value right, selection highlight when focused. Subclasses set value_text()/key()."""
    def __init__(self, label, on_change=None):
        self.label = label
        self.on_change = on_change

    def value_text(self):
        return ""

    def _emit(self, v):
        if self.on_change:
            self.on_change(v)

    def _touch_lr(self, app, lx, w):                 # tap right half = R, left half = L
        return self.key(app, "R" if lx >= w // 2 else "L")

    def draw(self, p, x, y, w, focused):
        th = p.th
        active = focused and p.active                # the focused row is in encoder edit mode
        screen = active and th.active_screen         # 1bpp: screen the row + halo the text
        if focused:
            p.fill(x, y, w, th.row_h, th.active_bg if active else th.sel_bg)
            if screen:
                p.checker(x, y, w, th.row_h, th.active_hatch)
        fg = (th.active_fg if active else th.sel_fg) if focused else th.fg
        halo = th.active_bg if screen else None
        p.text(x + th.pad, y + th.text_dy, self.label, fg, halo)
        vt = self.value_text()
        if vt:
            p.rtext(x + w - th.pad, y + th.text_dy, vt, fg, halo)

    def draw_big(self, p, x, y, w, focused):        # 2x-tall centred carousel item: label + value in 2x text
        th = p.th
        active = focused and p.active
        rh2 = th.row_h * 2
        if focused:
            p.fill(x, y, w, rh2, th.active_bg if active else th.sel_bg)
            if active and th.active_screen:
                p.checker(x, y, w, rh2, th.active_hatch)
        fg = (th.active_fg if active else th.sel_fg) if focused else th.fg
        ty = y + th.text_dy                          # 2x glyphs are ~2*font_h tall -> fit the 2*row_h slot
        p.btext(x + th.pad, ty, self.label, fg, 2)
        vt = self.value_text()
        if vt:
            p.brtext(x + w - th.pad, ty, vt, fg, 2)


class Toggle(_Field):
    def __init__(self, label, value=False, on_change=None):
        super().__init__(label, on_change)
        self.value = bool(value)

    def set_value(self, v):
        self.value = bool(v)

    def hint(self):
        return "A: toggle"

    def value_text(self):
        return "ON" if self.value else "OFF"

    def key(self, app, k):
        if k == "A":                                # A only; repeated L/R must not toggle
            self.value = not self.value
            self._emit(self.value)
            return True
        return False


class Choice(_Field):
    adjustable = True

    def __init__(self, label, options, index=0, on_change=None):
        super().__init__(label, on_change)
        options = list(options)
        if not options:
            raise ValueError("Choice needs at least one option")
        self.options = options
        self.index = min(max(index, 0), len(options) - 1)   # clamp initial index

    def hint(self):
        return "<>: change"

    def get_value(self):
        return self.options[self.index]

    def set_value(self, v):
        if v in self.options:
            self.index = self.options.index(v)

    def value_text(self):
        return "< %s >" % self.options[self.index]

    def key(self, app, k):
        if len(self.options) < 2:                    # nothing to cycle to: no change, no emit
            return False
        if k == "R" or k == "A":
            self.index = (self.index + 1) % len(self.options)
        elif k == "L":
            self.index = (self.index - 1) % len(self.options)
        else:
            return False
        self._emit(self.options[self.index])
        return True

    def touch(self, app, lx, ly, w):
        return self._touch_lr(app, lx, w)            # tap right half = next, left = prev


class IntField(_Field):
    adjustable = True

    def __init__(self, label, value=0, lo=0, hi=100, step=1, on_change=None):
        super().__init__(label, on_change)
        if lo > hi:
            raise ValueError("IntField lo > hi")
        if step <= 0:
            raise ValueError("IntField step must be positive")
        self.lo = lo
        self.hi = hi
        self.step = step
        self.value = min(max(value, lo), hi)         # clamp into range at construction

    def hint(self):
        return "<>: adjust"

    def value_text(self):
        return "< %d >" % self.value

    def set_value(self, v):
        self.value = min(max(int(v), self.lo), self.hi)

    def key(self, app, k):
        old = self.value
        if k == "R":
            self.value = min(self.hi, self.value + self.step)
        elif k == "L":
            self.value = max(self.lo, self.value - self.step)
        else:
            return False
        if self.value == old:                       # already at the limit: no change, no redraw/emit
            return False
        self._emit(self.value)
        return True

    def touch(self, app, lx, ly, w):
        return self._touch_lr(app, lx, w)            # tap right half = +step, left = -step


def _next_focusable(widgets, sel, d):
    """Advance `sel` by d (wrapping) to the next focusable widget. Returns (new_sel, changed)."""
    n = len(widgets)
    i = sel
    for _ in range(n):
        i = (i + d) % n
        if widgets[i].focusable:
            return i, i != sel
    return sel, False


class Button(_Field):
    def __init__(self, label, on_press=None):
        super().__init__(label)
        self.on_press = on_press

    def hint(self):
        return "A: press"

    def draw(self, p, x, y, w, focused):
        th = p.th
        cx = x + th.pad
        cw = w - 2 * th.pad
        top = y + 1
        bh = th.row_h - 2
        if focused:
            p.fill(cx, top, cw, bh, th.sel_bg)
        p.frame(cx, top, cw, bh, th.sel_fg if focused else th.border)
        p.ctext(x + w // 2, top + 1, self.label, th.sel_fg if focused else th.fg)   # vertically centred

    def draw_big(self, p, x, y, w, focused):        # 2x-tall boxed button with a centred 2x label
        th = p.th
        bx = x + th.pad
        bw = w - 2 * th.pad
        bh = th.row_h * 2 - 4
        if focused:
            p.fill(bx, y + 2, bw, bh, th.sel_bg)
        p.frame(bx, y + 2, bw, bh, th.sel_fg if focused else th.border)
        tw = len(self.label) * p.cw * 2
        p.btext(x + (w - tw) // 2, y + th.text_dy + 2, self.label, th.sel_fg if focused else th.fg, 2)

    def key(self, app, k):
        if k == "A" and self.on_press:
            self.on_press(app)                       # a callback-less button does nothing (no repaint)
            return True
        return False


class Link(_Field):
    """Drill into a sub-screen (A). `make_screen(app)` returns a Screen; B pops back."""
    def __init__(self, label, make_screen):
        super().__init__(label)
        self.make_screen = make_screen

    def hint(self):
        return "A: open"

    def value_text(self):
        return ">"

    def key(self, app, k):
        if k == "A":
            app.push(self.make_screen(app))
            return True
        return False


# ---------------------------------------------------------------- screens
class View:
    """Base stack view. Subclasses implement draw() and key(); key() returns True when it changed
    something (so the Session repaints only then). char() and hit() ignore unsupported input by default."""
    def draw(self, p, W, H):                        # p = a Painter; W/H = full display size
        pass

    def key(self, app, k):                          # k in U/D/L/R/A/B; True if it changed anything
        return False

    def char(self, app, ch):                        # a typed character; True if consumed
        return False

    def hit(self, app, x, y, W, H):                 # a TAP at absolute (x, y); True if consumed
        return False

    def focused_adjustable(self):
        """True if the currently-focused item holds a value the encoder should edit (so its switch enters
        active mode). False = an action item (the switch fires it). Base views have no such item."""
        return False

    def _top_h(self, th):
        """Height reserved by the title bar (0 when it is turned off)."""
        return th.bar_h if th.title_bar else 0

    def _bot_h(self, th):
        """Height reserved by the softkey bar (0 when it is turned off)."""
        return th.bar_h if th.soft_bar else 0

    def _visible_rows(self, H, th):
        """Number of content rows that fit between the (optional) title and softkey bars."""
        return (H - self._top_h(th) - self._bot_h(th) - 2) // th.row_h

    def _softbar_back(self, app, x, y, W, H):
        """Touch affordance: a tap in the softkey bar's right third acts as B (pop the screen)."""
        th = app.th
        if th.soft_bar and y >= H - th.bar_h and x > W * 2 // 3:
            return app.pop()
        return False

    def _titlebar(self, p, W, title, right=None):
        th = p.th
        if not th.title_bar:
            return
        p.fill(0, 0, W, th.bar_h, th.bar_bg)
        p.text(th.pad, th.text_dy, title, th.bar_fg)
        if right:
            p.rtext(W - th.pad, th.text_dy, right, th.bar_fg)
        p.hline(0, th.bar_h, W, th.border)

    def _softbar(self, p, W, H, left="", right="B: back"):
        th = p.th
        if not th.soft_bar:
            return H
        by = H - th.bar_h
        p.fill(0, by, W, th.bar_h, th.bar_bg)
        p.hline(0, by, W, th.border)
        if left:
            p.text(th.pad, by + th.text_dy, left, th.bar_fg)
        if right:
            p.rtext(W - th.pad, by + th.text_dy, right, th.bar_fg)
        return by


class Screen(View):
    def __init__(self, title, widgets):
        self.title = title
        self.widgets = widgets
        self.top = 0
        self.sel = -1
        for i, wdg in enumerate(widgets):
            if wdg.focusable:
                self.sel = i
                break

    def _move(self, d):
        self.sel, changed = _next_focusable(self.widgets, self.sel, d)
        return changed

    def focused_adjustable(self):
        return 0 <= self.sel < len(self.widgets) and self.widgets[self.sel].adjustable

    def _scroll(self, app, d):
        rows = self._visible_rows(app.H, app.th)
        top = min(max(0, len(self.widgets) - rows), max(0, self.top + d))
        if top == self.top:
            return False
        self.top = top
        return True

    def _mark_row(self, app, i):                     # mark row i's rect if it is on-screen
        if self.top <= i < self.top + self._visible_rows(app.H, app.th):
            y = self._top_h(app.th) + 2 + (i - self.top) * app.th.row_h
            app.mark(y, y + app.th.row_h)

    def key(self, app, k):
        if self.sel < 0:                             # no focusable widget: U/D scroll the content
            if k == "U":
                return self._scroll(app, -1)         # a scroll shifts every row -> full (no mark)
            if k == "D":
                return self._scroll(app, 1)
            if k == "B":
                return app.pop()
            return False
        if k in ("U", "D"):
            old = self.sel
            if not self._move(-1 if k == "U" else 1):
                return False
            rows = self._visible_rows(app.H, app.th)
            if self.top <= self.sel < self.top + rows:   # no scroll: repaint the old + new rows...
                self._mark_row(app, old)
                self._mark_row(app, self.sel)
                # ...and the softbar ONLY if the hint changed. Skipping it keeps the dirty region a
                # contiguous couple of rows (small bounding box) instead of stretching to the bottom bar,
                # so the backend redraws + pushes far less on a plain focus move.
                if self.widgets[old].hint() != self.widgets[self.sel].hint():
                    app.mark(app.H - self._bot_h(app.th), app.H)
            else:
                app.invalidate()                     # focus scrolled off-screen -> full repaint
            return True
        if k == "B":
            return app.pop()
        if self.widgets[self.sel].key(app, k):       # value change: only the focused row (sel >= 0 here)
            self._mark_row(app, self.sel)
            return True
        return False

    def char(self, app, ch):                             # route a typed char to the focused widget
        if 0 <= self.sel < len(self.widgets) and self.widgets[self.sel].char(app, ch):
            self._mark_row(app, self.sel)
            return True
        return False

    def draw(self, p, W, H):
        th = p.th
        p.fill(0, 0, W, H, th.bg)
        self._titlebar(p, W, self.title)
        y0 = self._top_h(th) + 2
        rows = self._visible_rows(H, th)                     # visible content rows
        n = len(self.widgets)
        if self.sel >= 0:                                    # keep focus on screen (scroll)
            if self.sel < self.top:
                self.top = self.sel
            elif self.sel >= self.top + rows:
                self.top = self.sel - rows + 1
        scrollable = n > rows
        cw = W - 3 if scrollable else W                      # reserve a right gutter for the scrollbar
        y = y0
        for i in range(self.top, min(n, self.top + rows)):
            if p.visible(y, th.row_h):                       # skip rows outside the current band
                self.widgets[i].draw(p, 0, y, cw, i == self.sel)
            y += th.row_h
        if scrollable:                                       # right-edge scrollbar thumb (position + size)
            track = rows * th.row_h
            thumb = max(3, track * rows // n)
            self.top = min(self.top, n - rows)               # clamp before positioning the thumb
            ty = y0 + (track - thumb) * self.top // (n - rows)
            p.fill(W - 2, ty, 2, thumb, th.fg)
        hint = self.widgets[self.sel].hint() if 0 <= self.sel < len(self.widgets) else ""
        self._softbar(p, W, H, hint, "B: back")

    def hit(self, app, x, y, W, H):
        if self._softbar_back(app, x, y, W, H):
            return True
        th = app.th
        y0 = self._top_h(th) + 2
        rows = self._visible_rows(H, th)
        if not (y0 <= y < y0 + rows * th.row_h):     # tap outside the content rows
            return False
        scrollbar = len(self.widgets) > rows
        w = W - 3 if scrollbar else W                # match draw()'s scrollbar gutter (tap width == drawn)
        if scrollbar and x >= w:                     # tap in the reserved scrollbar gutter, not on a row
            return False
        i = self.top + (y - y0) // th.row_h          # which row (self.top is current from last draw)
        if 0 <= i < len(self.widgets) and self.widgets[i].focusable:
            moved = self.sel != i                    # a focus move is itself a visible change
            self.sel = i
            acted = self.widgets[i].touch(app, x, y - (y0 + (i - self.top) * th.row_h), w)
            return acted or moved
        return False


# ---------------------------------------------------------------- controller
class Session:
    """Backend-neutral owner of the view stack, geometry, theme, input dispatch and dirty state. Screens
    and widgets receive this as `app` (app.push/pop, app.W/H/th). `exit()` lets a run() loop hand control
    back to the host app; `exit_on_root_back` maps back on the root screen to exit().

    Dirty tracking is either FULL (repaint the whole screen) or a list of absolute Y `spans` (repaint only
    those rows). A view narrows a change with `app.mark(y0, y1)` (e.g. a focus move marks the old row, the
    new row, and the softkey bar); a view that reports a change without marking falls back to full. The
    displayio backend repaints only the strips a span touches; picogame collapses any dirty to a full
    StripDraw repaint (its layer invalidation is whole-screen)."""
    def __init__(self, theme=None, W=0, H=0, exit_on_root_back=False):
        self.th = theme or Theme()
        self.W = W
        self.H = H
        self.stack = []
        self._full = True                              # whole screen pending
        self._spans = []                               # else a list of (y0, y1) absolute row ranges
        self.running = False
        self.active = False                            # encoder edit mode: rotation adjusts the focused
                                                       # value instead of moving focus (see rotate/press)
        self.exit_on_root_back = exit_on_root_back
        self._painter = Painter(None, 0, 0, self.th)   # reused across bands/frames (no per-band alloc)

    @property
    def screen(self):
        return self.stack[-1] if self.stack else None

    @property
    def dirty(self):
        return self._full or bool(self._spans)

    def start(self, root):
        """Reset to a single root screen and arm the loop. run() calls this, so re-entering the UI never
        retains a previous stack (its screens/widgets/callbacks are released)."""
        self.stack = [root]
        self.active = False
        self.invalidate()
        self.running = True

    def exit(self):
        """Leave the UI: end the run() loop so control returns to the caller. Call it from any widget
        callback (a Button's on_press, a Link) via the `app` it receives: Button("Exit", lambda a: a.exit())."""
        self.running = False

    def push(self, screen):
        self.stack.append(screen)
        self.invalidate()

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()
            self.invalidate()
            return True
        return False

    def invalidate(self):
        """Mark the whole screen for repaint."""
        self._full = True

    def mark(self, y0, y1):
        """Mark the absolute rows [y0, y1) as changed (a partial repaint). A view calls this instead of
        invalidate() when it knows exactly which rows changed; ignored once a full repaint is pending.
        Overlapping spans merge in place, so a row marked twice in one pump stays ONE span (no duplicate
        tuple, and picogame - which repaints partially only for a single span - isn't forced to full)."""
        if self._full or y1 <= y0:
            return
        spans = self._spans
        for i in range(len(spans)):
            a, b = spans[i]
            if y0 <= b and a <= y1:                  # overlaps OR touches an existing span
                if a <= y0 and y1 <= b:              # fully contained -> nothing to do (no tuple churn)
                    return
                y0 = a if a < y0 else y0             # widen to the union...
                y1 = b if b > y1 else y1
                spans[i] = (y0, y1)
                j = i + 1                            # ...then cascade: absorb any later spans the widened
                while j < len(spans):                # range now touches/overlaps (a mark can bridge two)
                    c, e = spans[j]
                    if y0 <= e and c <= y1:
                        y0 = c if c < y0 else y0
                        y1 = e if e > y1 else y1
                        spans[i] = (y0, y1)
                        del spans[j]
                    else:
                        j += 1
                return
        spans.append((y0, y1))

    def set_theme(self, theme):
        """Swap the live Theme (the whole stack repaints with it next frame)."""
        self.th = theme
        self.invalidate()

    # Public input: call these named methods to drive the UI. up/down/left/right move focus (and L/R
    # adjust the focused value); ok activates/confirms; back cancels/pops (and exits on the root screen).
    def up(self):    self._dispatch("U")
    def down(self):  self._dispatch("D")
    def left(self):  self._dispatch("L")
    def right(self): self._dispatch("R")
    def ok(self):    self._dispatch("A")

    def back(self):
        """Cancel: leave encoder edit mode if active, else pop the screen (exits on the root)."""
        if self.active:
            self.active = False
            self.invalidate()
            return
        self._dispatch("B")

    # Rotary-encoder mode (one knob + switch). rotate turns the knob; press is the switch. Turning moves
    # focus, or edits the focused value while active; the switch enters/leaves active, or fires an action.
    # The app maps its hardware (encoder / a few buttons) to these; a long press maps to back(). See
    # the focus-nav README section and examples/encoder_demo.py / buttons_demo.py.
    def rotate(self, d):
        """Encoder turn: d>0 = clockwise. Moves focus (normally), or changes the focused value (active)."""
        if self.active:
            self.right() if d > 0 else self.left()
        else:
            self.down() if d > 0 else self.up()

    def press(self):
        """Encoder switch (short press). On a value item (Choice/IntField/Slider) it enters active so the
        knob edits the value, and a second press leaves active; on an action (Button/Link/Toggle) it fires."""
        if not self.stack:
            return
        if self.active:
            self.active = False
            self.invalidate()
        elif self.stack[-1].focused_adjustable():
            self.active = True
            self.invalidate()
        else:
            self.ok()

    def _dispatch(self, k):
        """Route one logical key to the top screen (internal code U/D/L/R/A/B; the public entry points
        are up()/down()/left()/right()/ok()/back()). The view marks what changed (mark/invalidate); a
        reported change with no marks falls back to full. back on the root screen stops if
        exit_on_root_back."""
        if not self.stack:
            return
        if k == "B" and len(self.stack) == 1 and self.exit_on_root_back:
            self.exit()
            return
        if self.stack[-1].key(self, k) and not self.dirty:
            self.invalidate()

    def char(self, ch):
        """Dispatch a typed character to the top screen; repaints only if a widget consumes it."""
        if self.stack and self.stack[-1].char(self, ch) and not self.dirty:
            self.invalidate()

    def touch(self, x, y):
        """Dispatch a tap at (x, y) to the top screen's hit-test; repaints if consumed. Taps outside the
        UI area (0,0)-(W,H) are ignored - so a viewport-translated tap that lands in the bezel, or any
        out-of-range coordinate from a touch source, hits nothing."""
        if not (0 <= x < self.W and 0 <= y < self.H):
            return
        if self.stack and self.stack[-1].hit(self, x, y, self.W, self.H) and not self.dirty:
            self.invalidate()

    def peek_dirty(self):
        """Return the pending repaint WITHOUT clearing it: "full", the live list of (y0, y1) spans, or
        None if clean. A backend paints from this and then calls ack_dirty() only after the push
        succeeds, so a failed bus/refresh leaves the dirty state intact for a retry. The returned span
        list is live (reused across frames) - read it, never mutate or retain it."""
        if self._full:
            return "full"
        if self._spans:
            return self._spans
        return None

    def ack_dirty(self):
        """Clear the pending repaint after a successful push. Empties the span list in place, so the
        per-frame path allocates no new list."""
        self._full = False
        del self._spans[:]

    def take_dirty(self):
        """Peek + ack in one call: return the pending repaint ("full", a fresh list of spans, or None)
        and clear it. For standalone/manual renders and tests; backends prefer peek_dirty()/ack_dirty()
        so a failed push can be retried."""
        d = self.peek_dirty()
        if d == "full":
            self.ack_dirty()
            return "full"
        if d:
            snap = list(d)                           # snapshot: ack_dirty empties the live list
            self.ack_dirty()
            return snap
        return None

    def draw_top(self, view, vx, vy, vh=0):
        """Paint the top screen into `view` (origin vx,vy, band height vh) through the reused Painter."""
        if self.stack:
            self._painter.reset(view, vx, vy, self.th, vh, self.active)
            self.stack[-1].draw(self._painter, self.W, self.H)


# ---------------------------------------------------------------- backend facade
class _AppFacade:
    """Mixin giving every backend the same public controller API by delegating to `self.session` and
    repainting through `self._flush()`. A backend supplies __init__ (bootstrap + self.session), _flush()
    (push to its panel) and run(); one that insets/transforms touch (e.g. a viewport) overrides touch().
    This is the single source of the input surface - add a Session verb here, not in three backends.

    Repaints are COALESCED: every verb runs inside `_do`, which defers `_flush()` until the outermost
    call unwinds and paints once if anything went dirty. So a `source.pump()` that drains five encoder
    detents (or a callback that fires another verb) produces ONE panel push, not five."""
    _defer = 0                                       # re-entrancy depth; >0 = don't paint yet

    def _do(self, fn, *a):
        """Run a session mutation, then paint once when the outermost _do unwinds (if it went dirty).
        Returns the mutation's own result, so facade verbs match their Session counterparts (e.g.
        `app.pop()` reports whether a screen was popped, like `session.pop()`)."""
        self._defer += 1
        try:
            r = fn(*a)
        finally:
            self._defer -= 1
        if self._defer == 0 and self.session.dirty:
            self._flush()
        return r

    def run_pump(self, source):
        """Drain one input source cycle as a single coalesced transaction (used by the run loops)."""
        self._do(source.pump, self)

    def up(self):        return self._do(self.session.up)
    def down(self):      return self._do(self.session.down)
    def left(self):      return self._do(self.session.left)
    def right(self):     return self._do(self.session.right)
    def ok(self):        return self._do(self.session.ok)
    def back(self):      return self._do(self.session.back)
    def rotate(self, d): return self._do(self.session.rotate, d)
    def press(self):     return self._do(self.session.press)
    def char(self, ch):  return self._do(self.session.char, ch)
    def touch(self, x, y): return self._do(self.session.touch, x, y)
    def push(self, screen): return self._do(self.session.push, screen)
    def pop(self):       return self._do(self.session.pop)
    def invalidate(self): return self._do(self.session.invalidate)
    def set_theme(self, theme): return self._do(self.session.set_theme, theme)

    def exit(self):
        """Leave run()'s loop; control returns to the caller."""
        self.session.exit()

    @property
    def W(self):
        return self.session.W

    @property
    def H(self):
        return self.session.H

    @property
    def th(self):
        return self.session.th

    @property
    def stack(self):
        return self.session.stack

