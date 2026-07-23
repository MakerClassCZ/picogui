# picogui_fields: TimeField / DateField (with their PartEditor) and RadioGroup (opt-in).
from picogui import _Field, View, _font_cw


def _days_in(y, mo):
    if mo == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    return 30 if mo in (4, 6, 9, 11) else 31


class TimeField(_Field):
    """HH:MM; A opens a PartEditor (L/R picks a sub-field, U/D adjusts). Values clamp to 0-23 / 0-59."""
    def __init__(self, label, hour=0, minute=0, on_change=None):
        super().__init__(label, on_change)
        self.set_value((hour, minute))

    def hint(self):
        return "A: edit"

    def value_text(self):
        return "%02d:%02d" % (self.hour, self.minute)

    def get_value(self):
        return (self.hour, self.minute)

    def set_value(self, v):
        self.hour = min(23, max(0, int(v[0])))
        self.minute = min(59, max(0, int(v[1])))

    # --- PartEditor protocol: parts()/part_range()/part_span()/format_parts()/set_parts()
    def parts(self):
        return [self.hour, self.minute]

    def part_range(self, i, parts):
        return (0, 23) if i == 0 else (0, 59)

    def part_span(self, i):                         # (first char, n chars) in format_parts()
        return (0, 2) if i == 0 else (3, 2)

    def format_parts(self, parts):
        return "%02d:%02d" % (parts[0], parts[1])

    def set_parts(self, parts):
        self.hour, self.minute = parts[0], parts[1]
        self._emit((self.hour, self.minute))

    def key(self, app, k):
        if k == "A":
            app.push(PartEditor(self))
            return True
        return False


class DateField(_Field):
    """Y-M-D; A opens a PartEditor. Year 1970-2099, month 1-12, day clamped to the month's length."""
    def __init__(self, label, year=2026, month=1, day=1, on_change=None):
        super().__init__(label, on_change)
        self.set_value((year, month, day))

    def hint(self):
        return "A: edit"

    def value_text(self):
        return "%04d-%02d-%02d" % (self.year, self.month, self.day)

    def get_value(self):
        return (self.year, self.month, self.day)

    def set_value(self, v):
        self.year = min(2099, max(1970, int(v[0])))
        self.month = min(12, max(1, int(v[1])))
        self.day = min(_days_in(self.year, self.month), max(1, int(v[2])))

    def parts(self):
        return [self.year, self.month, self.day]

    def part_range(self, i, parts):
        if i == 0:
            return (1970, 2099)
        if i == 1:
            return (1, 12)
        return (1, _days_in(parts[0], parts[1]))

    def part_span(self, i):
        return ((0, 4), (5, 2), (8, 2))[i]

    def format_parts(self, parts):
        return "%04d-%02d-%02d" % (parts[0], parts[1], parts[2])

    def set_parts(self, parts):
        self.year, self.month, self.day = parts[0], parts[1], parts[2]
        self._emit((self.year, self.month, self.day))

    def key(self, app, k):
        if k == "A":
            app.push(PartEditor(self))
            return True
        return False


class RadioGroup:
    """One-of-N as a set of rows: splice `grp.rows()` into a Screen's widget list.
    Not a Widget itself (a widget owns one row); each option is its own focusable row."""
    def __init__(self, options, index=0, on_change=None):
        options = list(options)
        if not options:
            raise ValueError("RadioGroup needs at least one option")
        self.options = options
        self.index = min(max(index, 0), len(options) - 1)
        self.on_change = on_change

    # Silent bindable value interface (matches every value widget): the value IS the selected option.
    def get_value(self):
        return self.options[self.index]

    def set_value(self, option):                     # select by option value; silent (no on_change)
        if option in self.options:
            self.index = self.options.index(option)

    value = get_value                                # back-compat alias

    def rows(self):
        return [_RadioRow(self, i) for i in range(len(self.options))]


class _RadioRow(_Field):
    def __init__(self, group, i):
        super().__init__(group.options[i])
        self.group = group
        self.i = i

    def hint(self):
        return "A: select"

    def draw(self, p, x, y, w, focused):
        th = p.th
        if focused:
            p.fill(x, y, w, th.row_h, th.sel_bg)
        fg = th.sel_fg if focused else th.fg
        mark = "(*) " if self.group.index == self.i else "( ) "
        p.text(x + th.pad, y + th.text_dy, mark, fg)             # mark + label as two draws (no concat)
        p.text(x + th.pad + 4 * p.cw, y + th.text_dy, self.label, fg)

    def key(self, app, k):
        if k == "A":
            if self.group.index == self.i:           # already selected: no change, no emit
                return False
            self.group.index = self.i
            if self.group.on_change:
                self.group.on_change(self.group.options[self.i])
            return True
        return False



class PartEditor(View):
    """Pushed sub-field editor for TimeField/DateField (any field with the parts()
    protocol): L/R picks a part, U/D adjusts it (wraps), A commits, B cancels."""
    def __init__(self, field):
        self.field = field
        self.title = "Edit: " + field.label
        self.parts = field.parts()
        self.part = 0
        self.sel = -1

    def _adjust(self, d):
        f = self.field
        lo, hi = f.part_range(self.part, self.parts)
        v = self.parts[self.part] + d
        if v > hi:
            v = lo
        elif v < lo:
            v = hi
        self.parts[self.part] = v
        for i in range(len(self.parts)):            # re-clamp dependents (day vs month)
            lo, hi = f.part_range(i, self.parts)
            if self.parts[i] > hi:
                self.parts[i] = hi
            elif self.parts[i] < lo:
                self.parts[i] = lo

    def key(self, app, k):
        if k == "U":
            self._adjust(1)
        elif k == "D":
            self._adjust(-1)
        elif k == "L":
            self.part = (self.part - 1) % len(self.parts)
        elif k == "R":
            self.part = (self.part + 1) % len(self.parts)
        elif k == "A":
            self.field.set_parts(self.parts)
            app.pop()
        elif k == "B":
            app.pop()
        else:
            return False
        return True

    def draw(self, p, W, H):
        th = p.th
        p.fill(0, 0, W, H, th.bg)
        self._titlebar(p, W, self.title)
        cw = p.cw
        s = self.field.format_parts(self.parts)
        x0 = W // 2 - len(s) * cw // 2
        y = H // 2 - 5
        p.frame(x0 - 12, y - 12, len(s) * cw + 24, 34, th.border)
        a, n = self.field.part_span(self.part)
        px = x0 + a * cw                             # active part: highlight + arrows
        p.fill(px - 2, y - 3, n * cw + 4, 14, th.sel_bg)
        p.text(x0, y, s, th.fg)
        p.text(px, y, s[a:a + n], th.sel_fg)
        cx = px + n * cw // 2
        p.ctext(cx, y - 22, "^", th.dim)
        p.ctext(cx, y + 25, "v", th.dim)
        self._softbar(p, W, H, "<>: part  ^v: adjust", "A: OK  B: cancel")

    def hit(self, app, x, y, W, H):
        th = app.th
        bot = self._bot_h(th)                         # 0 when soft_bar is off -> those pixels aren't buttons
        if bot and y >= H - bot:                       # softbar: left half = OK (commit), right = cancel
            return self.key(app, "A" if x < W // 2 else "B")
        cw = _font_cw(th.font)
        s = self.field.format_parts(self.parts)
        x0 = W // 2 - len(s) * cw // 2
        yv = H // 2 - 5
        changed = False
        for i in range(len(self.parts)):              # tap a part in the value string to select it
            a, n = self.field.part_span(i)
            px = x0 + a * cw
            if px <= x < px + n * cw:
                changed = self.part != i
                self.part = i
                break
        before = list(self.parts)
        if y < yv:                                    # tap above the value = +1, below = -1
            self._adjust(1)
        elif y > yv + 12:
            self._adjust(-1)
        return changed or self.parts != before
