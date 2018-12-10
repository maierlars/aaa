#!/usr/bin/python

import sys
import json
import curses, curses.ascii
import textwrap
import datetime
import re

import agency


class Rect:
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def __str__(self):
        return "({},{}), ({}, {})".format(self.x, self.y, self.width, self.height)

    def zero():
        return Rect(0, 0, 0, 0)



class Layout:
    def __init__(self, rect):
        self.rect = rect

    def update(self):
        pass

    def layout(self, rect):
        self.rect = rect

class LayoutSwitch(Layout):
    def __init__(self, rect, subs):
        super().__init__(rect)
        self.subs = subs
        self.idx = 0
        self.layout(rect)

    def layout(self, rect):
        super().layout(rect)
        for s in self.subs:
            s.layout(rect)

    def input(self, c):
        self.subs[self.idx].input(c)

    def update(self):
        self.subs[self.idx].update()

    def select(self, idx):
        if not idx in range(0, len(self.subs)):
            raise ValueError("Invalid LayoutSwitch index")
        self.idx = idx
        self.update()

class LayoutColumns(Layout):
    def __init__(self, app, rect, colums, rels):
        super().__init__(rect)
        self.colums = colums
        self.bars = []
        self.app = app
        self.setRelations(rels)
        self.layout(self.rect)

    def update(self):
        for x in self.colums:
            x.update()

        for x in self.bars:
            for y in range(0, self.rect.height):
                self.app.stdscr.addch(self.rect.y + y, x, curses.ACS_VLINE)

    def layout(self, rect):
        super().layout(rect)

        total = sum(self.rels)
        offset = 0
        avail = self.rect.width - len(self.colums) + 1
        self.bars = []

        for i, col in enumerate(self.colums):
            width = (avail * self.rels[i]) // total

            col.layout(Rect(
                offset, 0,
                width, self.rect.height
            ))
            offset += width
            self.bars.append(offset)
            offset += 1

        # remove last bar
        self.bars.pop()


    def setRelations(self, rels):
        if len(rels) != len(self.colums):
            raise ValueError("Invalid length of rels")
        self.rels = rels


class Control:

    def __init__(self, app, rect):
        self.app = app
        self.rect = rect

    def layout(self, rect):
        self.rect = rect

    def update(self):
        pass

    def input(self, c):
        pass


class AgencyLogList(Control):

    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.app = app
        self.top = 0
        self.highlight = 0
        self.filter = ""
        self.regex = None
        self.filterChanged = False
        self.list = []

    def layout(self, rect):
        super().layout(rect)

    def update(self):
        # Update top
        if self.highlight < self.top:
            self.top = self.highlight

        bottom = self.top + self.rect.height - 1

        if self.highlight >= bottom:
            self.top = self.highlight - self.rect.height + 1

        if self.top < 0:
            self.top = 0

        maxTop = len(self.app.log) - self.rect.height
        if self.top > maxTop:
            self.top = maxTop

        if self.rect.width == 0:
            return

        maxlen = self.rect.width

        # Paint all lines from top upto height many
        for i in range(0, self.rect.height):
            idx = self.top + i
            if idx >= len(self.app.log):
                break
            y = self.rect.y + i
            x = self.rect.x
            ent = self.app.log[idx]

            text = " ".join(x for x in ent["request"])
            msg = "[{0!s}|{1!s}] {2!s}: {3}".format(ent["timestamp"], ent["term"], ent["_id"], text).ljust(self.rect.width)

            attr = 0
            if idx == self.highlight:
                attr |= curses.A_STANDOUT
            self.app.stdscr.addnstr(y, x, msg, maxlen, attr)
            self.app.stdscr.clrtoeol()

    def input(self, c):
        if c == curses.KEY_UP:
            self.highlight -= 1
        elif c == curses.KEY_DOWN:
            self.highlight += 1
        elif c == curses.KEY_NPAGE:
            self.highlight += self.rect.height
            self.top += self.rect.height
        elif c == curses.KEY_PPAGE:
            self.highlight -= self.rect.height
            self.top -= self.rect.height
        elif c == ord('f'):
            regex = self.app.userString(label = "Regular Search Expr", default = self.filter, prompt = "> ")
            # try to compile the regex
            self.filter = regex
            self.regex = re.compile(regex)
            raise NotImplementedError("Filters are not yet implemented")

        if self.highlight < 0:
            self.highlight = 0
        elif self.highlight >= len(self.app.log):
            self.highlight = len(self.app.log) - 1

class AgencyLogView(Control):

    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.idx = None

    def update(self):
        if self.rect.width == 0:
            return

        # format in json
        if not self.idx == None:
            lines = json.dumps(self.app.log[self.idx], indent=4, separators=(',', ': ')).splitlines()
            x = self.rect.x

            for i in range(0, self.rect.height):
                y = self.rect.y + i

                if i < len(lines):
                    self.app.stdscr.addnstr(y, x, lines[i], self.rect.width)
                else:
                    self.app.stdscr.move(y, x)
                    self.app.stdscr.clrtoeol()

    def select(self, idx):
        self.idx = idx


class LineView(Control):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.lines = []
        self.top = 0
        self.head = None
        self.highlight = None

    def update(self):
        if self.rect.width == 0 or self.rect.height == 0:
            return

        maxtop = len(self.lines) - self.rect.height + 1
        if self.top > maxtop:
            self.top = maxtop
        if self.top < 0:
            self .top = 0

        maxlen = self.rect.width
        x = self.rect.x
        y = self.rect.y

        if self.head != None:
            # print a head line
            self.app.stdscr.addnstr(y, x, self.head.ljust(maxlen), maxlen, curses.A_BOLD)
            y += 1

        i = self.top
        while y < self.rect.height:

            attr = 0
            if i == self.highlight:
                attr = curses.A_STANDOUT

            if i < len(self.lines):
                line = self.lines[i].ljust(maxlen)
                self.app.stdscr.addnstr(y, x, line, maxlen, attr)
            else:
                self.app.stdscr.move(y, x)
                self.app.stdscr.clrtoeol()

            y += 1
            i += 1


    def input(self, c):
        if c == curses.KEY_UP:
            self.top -= 1
        elif c == curses.KEY_DOWN:
            self.top += 1
        elif c == curses.KEY_NPAGE:
            self.top += self.rect.height
        elif c == curses.KEY_PPAGE:
            self.top -= self.rect.height

    def head(self, headline):
        self.head = headline

    def set(self, value):
        self.json = value

    def jsonLines(self, value):
        self.lines = json.dumps(value, indent=4, separators=(',', ': ')).splitlines()

class AgencyLogView(LineView):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.idx = None
        self.head = None

    def update(self):
        self.idx = self.app.list.highlight

        if self.idx < len(self.app.log):
            entry = self.app.log[self.idx]
            self.head = entry['_key']
            self.jsonLines(entry)

        super().update()

    def set(self, idx):
        self.idx = idx


class AgencyStoreView(LineView):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.store = None
        self.lastIdx = None
        self.path = []

    def layout(self, rect):
        super().layout(rect)

    def updateStore(self):
        idx = self.app.list.highlight
        if self.lastIdx == idx:
            return
        self.lastIdx = idx
        self.store = agency.AgencyStore()

        for i in range(0, idx+1):
            self.store.apply(self.app.log[i]["request"])

    def update(self):
        self.head = "/" + "/".join(self.path)
        self.updateStore()
        self.jsonLines(self.store._ref(self.path))
        super().update()

    def input(self, c):
        if c == ord('p'):
            pathstr = self.app.userString(prompt = "Path: ", default=self.head, complete=self.completePath)
            self.path = agency.AgencyStore.parsePath(pathstr)
        else:
            super().input(c)

    def set(self, store):
        self.store = store

    def completePath(self, pathstr):
        if self.store == None:
            return

        if len(pathstr) == 0:
            return "/"

        path = agency.AgencyStore.parsePath(pathstr)

        ref = self.store._ref(path)
        if ref == None:
            ref = self.store._ref(path[:-1])
            if not ref == None and isinstance(ref, dict):
                word = path[-1]
                # Now find all key that start with word
                keys = [h for h in ref.keys() if h.startswith(word)]

                if not len(keys) == 1:
                    return list(keys)
                else:
                    return "/" + "/".join(path[:-1] + [keys[0]])
        else:
            if pathstr[-1] == '/':
                if isinstance(ref, dict):
                    keys = list(ref.keys())

                    if not len(keys) == 1:
                        return keys
                    else:
                        return "/" + "/".join(path + [keys[0]])
            else:
                if isinstance(ref, dict):
                    return pathstr + '/'
        return None



class App:
    def __init__(self, stdscr, argv):
        self.stdscr = stdscr
        self.log = {}
        self.stop = False

        if len(argv) == 2:
            self.loadLogFromFile(argv[1])
        else:
            raise RuntimeError("Invalid number of arguments")

        self.layoutWindow()
        self.list = AgencyLogList(self, Rect.zero())
        self.view = AgencyStoreView(self, Rect.zero())
        self.logView = AgencyLogView(self, Rect.zero())
        self.switch = LayoutSwitch(Rect.zero(), [self.logView, self.view])

        self.split = LayoutColumns(self, self.rect, [self.list, self.switch], [4,6])

        self.focus = self.list

    def loadLogFromFile(self, filename):
        with open(filename) as f:
            self.log = json.load(f)

    def layoutWindow(self):
        # sacrifice the last column, since ncurses emulates a bug from the 80s
        # that throws an exception is one writes to the lower-right corner
        self.rect = Rect(0, 0, curses.COLS - 1, curses.LINES)

    def layout(self):
        # Update the layout of all child windows
        self.layoutWindow()
        self.split.layout(self.rect)

    def update(self):
        self.split.update()
        self.stdscr.refresh()

    def input(self, c):
        if c == curses.KEY_RESIZE:
            self.resize()
        elif c == ord(':'):
            cmdline = self.userString(prompt = ":").split()

            if len(cmdline) > 0:
                self.exec(cmdline)
        elif c == curses.KEY_RIGHT:
            self.focus = self.switch
        elif c == curses.KEY_LEFT:
            self.focus = self.list
        elif c == curses.KEY_F1:
            self.switch.select(0)
        elif c == curses.KEY_F2:
            self.switch.select(1)
        else:
            self.focus.input(c)

    def resize(self):
        curses.update_lines_cols()
        self.layout()

    def userInput(self):
        self.input(self.stdscr.getch())

    def run(self):
        while not self.stop:
            try:
                self.update()
                self.userInput()
            except Exception as err:
                self.displayMsg("Error: {}".format(err), ColorFormat.CF_ERROR)


    def exec(self, argv):

        cmd = argv[0]

        if cmd == "quit" or cmd == "q":
            self.stop = True
        elif cmd == "split":
            if len(argv) != 3:
                raise ValueError("Split requires two integer arguments")

            self.split.setRelations([int(argv[1]), int(argv[2])])
            self.layout()

        elif cmd == "view":
            if len(argv) != 2:
                raise ValueError("View requires either `log` or `store`")

            if argv[1] == "log":
                self.switch.select(0)
            elif argv[1] == "store":
                self.switch.select(1)
            else:
                raise ValueError("Unkown view: {}".format(argv[1]))
        elif cmd == "time":
            self.displayMsg("It is now {}".format(datetime.datetime.now().time()), 0)
        elif cmd == "help":
            self.displayMsg("Available commands: quit time error help")
        elif cmd == "error":
            raise Exception("This is a long error message with \n line breaks")
        else:
            raise NotImplementedError("Unkown command: {}".format(cmd))


    def displayMsg(self, msg, attr = 0):
        while True:
            x = self.rect.x
            maxlen = self.rect.width

            # display line by line, wrap long lines
            lines = [ wrap for line in msg.splitlines() for wrap in textwrap.wrap(line) ]
            top = self.rect.y + self.rect.height - len(lines)

            # display lines
            self.update()
            for i, line in enumerate(lines):
                self.stdscr.addnstr(top + i, x, line.ljust(maxlen), maxlen, attr)


            c = self.stdscr.getch()
            if c == curses.KEY_RESIZE:
                self.resize()
                self.update()
            else:
                self.update()
                self.input(c)
                break




    # Allows the user to type a string. Returns non when escape was pressed.
    # Complete is a callback function that is called with the already
    #   provided string and returns either an array of strings containing
    #   possible completions or a string containing the completed text
    def userString(self, label = None, complete = None, default = "", prompt = "> "):
        user = default
        hints = []

        curses.curs_set(1)
        try:
            while True:

                height = 1
                if not label == None:
                    height += 1

                if height > self.rect.height:
                    hints = []
                else:
                    height += len(hints)

                maxlen = self.rect.width - 1
                y = self.rect.y + self.rect.height - height
                x = self.rect.x

                self.update()

                # display the label in one line
                # then display possible hints
                # then display > and the user strings last bytes

                if not label == None:
                    self.stdscr.addnstr(y, x, label.ljust(maxlen), maxlen, curses.A_STANDOUT | curses.A_BOLD)
                    y += 1

                for h in hints:
                    self.stdscr.addnstr(y, x, h.ljust(maxlen), maxlen, curses.A_STANDOUT)
                    y += 1

                msg = (prompt + user[-maxlen+2:])
                self.stdscr.addnstr(y, x, msg, maxlen)
                self.stdscr.clrtoeol()

                c = self.stdscr.getch()
                if c == curses.KEY_RESIZE:
                    self.resize()
                    self.update()
                elif c == curses.KEY_BACKSPACE or c == curses.KEY_LEFT or c == curses.KEY_DC or c == curses.ascii.DEL:
                    user = user[:-1]
                elif c == ord('\n') or c == ord('\r'):
                    self.update()
                    return user
                elif c == ord('\t'):
                    # tabulator, time for auto complete
                    if not complete == None:
                        hints = []
                        hint = complete(user)
                        if isinstance(hint, list):
                            hints = hint
                        elif isinstance(hint, str):
                            user = hint
                elif not curses.has_key(c):
                    user += chr(c)
        finally:
            curses.curs_set(0)


class ColorPairs:
    CP_RED_WHITE = 1


class ColorFormat:
    CF_ERROR = None


def main(stdscr, argv):
    stdscr.clear()
    curses.curs_set(0)

    # initialise some colors
    curses.init_pair(ColorPairs.CP_RED_WHITE, curses.COLOR_RED, curses.COLOR_BLACK)

    # Init color formats
    ColorFormat.CF_ERROR = curses.A_BOLD | curses.color_pair(ColorPairs.CP_RED_WHITE);

    app = App(stdscr, argv)
    app.run()

if __name__ == '__main__':
    try:
        curses.wrapper(main, sys.argv)
    except Exception as e:
        raise e