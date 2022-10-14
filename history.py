import os

class History:
    def __init__(self):
        self._history = []
        self._idx = 0

    def append(self, cmdline):
        self._history.append(cmdline)

    def reset(self):
        self._idx = 0

    def up(self):
        self._idx = max(self._idx - 1, -len(self._history))
        if self._idx:
            return self._history[self._idx]
        return ""

    def down(self):
        self._idx = min(self._idx + 1, 0)
        if self._idx:
            return self._history[self._idx]
        return ""

    @property
    def history(self):
        return self._history

    @history.setter
    def history(self, value):
        self._history = value


class CmdHistory(History):
    def __init__(self):
        super().__init__()
        hidden_prefix = "." if os.name != "nt" else "_"
        path = os.path.expanduser(f"~/{hidden_prefix}aaa_history")
        if os.path.isfile(path) and os.access(path, os.R_OK):
            with open(path) as f:
                self._history = f.read().splitlines()
        try:
            self._file = open(path, "a")
        except IOError:
            self._file = None

    def append(self, cmdline):
        super().append(cmdline)
        print(cmdline, file=self._file)

    def __del__(self):
        if self._file:
            self._file.close()
