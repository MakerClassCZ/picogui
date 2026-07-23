# picogui_text: an editable string field (opt-in). Text opens the on-screen Keyboard (loaded lazily
# from picogui_keyboard) or takes direct char() input from a real keyboard.
from picogui import _Field


class Text(_Field):
    """A string field; A opens the on-screen keyboard.

    The keyboard is pluggable: by default A opens the grid `picogui_keyboard.Keyboard` (good on wide
    displays). For a small OLED, a round display, or rotary-only input, set `Text.keyboard` (class-wide)
    or `a_field.keyboard` (one field) to `picogui_keyboard_row.RowKeyboard` (one-row, L/R + pick)."""
    keyboard = None                                  # None -> lazy default grid Keyboard; else a KB class

    def __init__(self, label, value="", maxlen=16, on_change=None):
        super().__init__(label, on_change)
        self.value = value
        self.maxlen = maxlen

    def hint(self):
        return "A: edit"

    def value_text(self):
        v = self.value or "-"
        return v if len(v) <= 12 else v[:11] + "~"

    def key(self, app, k):
        if k == "A":
            cls = self.keyboard
            if cls is None:
                from picogui_keyboard import Keyboard   # lazy: loaded only when a field is opened
                cls = Keyboard
            app.push(cls(self))
            return True
        return False

    def char(self, app, ch):
        """Type into the field directly from a real keyboard: a printable char appends (up to maxlen),
        '\\b' backspaces. Returns True only when the value actually changed."""
        if ch == "\b":
            if not self.value:                       # backspace on empty: no change
                return False
            self.value = self.value[:-1]
            self._emit(self.value)
            return True
        if len(ch) == 1 and ch >= " " and ch != "\x7f":       # printable
            if len(self.value) >= self.maxlen:       # at maxlen: no change
                return False
            self.value += ch
            self._emit(self.value)
            return True
        return False
