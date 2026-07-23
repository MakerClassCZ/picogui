# picogui_dispbase: shared lifecycle for the displayio-push backends (picogui_mono, picogui_fb).
#
# These backends render a full-frame surface into a displayio.Bitmap and let display.refresh() push it -
# UNLIKE picogui_rgb, which owns the bus and streams RGB565 strips itself. Everything those two share
# lives here: display takeover/handback (swap root_group + save/restore auto_refresh), the
# peek -> clip -> draw -> refresh -> ack flush (failure-atomic: ack only after a successful refresh), and
# the deadline-paced run loop. A concrete backend subclasses _DisplayioApp and supplies only
# `_build(display) -> (surface, displayio.Group)` (its Bitmap + shader + Surface). Kept as its own module
# so a mono build does not pull the colour backend and vice versa (like picogui_glyph).
import picogui as ui
import bitmaptools                                  # a standard CircuitPython module (C region fills)
from picogui_glyph import _bbox, _glyph_flat


class _BitmapSurface:
    """picogui's Painter primitives drawn into a displayio.Bitmap, shared by picogui_mono (1bpp) and
    picogui_fb (16bpp colour). The ONLY per-backend difference is `_val(color)` - what value a colour
    maps to in THIS bitmap (mono: 1/0 on-off; fb: the RGB565 int itself). Colour is constant within a
    primitive, so `_val` is applied once per call, not per pixel.

    Rectangle fills go through `bitmaptools.fill_region` (C); text and diagonal lines are per-pixel. A
    vertical CLIP window [_cy0, _cy1) bounds every write, so a partial repaint touches only the dirty
    rows (the rest keep the previous frame; displayio pushes the diff)."""
    def __init__(self, bitmap):
        self.w = bitmap.width
        self.h = bitmap.height
        self.bmp = bitmap
        self._cy0 = 0
        self._cy1 = bitmap.height

    def _val(self, color):
        raise NotImplementedError                    # subclass: colour -> bitmap value

    def set_clip(self, y0, y1):
        """Bound writes to absolute rows [y0, y1) (clamped). Reset to full height for a full repaint."""
        self._cy0 = max(0, y0)
        self._cy1 = min(self.h, y1)

    # NB: displayio.Bitmap accepts a LINEAR int index (y*width+x) as well as an (x,y) tuple; the linear
    # form allocates nothing, while `bmp[x, y]` builds a throwaway tuple per pixel. The per-pixel hot
    # paths below (pixel, diagonal line, text) use the linear form to avoid heap churn on constrained
    # (mono RP2040) hardware.
    def color_at(self, x, y):                        # raw bitmap value of one pixel (tests / preview)
        return self.bmp[y * self.w + x]

    def _fill(self, x0, y0, x1, y1, v):              # x0<x1, y already clamped to the clip window
        bitmaptools.fill_region(self.bmp, x0, y0, x1, y1, v)

    def clear(self, color):
        v = self._val(color)
        if self._cy0 <= 0 and self._cy1 >= self.h:
            self.bmp.fill(v)                         # whole buffer (fast C)
        else:
            self._fill(0, self._cy0, self.w, self._cy1, v)   # honour the clip window

    def pixel(self, x, y, color):
        if 0 <= x < self.w and self._cy0 <= y < self._cy1:
            self.bmp[y * self.w + x] = self._val(color)

    def fill_rect(self, x, y, w, h, color):
        x0 = max(0, x); x1 = min(self.w, x + w)
        y0 = max(self._cy0, y); y1 = min(self._cy1, y + h)   # clamp to the clip window
        if x1 <= x0 or y1 <= y0:
            return
        self._fill(x0, y0, x1, y1, self._val(color))

    def line(self, x0, y0, x1, y1, color):
        if y0 == y1:                                 # horizontal -> a 1px-high rect (fast)
            self.fill_rect(min(x0, x1), y0, abs(x1 - x0) + 1, 1, color)
        elif x0 == x1:                               # vertical -> a 1px-wide rect
            self.fill_rect(x0, min(y0, y1), 1, abs(y1 - y0) + 1, color)
        else:                                        # diagonal -> Bresenham, per-pixel (clip inline)
            v = self._val(color)
            bmp = self.bmp
            cy0, cy1, w = self._cy0, self._cy1, self.w
            dx = abs(x1 - x0); dy = -abs(y1 - y0)
            sx = 1 if x0 < x1 else -1; sy = 1 if y0 < y1 else -1
            err = dx + dy
            while True:
                if 0 <= x0 < w and cy0 <= y0 < cy1:
                    bmp[y0 * w + x0] = v
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy; x0 += sx
                if e2 <= dx:
                    err += dx; y0 += sy

    def text(self, x, y, s, color, font, bg=None):
        fw, fh = _bbox(font)
        bmp = self.bmp
        cy0, cy1, sw = self._cy0, self._cy1, self.w
        fg = self._val(color)
        bgv = None if bg is None else self._val(bg)
        for ch in s:
            flat = _glyph_flat(font, ord(ch), fw, fh)   # flat fw*fh mask, 1 = foreground
            for gy in range(fh):
                cyp = y + gy
                if not (cy0 <= cyp < cy1):              # row outside the clip window
                    continue
                row = gy * fw
                base = cyp * sw                          # linear row base (no per-pixel (x,y) tuple)
                for gx in range(fw):
                    xp = x + gx
                    if 0 <= xp < sw:
                        if flat[row + gx]:
                            bmp[base + xp] = fg
                        elif bgv is not None:
                            bmp[base + xp] = bgv
            x += fw

    def blit(self, bm, x, y):
        raise NotImplementedError("bitmap Icon blit is unsupported on the displayio-Bitmap backends; "
                                  "use mask icons")


class _DisplayioApp(ui._AppFacade):
    """Base for backends that render into a displayio.Bitmap and push via display.refresh(). Subclasses
    implement `_build`. The stack/dispatch/theme live in self.session; the input API comes from
    ui._AppFacade; run(screen, source) drives it like the other backends."""
    def __init__(self, display, theme, exit_on_root_back=True):
        self._display = display
        self._saved = None
        self.source = None
        self.session = ui.Session(theme, display.width, display.height,
                                  exit_on_root_back=exit_on_root_back)
        self.surf, self._group = self._build(display)

    def _build(self, display):
        """Return (surface, displayio.Group). The surface implements picogui's Painter primitives plus
        set_clip(y0, y1); the group holds a TileGrid over the backing Bitmap."""
        raise NotImplementedError

    # -- display takeover / handback -------------------------------------------------------
    def acquire(self):
        """Take the display over: stop its auto-refresh, swap in our group. Idempotent. (Every supported
        displayio display has auto_refresh + root_group; we don't guard for ones that don't.)"""
        if self._saved is not None:
            return
        d = self._display
        self._saved = (d.auto_refresh, d.root_group)   # set BEFORE mutating so release() can roll back
        try:
            d.auto_refresh = False
            d.root_group = self._group
        except Exception:
            self.release()                           # self-rollback: a failed `with` won't get __exit__
            raise

    def release(self):
        """Hand the display back: restore its root_group + auto_refresh. Idempotent."""
        if self._saved is None:
            return
        ar, rg = self._saved
        self._saved = None
        self._display.root_group = rg                # restore the host group FIRST, then re-enable
        self._display.auto_refresh = ar              # auto-refresh - else a refresh could present our
        #                                              (now-detached) frame once more before the swap

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    def _flush(self):
        if self._saved is None:                      # not acquired yet: don't refresh the HOST's live
            return                                   # display. Dirty stays pending; run()/acquire() paints.
        d = self.session.peek_dirty()                # peek, not take: ack only after refresh() returns,
        if not d:                                    # so a failed refresh leaves the frame dirty to retry
            return
        if d == "full":
            self.surf.set_clip(0, self.surf.h)
        else:
            y0 = self.surf.h                         # bounding span of the dirty rows, in one pass
            y1 = 0                                   # (no min()/max() generator temporaries)
            for a, b in d:
                if a < y0:
                    y0 = a
                if b > y1:
                    y1 = b
            self.surf.set_clip(y0, y1)               # only redraw the dirty rows
        self.session.draw_top(self.surf, 0, 0)
        self.surf.set_clip(0, self.surf.h)           # reset so later direct draws aren't clipped
        self._display.refresh()
        self.session.ack_dirty()

    def render(self):
        """Force a full repaint (benchmarks / manual redraws). Parity with picogui_rgb.render()."""
        self.session.invalidate()
        self._flush()

    def run(self, root, source, fps=30):
        """Drive from a source (an object with pump(app)). Takes the display over on entry (inside the
        try, so a mid-acquire/paint failure still hands it back), releases on exit. `fps` caps the loop
        rate (input poll), not the draw rate - the UI repaints only on change, deadline-paced."""
        import time
        period = 1.0 / fps
        self.source = source
        try:
            self.acquire()
            self.session.start(root)                 # start() already invalidates -> full initial paint
            self._flush()                            # initial paint
            while self.session.running:
                t0 = time.monotonic()
                self.run_pump(source)                # drain input, repaint once if dirty
                dt = time.monotonic() - t0
                if dt < period:                      # sleep only the remainder (0 after a slow repaint)
                    time.sleep(period - dt)
        finally:
            self.release()                           # hand the display back
