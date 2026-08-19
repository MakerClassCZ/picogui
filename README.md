# picogui

A configuration-UI toolkit for CircuitPython: a stack of screens made of rows, on displays from a
128x64 OLED to a 640x480 framebuffer, touch and round included.

<img width="642" height="482" alt="image" src="https://github.com/user-attachments/assets/5d38a0fe-fbee-4343-be98-3b84197690a3" />

The UI is something a program **calls**: `run()` owns the screen and the input while the UI is up, and
returns when the user leaves it.

```python
import picogui as ui
from picogui_picogame import App

App().run(ui.Screen("Settings", [
    ui.Label("SYSTEM", dim=True),
    ui.Choice("Mode", ["Off", "Auto", "Manual"]),
    ui.IntField("Interval s", 10, 1, 60),
    ui.Toggle("Beep", True),
    ui.Link("Display", lambda app: ui.Screen("Display", [   # a sub-screen is just another Screen
        ui.Choice("Theme", ["Dark", "Light", "Amber"]),
        ui.IntField("Backlight", 70, 0, 100, step=5),
        ui.Toggle("Night mode", False),
    ])),
    ui.Button("Exit", lambda app: app.exit()),
]))
```

The UI is data: a screen is a list of rows, a sub-screen is another list, and a callback appears only
where something has to happen. The rows hold the values - read them back, or bind them to a dict with
[`Form`](#forms).

Run them in the browser:
[settings](https://picogame.makerclass.cz/playground/?game=ui_settings) ·
[form binding](https://picogame.makerclass.cz/playground/?game=ui_form) ·
[tabs](https://picogame.makerclass.cz/playground/?game=ui_tabs) ·
[organizer](https://picogame.makerclass.cz/playground/?game=ui_organizer) (icon grid, records, time/date fields, live theme switch)

## Deploy
Copy the modules you need into **`CIRCUITPY/lib/`** - either the `.py` sources or the precompiled
`.mpy` from [`mpy/`](mpy/) (smaller, faster imports; keep only ONE file per module in `/lib`). Or with
[`circup`](https://github.com/adafruit/circup):

```sh
circup bundle-add MakerClassCZ/picogui      # register this bundle (one time)
circup install picogui picogui_form         # core + the modules you use
```

## Control
The UI reacts to these commands and nothing else - send them from wherever your input comes from.

| Command | What it does |
|---|---|
| `app.up()` / `app.down()` | move the focus between rows |
| `app.left()` / `app.right()` | change the focused row's value (choice, number, slider, tab) |
| `app.ok()` | activate: fire a button, open a link/editor, toggle |
| `app.back()` | pop the screen; on the root screen it exits the loop (`exit_on_root_back=True`) |
| `app.rotate(d)` | encoder turn: `d>0` = clockwise. Moves the focus, or changes the value while a row is active |
| `app.press()` | encoder switch: makes a value row *active* (so `rotate` edits it) and back, or fires a non-value row |
| `app.char(ch)` | type a character into the focused text field |
| `app.touch(x, y)` | a touch in panel pixels: focuses the row it hits, or hits the control under it |
| `app.push(screen)` / `app.pop()` | drill into a screen / go back |
| `app.invalidate()` | repaint everything (after you changed the data behind a widget) |
| `app.set_theme(theme)` / `app.exit()` | swap the live theme / leave `run()` |

Repaints are coalesced: a burst of commands paints once, and only the rows that changed.

So a **D-pad** device sends up/down/left/right/ok/back, and a **one-knob** device needs just
`rotate` and `press`.

## Backends
One per program: it owns the panel and the loop. All four take the same commands and
`run(root, source, fps=30)`.

The displayio backends borrow the panel and give it back: `acquire()` saves the host's `root_group` +
`auto_refresh` (on an own-bus panel it grabs the bus), `release()` puts them back, and `run()` or
`with App(...) as app:` does both.

| Module | Panel | RAM | Notes |
|---|---|---|---|
| `picogui_rgb` | SPI colour panel (ST7789, GC9A01, …) on stock CircuitPython | one `W × strip_h` RGB565 strip (~10 KB at 320×16) | Owns the bus and streams strips (CASET/RASET/RAMWR). Panel geometry is configurable (`col_cmd`/`row_cmd`/`ram_cmd`, `colstart`/`rowstart`, `viewport`); `sink=` replaces the push for a desktop harness. |
| `picogui_mono` | 1bpp OLED/LCD (SSD1306, SH1107, …) | one 1bpp `displayio.Bitmap` | You build the panel with its displayio driver and hand it over. Pair with `picogui_themes.MonoTheme()`. |
| `picogui_fb` | any colour displayio display, incl. picodvi/HSTX | full frame, `W*H*2` bytes | For PSRAM-class boards (Fruit Jam, Picomputer). Bitmap value IS the RGB565 int. |
| `picogui_picogame` | boards running the [picogame](https://github.com/MakerClassCZ/circuitpython/tree/picogame) engine | zero retained (one full-screen `StripDraw`) | Builds its own `Scene`, input (`picogame_input.Buttons`) and clock, so `run()` needs no source; any change repaints the whole screen. Restores nothing on exit: a game keeps its scene and sprites, but repaints itself with `scene.invalidate()` + `scene.refresh()` after `run()` returns. Holds a second pair of strip buffers while the App exists. |

## Input sources
`run()` polls one **source** each tick - any object with a `pump(app)` method that sends the commands
above. `picogui_picogame` has a built-in one (`picogame_input.Buttons`); the other backends ship no
input, so you pass yours:

| Source | Provides |
|---|---|
| `picogui_rgb.KeypadSource(keys, nav, chars)` | a `keypad.Keys`/`KeyMatrix` you built: `nav = {key_number: 'up'/'down'/'left'/'right'/'ok'/'back'}`, optional `chars = {key_number: 'a'}` |
| `picogui_rgb.TouchSource(read)` | `read()` returns `(x, y)` in panel pixels, or `None` |

Your own is the same shape - a rotary encoder:

```python
class EncoderSource:
    def __init__(self, enc, sw):
        self.enc, self.sw, self.last, self.was = enc, sw, enc.position, sw.value

    def pump(self, app):
        pos = self.enc.position
        if pos != self.last:
            app.rotate(pos - self.last)      # +1 / -1 per detent
            self.last = pos
        now = self.sw.value
        if self.was and not now:             # active-low switch
            app.press()
        self.was = now
```

An analog knob (potentiometer, LDR) is the same with a deadband: quantise the ADC into detents first,
or the focus chases the noise.

## Widgets
Rows for `Screen(title, widgets)`. Each value widget has `get_value()` / `set_value(v)` and an
`on_change(value)` callback that fires on every user edit - implement those and your own class is a
widget.

| Module | Provides |
|---|---|
| `picogui` (core) | `Label(text, dim=False)` · `Toggle(label, value, on_change)` · `Choice(label, options, index, on_change)` · `IntField(label, value, lo, hi, step, on_change)` · `Button(label, on_press)` (`on_press(app)`) · `Link(label, make_screen)` - drills into `make_screen(app)`, B pops. |
| `picogui_widgets` | `Slider` (IntField with a bar) · `ProgressBar` (display-only) · `Swatch(label, get)` (colour chip) · `Custom(draw, key=…, touch=…, char=…, focusable=…)` - a row from callbacks instead of a subclass. |
| `picogui_text` | `Text(label, value, maxlen, on_change)` - opens the on-screen keyboard, or takes `app.char(ch)` from a real one. |
| `picogui_fields` | `TimeField(label, hour, minute)` · `DateField(label, year, month, day)` - A opens a `PartEditor` (L/R picks the sub-field, U/D adjusts) · `RadioGroup(options, index, on_change)` - splice `grp.rows()` into a screen. |

## Views
Full-screen views you `push()`; `Screen` is the ordinary row list. A custom one subclasses `View` and
implements `draw(p, W, H)` and `key(app, k)` (`k` = `'U' 'D' 'L' 'R' 'A' 'B'`), returning `True` when
the frame changed.

| Module | Provides |
|---|---|
| `picogui` (core) | `Screen(title, widgets)` · `View` (base). |
| `picogui_records` | `RecordList(title, items, on_select, empty, hint)` - scrollable list of strings or `(text, right)` pairs; **the item list may be mutated between frames**, the selection re-clamps, empty state included. `NoteView(title, text)` - word-wrapped text, cached wrap, U/D scrolls. |
| `picogui_grid` | `MenuGrid(title, items, cell_w, cell_h)` - icon-grid home menu; takes an `Icon` (`picogui_icons.ICONS['gear']`, or your own mask) or a badge char. |
| `picogui_tabs` | `Tabs(title, tabs)` - tab bar over N pages; the bar is the top focus row. |
| `picogui_dialog` | `Dialog(title, message, on_yes, yesno=True)` - centred modal, A = yes, B = no. |
| `picogui_carousel` | `Carousel(title, widgets)` - round-display list: the focused row is centred, neighbours taper to the circle. |
| `picogui_keyboard`, `picogui_keyboard_row` | `Keyboard(field)` - D-pad grid. `RowKeyboard(field, chars=None)` - one row, for small/round displays and rotary input. |

## Forms
`picogui_form.Form` writes widget edits into a mapping and persists it. Builders: `label section
toggle intval slider choice text button link`.

```python
from picogui_form import Form, Section

cfg = {"mode": "Auto", "interval": 10, "beep": True}
f = Form(cfg, on_commit=save_to_disk)          # autosave: each discrete edit commits

screen = ui.Screen("Settings",
    Section("SYSTEM", [f.choice("mode", "Mode", ["Off", "Auto", "Manual"]),
                       f.intval("interval", "Interval s", 1, 60)]) +
    Section("SOUND",  [f.toggle("beep", "Beep")]) +
    [f.button("Save now", lambda app: f.commit())])
```

Toggle/choice/int/slider commit immediately; a text edit stays `dirty` until the next discrete change
or an explicit `commit()`. With `on_error(exc)` a failed write keeps `dirty` set, so the edit isn't
lost and a later commit retries.

## Repeatable elements
"N of something + Add" is a `RecordList` whose `items` you own, plus a screen pushed per element. The
stack is the tree - nesting deeper is another `Link` or `RecordList` inside the pushed screen.

```python
PROFILES = [{"mode": "Auto", "interval": 10}]

def rows():
    return ["Profile %d" % (i + 1) for i in range(len(PROFILES))] + ["+ Add profile"]

def open_row(app, i):
    if i == len(PROFILES):                      # the "+ Add" row
        PROFILES.append({"mode": "Auto", "interval": 10})
        lst.items = rows()
        app.invalidate()
        return
    f = Form(PROFILES[i])
    app.push(ui.Screen("Profile %d" % (i + 1), [f.choice("mode", "Mode", ["Off", "Auto", "Manual"]),
                                                f.intval("interval", "Interval s", 1, 60)]))

lst = RecordList("Profiles", rows(), on_select=open_row)
```

## Themes
`Theme` is a plain object: `font bg fg dim sel_bg sel_fg active_bg active_fg active_screen
active_hatch bar_bg bar_fg border accent row_h pad bar_h text_dy title_bar soft_bar`. Turn
`title_bar`/`soft_bar` off to reclaim rows on a small panel.

| Preset | Look |
|---|---|
| `picogui.Theme()` | dark colour default; blue focus, amber active row |
| `picogui_themes.LcdTheme()` | dark ink on light "paper" (organizer LCD) |
| `picogui_themes.MonoTheme(title_bar=True, soft_bar=False)` | 1bpp: inverted-video selection, screened active row (no third tone available) |

`ui.derive(theme, **overrides)` returns a proxy, so a screen or a single row can retint by swapping
`p.th`: `p.th = ui.derive(app.th, sel_bg=ui.rgb565(180, 40, 40))`.

## Drawing
Widgets and views draw through `Painter` (`p`) in absolute screen coordinates, clipped to the strip
being painted: `text rtext ctext btext brtext` (left/right/centre/big/big-right), `fill hline frame
checker pixel blit`, `p.visible(y, h)` to skip work outside the current band, `p.th` for the theme.

A view reports a change by returning `True` from `key()`, and narrows the repaint with
`app.mark(y0, y1)` (absolute rows). Without a mark the frame repaints fully.

## Own loop
`run()` is a blocking loop, so a program that has to keep doing something while the UI is up drives
it itself: `run()` is `start(root)` + a pump + `acquire()`/`release()` around them.
`picogui_picogame` exposes `tick()` (one pump + at most one repaint); the others expose `acquire()`,
`release()`, `render()` and `run_pump(source)`.

```python
app = picogui_picogame.App()
app.session.start(root)
while running:
    app.tick()          # one input pump + at most one repaint
    device.service()    # the rest of your program keeps running
```

Edits reach your program as they happen: a widget's `on_change(value)` fires on the key that made it,
and a `Form` writes the new value into its dict, so nothing has to be read back after the UI closes.

`Session.take_dirty()` and `draw_top(view, vx, vy, vh)` are the hooks a new backend implements.

## In an existing scene
A program that already has a picogame `Scene` does not need the backend `App` (and the second Scene
and strip buffers it builds). A `Session` plus one `StripDraw` layer paints into the scene you have:

```python
sess = ui.Session(W=W, H=H)
sess.start(ui.Screen("Settings", [...]))

def paint(view, vx, vy, vw, vh):
    sess.draw_top(view, vx, vy, vh)

layer = scene.add(pg.StripDraw(paint, 0, 0, W, H, always_dirty=False))

# in your loop: feed the commands, and repaint the layer only when the UI says it changed
sess.down() / sess.ok() / ...
if sess.dirty:
    layer.invalidate()
    sess.ack_dirty()
scene.refresh()
```

The UI is then one layer among your sprites - `layer.visible = False` puts it away, and the rest of
the scene keeps drawing while it is up.

## Modules
| Module | Contains |
|---|---|
| `picogui` | `Session` (stack, focus, dispatch, dirty), `Screen`, `View`, `Theme`, `derive`, `Painter`, `rgb565`, and the core widgets: `Label`, `Toggle`, `Choice`, `IntField`, `Button`, `Link` |
| `picogui_widgets` | `Slider`, `ProgressBar`, `Swatch`, `Custom` |
| `picogui_text` | `Text` (string field) |
| `picogui_keyboard` | `Keyboard` - D-pad grid, opened by `Text` |
| `picogui_keyboard_row` | `RowKeyboard` - one row, for small/round displays and rotary input |
| `picogui_fields` | `TimeField`, `DateField`, `PartEditor`, `RadioGroup` |
| `picogui_records` | `RecordList`, `NoteView` |
| `picogui_grid` | `MenuGrid` |
| `picogui_tabs` | `Tabs` |
| `picogui_dialog` | `Dialog` |
| `picogui_carousel` | `Carousel` |
| `picogui_form` | `Form`, `Section` |
| `picogui_icons` | the built-in pictogram catalogue (`ICONS`) |
| `picogui_iconbase` | just the `Icon` type, for a module that only accepts one |
| `picogui_themes` | `LcdTheme`, `MonoTheme` |
| `picogui_glyph` | software glyph rasteriser + bounded cache (used by the software backends) |
| `picogui_rgb` | SPI colour backend: `App`, `Surface`, `KeypadSource`, `TouchSource` |
| `picogui_mono` | 1bpp displayio backend: `App`, `MonoSurface` |
| `picogui_fb` | colour displayio/framebuffer backend: `App`, `ColorSurface` |
| `picogui_dispbase` | shared lifecycle for the two displayio backends |
| `picogui_picogame` | picogame backend: `App` |
| `picogui_full` | re-exports everything (for boards with RAM to spare) |
| `picogui_extras` | back-compat aggregator - prefer the specific modules |

## Limits
- 1bpp panels have no third tone: use `MonoTheme`; `Swatch` and the accent-coloured `Slider` bar
  degrade to on/off.
- Round panels: `Carousel` and `RowKeyboard` fit the circle; a full `Keyboard` grid and a wide tab bar
  get clipped.
- `picogui_fb` needs `W*H*2` bytes of buffer - not an RP2040 target.
- `picogui_picogame.App` builds its own `Scene` and strip buffers. To draw into a scene you already
  have (and pay for no second set), skip the App - see [In an existing scene](#in-an-existing-scene).
- Rows only: no free-form layout, no overlapping widgets, no animation system.

## License
MIT - see [LICENSE](LICENSE).
