# picogui_form: binds widget changes to a mapping (opt-in application layer). Slider/Text builders
# lazily import their addons, so a numeric form never loads the widgets/text modules.
from picogui import Label, Toggle, IntField, Choice, Button, Link


# ---------------------------------------------------------------- forms / binding
def Section(title, widgets):
    """Sugar: a dim section header + its widgets as a flat list to splice into a Screen:
        Screen("Settings", Section("SYSTEM", [...]) + Section("POWER", [...]))"""
    return [Label(title, dim=True)] + list(widgets)


class Form:
    """Bind widget changes to a mapping. A user change writes `data[key]` and marks the form `dirty`.
    Discrete changes (toggle/choice/int/slider) autosave via `on_commit(data)` when autosave=True; text
    stays dirty until the next discrete change or an explicit commit(). commit() errors propagate, or go
    to on_error(exc) if given. See the README for the save-backend policy and examples."""
    def __init__(self, data, on_commit=None, on_error=None, autosave=True):
        self.data = data
        self.on_commit = on_commit
        self.on_error = on_error
        self.autosave = autosave
        self.widgets = []
        self.dirty = False

    def commit(self):
        """Persist `data` now via on_commit. No-op if unchanged. On error, dirty stays True (the change
        is not lost); the error propagates, or goes to on_error(exc) if one was given."""
        if not self.dirty or self.on_commit is None:
            self.dirty = False
            return
        try:
            self.on_commit(self.data)
            self.dirty = False
        except Exception as e:
            if self.on_error is not None:
                self.on_error(e)                         # keep dirty=True so a later commit can retry
            else:
                raise

    def _set(self, key, v, persist):
        self.data[key] = v
        self.dirty = True
        if persist and self.autosave:
            self.commit()

    def _add(self, w):
        self.widgets.append(w)
        return w

    def _cb(self, key, persist=True):
        return lambda v: self._set(key, v, persist)

    def section(self, title):
        return self._add(Label(title, dim=True))

    def label(self, text, dim=False):
        return self._add(Label(text, dim))

    def toggle(self, key, label, default=False):
        return self._add(Toggle(label, bool(self.data.get(key, default)), self._cb(key)))

    def intval(self, key, label, lo=0, hi=100, step=1, default=None):
        return self._add(IntField(label, int(self.data.get(key, lo if default is None else default)),
                                  lo, hi, step, self._cb(key)))

    def slider(self, key, label, lo=0, hi=100, step=1, default=None):
        from picogui_widgets import Slider          # lazy: only a form that uses a slider loads it
        return self._add(Slider(label, int(self.data.get(key, lo if default is None else default)),
                                lo, hi, step, self._cb(key)))

    def choice(self, key, label, options, default=None):
        options = list(options)                      # materialise (accept a generator; enable index())
        if not options:
            raise ValueError("Form.choice needs at least one option")
        cur = self.data.get(key, options[0] if default is None else default)
        return self._add(Choice(label, options, options.index(cur) if cur in options else 0, self._cb(key)))

    def text(self, key, label, maxlen=16, default=""):
        from picogui_text import Text               # lazy: only a form with a text field loads it
        # persist=False: typed chars mark dirty but never autosave per keystroke (see class docstring).
        return self._add(Text(label, str(self.data.get(key, default)), maxlen, self._cb(key, persist=False)))

    def button(self, label, on_press):
        return self._add(Button(label, on_press))

    def link(self, label, make_screen):
        return self._add(Link(label, make_screen))
