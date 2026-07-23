# picogui_dialog: a centred modal yes/no (or OK) box (opt-in).
from picogui import View


class Dialog(View):
    """A centred modal box. A = yes/ok, B = no/cancel.

    Contract: a Dialog is OPAQUE - it paints the whole screen background, then the box. It reads the
    same on every backend (the box on a clean field), rather than depending on what happened to be in
    the framebuffer (which differed: the RGB strip renderer clears each band, the mono Bitmap does not).
    Push it as a full-screen modal; it is not a translucent overlay over the screen beneath."""
    def __init__(self, title, message, on_yes=None, yesno=True):
        self.title = title
        self.message = message
        self.on_yes = on_yes
        self.yesno = yesno
        self.sel = -1

    def key(self, app, k):
        if k == "A":
            app.pop()
            if self.on_yes:
                self.on_yes(app)
            return True
        if k == "B":
            app.pop()
            return True
        return False

    def _box(self, W, H):
        bw = min(W - 8, max(80, W - 40))             # fit narrow panels too (never wider than the screen)
        bh = min(H - 8, 70)                          # clamp so it fits a short panel (e.g. 128x64)
        return (W - bw) // 2, (H - bh) // 2, bw, bh

    def draw(self, p, W, H):
        th = p.th
        p.fill(0, 0, W, H, th.bg)                     # opaque: clean field on every backend (see class doc)
        bx, by, bw, bh = self._box(W, H)
        p.fill(bx, by, bw, bh, th.bar_bg)
        p.frame(bx, by, bw, bh, th.accent)
        p.fill(bx, by, bw, th.bar_h, th.sel_bg)
        p.text(bx + th.pad, by + th.text_dy, self.title, th.sel_fg)
        p.ctext(W // 2, by + th.bar_h + 8, self.message, th.fg)
        if self.yesno:
            p.text(bx + th.pad, by + bh - 12, "A: yes", th.accent)
            p.rtext(bx + bw - th.pad, by + bh - 12, "B: no", th.dim)
        else:
            p.ctext(W // 2, by + bh - 12, "A: OK", th.accent)

    def hit(self, app, x, y, W, H):
        bx, by, bw, bh = self._box(W, H)
        if not (bx <= x < bx + bw and by <= y < by + bh):   # tap outside the modal box: ignore
            return False
        if y >= by + bh - 18:                        # only the button row acts (and pops -> a change)
            if self.yesno:
                return self.key(app, "A" if x < W // 2 else "B")   # left = yes, right = no
            return self.key(app, "A")                # OK
        return False                                 # inert tap inside the box: no change
