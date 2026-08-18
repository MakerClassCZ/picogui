# picogui_fb: full-frame COLOUR backend for a stock displayio display - a picodvi FramebufferDisplay
# (Fruit Jam / Picomputer DVI), or any colour display you hand over already set up as a displayio display.
#
# It renders into a 16bpp displayio.Bitmap whose values ARE RGB565 ints (a ColorConverter(RGB565_SWAPPED)
# shader matches picogui's byte-swapped rgb565(), so colours need no conversion) and lets display.refresh()
# push it - the SAME displayio-push lifecycle as picogui_mono, shared in picogui_dispbase, just colour
# instead of 1bpp. Bulk fills go through bitmaptools.fill_region (C); text and diagonal lines are
# per-pixel Python; a clip window keeps a partial repaint to the dirty rows.
#
# Use it where the display is a memory framebuffer (DVI) - picogui_rgb can't (no display.bus there) - or
# any colour displayio display on a board with room for a width*height*2 buffer (RP2350/PSRAM). On an
# RP2040 without PSRAM that buffer is usually too big; drive an SPI panel with picogui_rgb (bus strips)
# there instead.
from picogui_dispbase import _DisplayioApp, _BitmapSurface


class ColorSurface(_BitmapSurface):
    """16bpp colour surface: the bitmap value IS the RGB565 int (a ColorConverter(RGB565_SWAPPED) shader
    shows it, matching picogui's byte-swapped rgb565()). All drawing (fill via bitmaptools, text, lines,
    clip) lives in _BitmapSurface; the value mapping is the identity."""
    def _val(self, color):
        return color


class App(_DisplayioApp):
    """picogui on a colour displayio display (a picodvi FramebufferDisplay, or any colour display handed
    over). Pass the display (e.g. picogame_game.display() / supervisor.runtime.display, or one you built). picogui
    renders into a 16bpp Bitmap and displayio pushes it; takeover/handback coexist with a host UI. The
    displayio-push lifecycle is shared in picogui_dispbase; this class only builds the colour stack."""
    def __init__(self, display, theme=None, exit_on_root_back=True):
        if theme is None:
            import picogui as ui
            theme = ui.Theme()
        super().__init__(display, theme, exit_on_root_back)

    def _build(self, display):
        import displayio
        w, h = display.width, display.height
        try:
            bmp = displayio.Bitmap(w, h, 65536)       # 16bpp: values are RGB565 ints; W*H*2 contiguous B
        except MemoryError:
            raise MemoryError(
                "picogui_fb needs a %d-byte full-frame buffer (%dx%d x2) - too big for this board's RAM. "
                "Use picogui_rgb (streams small strips over the display bus) for an SPI colour panel; "
                "picogui_fb is for PSRAM / big-RAM boards (e.g. a picodvi FramebufferDisplay)."
                % (w * h * 2, w, h))
        cc = displayio.ColorConverter(input_colorspace=displayio.Colorspace.RGB565_SWAPPED)
        group = displayio.Group()
        group.append(displayio.TileGrid(bmp, pixel_shader=cc))
        return ColorSurface(bmp), group
