# picogui_mono: 1bpp backend for small MONO displays (OLED - SSD1306/SH1107/SH1106 - or a mono LCD).
# picogui embeds NO panel driver: exactly like the SPI backend (picogui_rgb), the APP builds the
# display with its own displayio driver and hands it in. You build a mono displayio display and pass it:
#       App(display=my_display)
# picogui renders into a 2-colour displayio.Bitmap and lets displayio push the panel (all the
# controller-specific work + partial refresh). App takes the display over on entry and hands it back
# on exit, so it coexists with a host displayio UI. ANY mono controller with a displayio driver works.
# A pixel is ON iff the colour != 0, so it pairs with picogui_themes.MonoTheme; text uses the shared
# software glyph rasteriser (picogui_glyph), NOT the RGB backend - a mono build never loads picogui_rgb.
#
# Why a Bitmap here but strips in picogui_rgb: a 1bpp Bitmap is tiny (~1 KB), so rendering the whole
# frame into it and letting displayio push is cheap; a full RGB565 Bitmap would be far too big, which is
# why the RGB backend streams small strips over the bus itself instead.
from picogui_dispbase import _DisplayioApp, _BitmapSurface   # shared lifecycle + surface (also picogui_fb)


class MonoSurface(_BitmapSurface):
    """1bpp surface: a pixel is ON (bitmap value 1) iff the colour != 0. All the drawing (fill via
    bitmaptools, text, lines, clip) lives in _BitmapSurface; only the value mapping differs."""
    def _val(self, color):
        return 1 if color else 0


class App(_DisplayioApp):
    """picogui on a mono OLED. Build the panel with its displayio driver (adafruit_displayio_ssd1306 /
    _sh1107 / ...) and pass it as `display`; picogui renders into a 1bpp Bitmap and displayio pushes it.
    The whole displayio-push lifecycle (takeover/handback, flush, run loop) is shared in
    picogui_dispbase; this class only builds the 1bpp Bitmap + 2-colour palette + MonoSurface."""
    def __init__(self, display, theme=None, exit_on_root_back=True):
        if theme is None:
            from picogui_themes import MonoTheme
            theme = MonoTheme()
        super().__init__(display, theme, exit_on_root_back)

    def _build(self, display):
        import displayio
        bmp = displayio.Bitmap(display.width, display.height, 2)
        pal = displayio.Palette(2)
        pal[0] = 0x000000                            # 0 = off (black); 1 = on (white)
        pal[1] = 0xFFFFFF
        group = displayio.Group()
        group.append(displayio.TileGrid(bmp, pixel_shader=pal))
        return MonoSurface(bmp), group
