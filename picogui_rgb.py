# picogui_rgb: stock-CircuitPython backend for an SPI COLOUR panel (ST7789 / GC9A01 / ...). It OWNS the
# display bus and streams small W x strip_h RGB565 strips (CASET/RASET/RAMWR) - so its RAM is one tiny
# strip buffer, the small-RAM default for RP2040 / ESP32-S3 bus panels. `Surface` is the software RGB565
# strip blitter; `App` takes the panel over (acquire/release) and delegates stack/dispatch/theme to
# picogui.Session. Input + touch are the developer's (KeypadSource / TouchSource); see the README.
#
# Sibling backends (pick by hardware): picogui_mono (1bpp OLED, renders a displayio.Bitmap),
# picogui_fb (colour framebuffer / DVI, needs a full-frame W*H*2 buffer -> PSRAM-class RAM),
# picogui_picogame (the picogame engine). mono/fb share picogui_dispbase; rgb stands alone (own-bus).
import struct

import picogui as ui
from picogui_glyph import _bbox, _glyph_flat, clear_glyph_cache   # shared software rasteriser + cache


def _fill2(mv, start, end):
    """Replicate the 2-byte seed at mv[start:start+2] across mv[start:end] by doubling the filled span.
    `mv` is a memoryview, so each slice assignment moves bytes in place with NO pixel-DATA copy (no
    bytes/bytearray temporary). It is not zero-allocation: each RHS `mv[a:b]` makes a small, short-lived
    memoryview header (~log2(n) of them per fill), which the doubling minimises. Source and destination
    spans never overlap (take <= filled)."""
    filled = 2
    n = end - start
    while filled < n:
        take = filled if filled < n - filled else n - filled
        mv[start + filled:start + filled + take] = mv[start:start + take]
        filled += take


class Surface:
    """A software strip buffer implementing picogui's surface primitives. `buf` is a bytearray of
    w*h*2 bytes in panel wire order (the two bytes of an rgb565() int, low byte first), pushed to the
    display without conversion. Reused across bands by App. Bulk fills go through the retained `mv`
    (a memoryview of `buf`): they copy NO pixel data via temporaries, though the slice-doubling makes a
    few small transient memoryview headers per fill (see _fill2)."""
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 2)
        self.mv = memoryview(self.buf)

    def clear(self, color):
        self.buf[0] = color & 0xFF
        self.buf[1] = color >> 8
        _fill2(self.mv, 0, len(self.buf))            # slice-double the 2-byte seed over the buffer

    def color_at(self, x, y):                        # int colour of one pixel (tests/inspection)
        i = (y * self.w + x) * 2
        return self.buf[i] | (self.buf[i + 1] << 8)

    def pixel(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 2
            self.buf[i] = color & 0xFF
            self.buf[i + 1] = color >> 8

    def fill_rect(self, x, y, w, h, color):
        x0 = max(0, x); x1 = min(self.w, x + w)
        y0 = max(0, y); y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        mv = self.mv
        sw2 = self.w * 2
        rowbytes = (x1 - x0) * 2
        base0 = y0 * sw2 + x0 * 2                     # build the first row by doubling...
        self.buf[base0] = color & 0xFF
        self.buf[base0 + 1] = color >> 8
        _fill2(mv, base0, base0 + rowbytes)
        src = mv[base0:base0 + rowbytes]             # a view (no copy); target rows never overlap it
        for yy in range(y0 + 1, y1):                 # ...then copy that row span to the rest
            base = yy * sw2 + x0 * 2
            mv[base:base + rowbytes] = src

    def line(self, x0, y0, x1, y1, color):
        if y0 == y1:                                 # horizontal -> a 1px-high rect
            self.fill_rect(min(x0, x1), y0, abs(x1 - x0) + 1, 1, color)
        elif x0 == x1:                               # vertical -> a 1px-wide rect
            self.fill_rect(x0, min(y0, y1), 1, abs(y1 - y0) + 1, color)
        else:
            dx = abs(x1 - x0); dy = -abs(y1 - y0)
            sx = 1 if x0 < x1 else -1; sy = 1 if y0 < y1 else -1
            err = dx + dy
            while True:
                self.pixel(x0, y0, color)
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy; x0 += sx
                if e2 <= dx:
                    err += dx; y0 += sy

    def text(self, x, y, s, fg, font, bg=None):
        fw, fh = _bbox(font)                          # memoized (no per-call tuple allocs)
        if y >= self.h or y + fh <= 0:               # whole run outside this strip: nothing to draw
            return
        lo = fg & 0xFF
        hi = fg >> 8
        blo = None if bg is None else (bg & 0xFF)
        bhi = None if bg is None else (bg >> 8)
        b = self.buf
        sw = self.w
        for ch in s:
            flat = _glyph_flat(font, ord(ch), fw, fh)   # flat fw*fh mask, 1 = foreground
            gx0 = 0 if x >= 0 else -x                 # visible column span, computed once per glyph
            gx1 = fw if x + fw <= sw else sw - x
            if gx0 < gx1:
                for gy in range(fh):
                    cy = y + gy
                    if 0 <= cy < self.h:
                        row = gy * fw
                        base = (cy * sw + x) * 2
                        for gx in range(gx0, gx1):
                            i = base + gx * 2
                            if flat[row + gx]:
                                b[i] = lo; b[i + 1] = hi
                            elif bg is not None:
                                b[i] = blo; b[i + 1] = bhi
            x += fw

    def blit(self, bm, x, y):
        # Full-colour bitmap icons (Icon(bitmap=...)) need a panel-specific format; not supported on this
        # backend. Built-in mask icons use pixel() and work. Use mask icons, or add a bitmap protocol.
        raise NotImplementedError("bitmap Icon blit is not supported on the rgb strip backend; "
                                  "use a mask Icon")


class KeypadSource:
    """Adapt a developer-owned `keypad` scanner to picogui's logical input: build the keypad object
    yourself (keypad.Keys or keypad.KeyMatrix) and map key numbers to the action each fires:
        nav   = {key_number: 'up'/'down'/'left'/'right'/'ok'/'back'}
        chars = {key_number: 'a'}          # optional: type into the focused text field
    Pass it as the `source` to App.run, or call pump(app) from your own loop. See the README."""
    def __init__(self, keys, nav=None, chars=None):
        import keypad
        self.keys = keys
        self.nav = nav or {}
        self.chars = chars or {}
        self._ev = keypad.Event()            # reused (no per-event alloc)

    def pump(self, app):
        ev = self._ev
        q = self.keys.events
        while q.get_into(ev):
            if not ev.pressed:               # act on key-down only
                continue
            kn = ev.key_number
            if kn in self.nav:
                getattr(app, self.nav[kn])()     # nav value is 'up'/'down'/'left'/'right'/'ok'/'back'
            elif kn in self.chars:
                app.char(self.chars[kn])


class TouchSource:
    """Adapt a developer-owned touchscreen to picogui. Pass a `read()` returning an (x, y) panel-pixel
    tuple while touched, else None. Fires app.touch(x, y) once on the press edge (a held finger does not
    re-fire). Build/calibrate the touch driver yourself; see the README."""
    def __init__(self, read):
        self.read = read                     # callable -> (x, y) while touched, else None/falsey
        self._down = False

    def pump(self, app):
        p = self.read()
        if p and not self._down:             # press edge only (touch-down)
            self._down = True
            app.touch(int(p[0]), int(p[1]))
        elif not p:
            self._down = False               # released -> arm the next tap


class App(ui._AppFacade):
    """Runs picogui on stock CircuitPython and shares the panel with a host app's displayio UI. The
    stack/dispatch/theme/dirty live in picogui.Session; this adds the software present path and input.
    The public input API (up/down/.../push/pop/W/H/th) comes from ui._AppFacade; touch is overridden to
    map panel pixels into the viewport.

    Takeover is explicit and reversible: acquire() saves the app's root_group + auto_refresh and grabs
    the bus; release() restores them so the app's UI repaints unchanged. `with App() as app:` does
    both; run() acquires on entry and releases on exit and returns when exit()/back-on-root ends the loop.

    Panel: assumes a FourWire/MIPI-DCS RGB565 display (column/row/ram commands + start offsets are
    configurable). `sink(surface, top, h)` overrides the push for the desktop harness (no panel touched;
    the surface is reused between bands, so a capturing sink must copy). See the README."""
    def __init__(self, display=None, theme=None, strip_h=16, sink=None, exit_on_root_back=True,
                 col_cmd=0x2A, row_cmd=0x2B, ram_cmd=0x2C, colstart=0, rowstart=0, viewport=None):
        # display first (required in practice), matching picogui_mono / picogui_fb - so App(a_display)
        # is never mistaken for a theme.
        if strip_h <= 0:
            raise ValueError("strip_h must be positive")
        theme = theme or ui.Theme()
        self._sink = sink
        self.source = None                           # set by run(); parity with mono/fb/picogame
        self._display = None
        self._acquired = False
        self._saved = None
        self.bus = None
        self._col_cmd = col_cmd
        self._row_cmd = row_cmd
        self._ram_cmd = ram_cmd
        self._colstart = colstart
        self._rowstart = rowstart
        W = H = 0
        if display is None and sink is None:
            display = picogame_game.display()
        if display is not None:
            self._display = display
            W = display.width
            H = display.height
        if not W or not H:
            raise ValueError("no display geometry: pass a display (or a display-like object with "
                             "width/height when using a sink)")
        self._fullW, self._fullH = W, H
        # viewport (x,y,w,h): draw the whole UI into a sub-rect of the panel (e.g. a square inscribed in
        # a round display); the border outside it is cleared to the theme bg once, on acquire.
        if viewport is None:
            vx = vy = 0
            vw, vh = W, H
        else:
            vx, vy, vw, vh = viewport
            if vw <= 0 or vh <= 0 or vx < 0 or vy < 0 or vx + vw > W or vy + vh > H:
                raise ValueError("viewport must fit inside the display")
        self._vx = vx
        self._vy = vy
        self._inset = bool(vx or vy or vw != W or vh != H)
        self.strip_h = min(strip_h, vh)              # no point allocating a band taller than the viewport
        self.session = ui.Session(theme, vw, vh, exit_on_root_back=exit_on_root_back)
        self._strip = Surface(vw, self.strip_h)      # one reused band buffer (no per-band alloc)
        self._colwin = bytearray(4)                  # reused CASET/RASET args (struct.pack_into)
        self._rowwin = bytearray(4)
        self._clearcw = bytearray(4)                 # retained 4-byte CASET window for the border clear
        #                                              (the pixels reuse self._strip - no 2nd framebuffer)
        struct.pack_into(">HH", self._colwin, 0, colstart + vx, colstart + vx + vw - 1)

    # -- display takeover / handback ---------------------------------------------------------
    def acquire(self):
        """Take over the panel: save the app's root_group + auto_refresh, stop auto-refresh, detach the
        group and grab the bus. Idempotent; a no-op with a sink or no display."""
        if self._acquired or self._sink is not None or self._display is None:
            self._acquired = True
            return
        d = self._display
        self._saved = (d.auto_refresh, d.root_group)   # supported displays have both; no per-attr guards
        self._acquired = True                        # set BEFORE the irreversible detach, so release()
        try:                                         # can undo everything if a later step raises
            d.auto_refresh = False
            d.root_group = None
            self.bus = d.bus                         # may raise on an odd display
            if self._inset:
                self._clear_panel(self.th.bg)        # blank the border outside the viewport, once
        except Exception:
            self.release()                           # self-rollback: __enter__ won't get its __exit__
            raise

    def release(self):
        """Hand the panel back: restore the app's root_group + auto_refresh so its UI repaints. Idempotent."""
        if not self._acquired or self._sink is not None or self._display is None:
            self._acquired = False
            return
        ar, rg = self._saved
        self.bus = None
        self._acquired = False
        self._saved = None                           # drop the old root_group ref (don't pin host UI)
        self._display.root_group = rg
        self._display.auto_refresh = ar

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    def touch(self, x, y):
        """Override: map the panel pixel into the viewport before hit-testing (Session.touch drops taps
        that fall outside it)."""
        self._do(self.session.touch, x - self._vx, y - self._vy)

    def _flush(self):
        d = self.session.peek_dirty()                # peek, not take: only ack after the push succeeds,
        if d:                                        # so a bus exception leaves the frame dirty to retry
            self._paint(d)
            self.session.ack_dirty()

    def render(self):
        """Force a full repaint and CLEAR the pending dirty state (benchmarks / manual redraws). Same
        contract as picogui_dispbase.render(): invalidate -> flush -> ack, so no repaint is left pending
        for the next facade op."""
        self.session.invalidate()
        self._flush()

    def _paint(self, dirty):
        """Repaint. `dirty` is "full" (all strips) or a list of (y0, y1) spans (only the strips those
        touch) - so a focus move pushes ~1-2 strips over SPI instead of the whole panel."""
        if not self.session.stack:
            return
        if self._sink is None and not self._acquired:
            raise RuntimeError("App must acquire() the display before rendering "
                               "(use `with App() as app:` or call app.run())")
        strip = self._strip
        bg = self.th.bg
        full = dirty == "full"
        for top in range(0, self.H, self.strip_h):
            h = min(self.strip_h, self.H - top)
            if not full:                             # skip strips no dirty span touches (spans may be
                bottom = top + h                     # disjoint - old row + softbar - so test each, no
                hit = False                          # bounding box, and no per-strip generator alloc)
                for y0, y1 in dirty:
                    if y0 < bottom and y1 > top:
                        hit = True
                        break
                if not hit:
                    continue
            strip.clear(bg)
            self.session.draw_top(strip, 0, top, h)  # band height -> off-band culling
            self._push_band(strip, top, h)

    def _push_band(self, surf, top, h):
        if self._sink is not None:
            self._sink(surf, top, h)
            return
        ry = self._rowstart + self._vy + top         # viewport row offset on the panel
        struct.pack_into(">HH", self._rowwin, 0, ry, ry + h - 1)
        self.bus.send(self._col_cmd, self._colwin)
        self.bus.send(self._row_cmd, self._rowwin)
        n = self.W * h * 2                           # only the used rows of the reused buffer
        self.bus.send(self._ram_cmd, surf.buf if n == len(surf.buf) else surf.mv[:n])

    def _clear_panel(self, color):
        """Fill the WHOLE panel with `color` (once on acquire when a viewport insets the UI, so the border
        around it is clean). REUSES the band we already hold (self._strip) rather than a second full-width
        buffer: a solid fill means any contiguous run of w*h*2 bytes paints w*h pixels of the colour, so
        the band tiles over the whole panel in vw-wide, strip_h-tall chunks - even the partial edge ones."""
        if self._sink is not None:
            return
        fw, fh = self._fullW, self._fullH
        strip = self._strip
        strip.clear(color)                           # paint the shared band bg (the first UI paint overwrites it)
        buf, mv, vw = strip.buf, strip.mv, strip.w
        cw, rw = self._clearcw, self._rowwin         # 4-byte windows only - never the viewport _colwin
        for top in range(0, fh, self.strip_h):
            h = min(self.strip_h, fh - top)
            struct.pack_into(">HH", rw, 0, self._rowstart + top, self._rowstart + top + h - 1)
            for left in range(0, fw, vw):
                w = min(vw, fw - left)
                struct.pack_into(">HH", cw, 0, self._colstart + left, self._colstart + left + w - 1)
                self.bus.send(self._col_cmd, cw)
                self.bus.send(self._row_cmd, rw)
                n = w * h * 2
                self.bus.send(self._ram_cmd, buf if n == len(buf) else mv[:n])

    def run(self, root, source, fps=30):
        """Drive from a developer-supplied `source` (an object with pump(app), e.g. KeypadSource /
        TouchSource). Acquires the panel on entry and releases it on exit (even on exception), so when
        the loop ends - app.exit(), or back on the root screen - the host app's UI is restored. Returns to
        the caller; call again to re-enter later.

        `fps` caps the loop RATE (input poll + idle sleep), not the draw rate: the UI only repaints when
        something changes, and a repaint takes as long as it takes. Deadline-paced, so a repaint slower
        than 1/fps adds NO extra sleep (the loop just runs as fast as the panel allows)."""
        import time
        period = 1.0 / fps
        self.source = source
        try:
            self.acquire()                           # inside try: a mid-acquire failure still hands back
            self.session.start(root)
            self._flush()                            # initial paint
            while self.session.running:
                t0 = time.monotonic()
                self.run_pump(source)                # drain input, span-aware repaint once if dirty
                dt = time.monotonic() - t0
                if dt < period:                      # sleep only the remainder (0 after a slow repaint)
                    time.sleep(period - dt)
        finally:
            self.release()
