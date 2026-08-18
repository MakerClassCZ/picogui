# picogui picogame backend: `App` bootstraps picogame (Scene + one full-screen StripDraw + input +
# clock) and delegates the stack/dispatch/theme/dirty to picogui.Session. The StripDraw paints the top
# screen through Session.draw_top; each tick polls input, dispatches, and repaints at most once per tick.
import picogame as pg
import picogui as ui


class _BuiltinButtons:
    """Wraps the built-in picogame_input.Buttons as a pump(app) source, so the built-in and the
    developer-supplied input paths BOTH go through run_pump -> the public facade verbs (no backend
    reaching into Session internals, and per-tick coalescing for free)."""
    def pump(self, app):
        app.btn.poll()
        k = app._key()
        if k == "U":
            app.up()
        elif k == "D":
            app.down()
        elif k == "L":
            app.left()
        elif k == "R":
            app.right()
        elif k == "A":
            app.ok()
        elif k == "B":
            app.back()


class App(ui._AppFacade):
    """picogui on picogame. Owns the Scene + StripDraw + Buttons; the stack/dispatch/theme live in
    self.session and the whole input API (up/down/.../push/pop/W/H/th) comes from ui._AppFacade."""
    def __init__(self, theme=None, background=None, btn=None, matrix=None, exit_on_root_back=True):
        """Input comes from picogame_input.Buttons (reads UP/DOWN/LEFT/RIGHT/A/B). With no args it
        auto-picks a settings.toml matrix or the board profile; override with btn=<Buttons-like> or a
        scanned matrix={...} (forwarded to picogame_input.Buttons(matrix=...); see its docs)."""
        import board
        import picogame_game
        import picogame_input
        theme = theme or ui.Theme()
        self.scene, self.bufA, self.bufB = picogame_game.setup(
            background=theme.bg if background is None else background)
        if btn is not None:
            self.btn = btn
        elif matrix is not None:
            self.btn = picogame_input.Buttons(matrix=matrix)
        else:
            self.btn = picogame_input.Buttons()
        _w, _h = picogame_game.screen()
        self.session = ui.Session(theme, _w, _h,
                                  exit_on_root_back=exit_on_root_back)
        self.strip = pg.StripDraw(self._draw, 0, 0, self.session.W, self.session.H, always_dirty=False)
        self.scene.add(self.strip)
        self.source = None                          # optional input source (run(source=...)); else Buttons
        self._btns = _BuiltinButtons()              # the built-in Buttons wrapped as a pump() source

    def _draw(self, view, vx, vy, vw, vh):
        self.session.draw_top(view, vx, vy, vh)     # vh -> off-band culling in the Views

    # -- lifecycle: no-op takeover for surface parity with rgb/mono/fb. picogame owns its own Scene
    # (from picogame_game.setup), so there is no host display to take over / hand back.
    def acquire(self):
        pass

    def release(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    # -- controller facade (delegate to Session, then reflect+clear its dirty flag onto the strip) ---
    def _flush(self):
        d = self.session.peek_dirty()
        if not d:
            return
        if d == "full":
            self.strip.invalidate()
        else:
            # The StripDraw dirty accumulator UNIONS sub-rects (firmware picogame_dirty_union), so
            # invalidating each span builds a bounding box that is never worse than full and much smaller
            # for the common case: a focus move now marks two ADJACENT rows -> Session.mark merges them
            # into one span -> a 2-row box, not the whole screen. Far-apart spans just degrade to ~full.
            W = self.session.W
            for y0, y1 in d:
                self.strip.invalidate(0, y0, W, y1 - y0)
        # Failure model differs from rgb/dispbase: here the dirty is TRANSFERRED to the StripDraw's own
        # accumulator (engine-owned) and the Session is acked now; the actual push is scene.refresh() in
        # tick(). So on a refresh failure the invalidation is retained by the ENGINE (the strip stays
        # dirty and repaints next refresh), not by the Session - the guarantee lives one layer down.
        self.session.ack_dirty()

    def render(self):
        """Force a full repaint + push (parity with rgb/dispbase render()). Marks the strip and refreshes
        the Scene now."""
        self.session.invalidate()
        self._flush()
        self.scene.refresh()

    def _key(self):
        b = self.btn
        if b.repeat(b.UP):
            return "U"
        if b.repeat(b.DOWN):
            return "D"
        if b.repeat(b.LEFT):                        # repeat: hold to keep adjusting sliders/ints/grids
            return "L"
        if b.repeat(b.RIGHT):
            return "R"
        if b.just_pressed(b.A):                     # actions stay single-press (no auto-fire)
            return "A"
        if b.just_pressed(b.B):
            return "B"
        return None

    def tick(self):
        # both the developer source and the built-in buttons go through run_pump -> public verbs ->
        # coalesced into at most one _flush this tick
        self.run_pump(self.source if self.source is not None else self._btns)
        self.scene.refresh()                        # composite + push at most once per tick

    def run(self, root, source=None, fps=30):
        """Run the UI loop (arg order matches the displayio/oled backends). Returns when app.exit() or
        back on the root screen ends it. With `source` (any object with pump(app) - your encoder/button
        reader; see examples/encoder_demo.py) input comes from it instead of the built-in
        picogame_input.Buttons. `fps` caps the loop rate (input poll), not the draw rate - the UI repaints
        only on change; picogame_clock.Clock deadline-paces it (a slow frame adds no extra sleep). The App
        owns its own Scene (from picogame_game.setup), so nothing else composites into it; the last frame
        stays on screen after run() returns until run() is called again."""
        import picogame_clock
        self.source = source
        self.session.start(root)
        self._flush()                               # initial paint (marks the strip; tick refreshes)
        clock = picogame_clock.Clock(fps)
        while self.session.running:
            self.tick()
            clock.tick()
