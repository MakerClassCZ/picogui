# picogui_themes: extra Theme presets (opt-in). The core ships one default Theme.
from picogui import Theme, rgb565


class LcdTheme(Theme):
    """Monochrome 'paper' LCD look (green-gray Casio organizer): dark ink on a light
    panel, inverted-video selection. All channels 565-aligned (R/B mult 8, G mult 4)."""
    def __init__(self):
        super().__init__()
        self.bg = rgb565(168, 180, 144)
        self.fg = rgb565(24, 28, 16)
        self.dim = rgb565(96, 104, 80)
        self.sel_bg = rgb565(40, 48, 32)
        self.sel_fg = rgb565(168, 180, 144)
        self.active_bg = rgb565(96, 104, 80)     # edit mode: a mid tone, distinct from the dark focus fill
        self.active_fg = rgb565(168, 180, 144)   # (3 tones here -> a solid active colour is enough)
        self.bar_bg = rgb565(144, 156, 120)
        self.bar_fg = rgb565(24, 28, 16)
        self.border = rgb565(72, 80, 56)
        self.accent = rgb565(24, 28, 16)


class MonoTheme(Theme):
    """1bpp OLED look (SSD1306/SH1107, ~128x64): pure on/off, inverted-video selection, a screened
    (hatched) active row, and compact metrics for the tiny panel. Pairs with picogui_mono.MonoSurface
    (a pixel is ON iff colour != 0). Turn bars off (title_bar/soft_bar) to reclaim rows - on 64px every
    row counts. Uses the built-in 6x12 terminalio font (no extra font needed)."""
    def __init__(self, title_bar=True, soft_bar=False):
        super().__init__()
        ON = rgb565(255, 255, 255)
        OFF = rgb565(0, 0, 0)
        self.bg = OFF                            # OFF (0): MonoSurface leaves these pixels dark
        self.fg = ON
        self.dim = ON                            # no grey on 1bpp; dim headers read as normal text
        self.sel_bg = ON                         # focused row = a lit block...
        self.sel_fg = OFF                        # ...with the text cut out of it (inverted video)
        self.active_bg = ON                      # active row = a lit block, then screened to a 50% checker
        self.active_fg = OFF                      # (clearly != the solid focus); a 1px glyph halo keeps
        self.active_screen = True                 # the text legible over it
        self.active_hatch = OFF                  # the checker screens toward OFF
        self.bar_bg = OFF                        # bars: dark, white text + a white separator line
        self.bar_fg = ON
        self.border = ON
        self.accent = ON
        self.row_h = 14                          # terminalio FONT is 6x12 -> 14px rows (1px top/bottom)
        self.bar_h = 14
        self.pad = 3
        self.text_dy = 1
        self.title_bar = title_bar
        self.soft_bar = soft_bar
