import curses, curses.ascii
import textwrap
import json, time
from bisect import bisect_left
import threading
import queue

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

    def serialize(self):
        return {
            'idx': self.idx,
            'subs': list([c.serialize() for c in self.subs])
        }

    def restore(self, state):
        if not len(state['subs']) == len(self.subs):
            raise ValueError("LayoutSwitch has invalid restore state")

        for i, c in enumerate(self.subs):
            c.restore(state['subs'][i])
        self.idx = state['idx']

    def layout(self, rect):
        super().layout(rect)
        for s in self.subs:
            s.layout(rect)

    def input(self, c):
        self.subs[self.idx].input(c)

    def update(self):
        super().update()
        self.subs[self.idx].update()

    def select(self, idx):
        if not idx in range(0, len(self.subs)):
            raise ValueError("Invalid LayoutSwitch index")
        self.idx = idx
        self.update()

    def title(self):
        return self.subs[self.idx].title()

class LayoutColumns(Layout):
    def __init__(self, app, rect, columns, rels):
        super().__init__(rect)
        self.columns = columns
        self.bars = []
        self.app = app
        self.focus = 0
        self.setRelations(rels)
        self.layout(self.rect)

    def serialize(self):
        return {
            'rels': self.rels,
            'columns': list([c.serialize() for c in self.columns])
        }

    def restore(self, state):
        if not len(state['columns']) == len(self.columns):
            raise ValueError("LayoutColumns has invalid restore state")

        for i, c in enumerate(self.columns):
            c.restore(state['columns'][i])
        self.setRelations(state['rels'])

    def input(self, c):
        self.columns[self.focus].input(c)

    def update(self):
        super().update()

        if self.rect.height == 0:
            return

        # Paint head lines
        for i, ctrl in enumerate(self.columns):
            ctrl.update()
            attr = curses.A_UNDERLINE
            if i == self.focus:
                attr |= curses.A_STANDOUT
            maxlen =  ctrl.rect.width
            self.app.stdscr.addnstr(self.rect.y, ctrl.rect.x, ctrl.title().ljust(maxlen), maxlen, attr)

        # Paint vertical bars
        for x in self.bars:
            for y in range(0, self.rect.height):
                attr = 0
                c = curses.ACS_VLINE
                if y == 0:
                    attr = curses.A_UNDERLINE
                    c = " "
                self.app.stdscr.addch(self.rect.y + y, x, c, attr)


    def layout(self, rect):
        super().layout(rect)

        total = sum(self.rels)
        offset = self.rect.x
        avail = self.rect.width - len(self.columns) + 1
        self.bars = []

        for i, col in enumerate(self.columns):
            width = (avail * self.rels[i]) // total

            col.layout(Rect(
                offset, self.rect.y + 1,
                width, self.rect.height - 1
            ))
            offset += width
            self.bars.append(offset)
            offset += 1

        # remove last bar
        self.bars.pop()


    def setRelations(self, rels):
        if len(rels) != len(self.columns):
            raise ValueError("Invalid length of rels")
        self.rels = rels

    def title(self):
        return self.columns[self.focus].title()

    def toggleFocus(self):
        self.focus = (self.focus + 1) % len(self.columns)

class Control:

    def __init__(self, app, rect):
        self.app = app
        self.rect = rect

    def layout(self, rect):
        self.rect = rect

    def update(self):
        pass

    def input(self, c):
        return False

    def serialize(self):
        raise NotImplementedError("Serialize was not implemented by the Control")

    def restore(self, state):
        raise NotImplementedError("Restore was not implemented by the Control")

    def title(self):
        raise NotImplementedError("Title was not implemented by the Control")

class PureLineView(Control):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.lines = []
        self.top = 0
        self.head = None

    def serialize(self):
        return {
            'top': self.top,
            'head': self.head,
        }

    def restore(self, state):
        self.top = state['top']
        self.head = state['head']

    def update(self):
        if self.rect.width == 0 or self.rect.height == 0:
            return

        maxtop = len(self.lines) - self.rect.height + 1
        if self.head != None:
            maxtop += 1
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
        while y <= self.rect.height - 1:

            attr = 0
            if i < len(self.lines):
                line = self.lines[i]
                strlen = self.app.printStyleLine(y, x, line, maxlen, attr)
                if strlen < maxlen:
                    rlen = maxlen - strlen
                    self.app.stdscr.addnstr(y, x + strlen, "".ljust(rlen), rlen, 0)
            else:
                self.app.stdscr.addnstr(y, x, "".ljust(maxlen), maxlen, 0)

            y += 1
            i += 1

        if y <= self.rect.height:
            lastLine = i if i < len(self.lines) else len(self.lines)
            statusString = "Line {} to {} of {}".format(self.top + 1, lastLine, len(self.lines))
            self.app.stdscr.addnstr(y, x, statusString.ljust(maxlen), maxlen, curses.A_BOLD)

    def input(self, c):
        if c == curses.KEY_UP:
            self.top -= 1
        elif c == curses.KEY_DOWN:
            self.top += 1
        elif c == curses.KEY_NPAGE:
            self.top += self.rect.height
        elif c == curses.KEY_PPAGE:
            self.top -= self.rect.height
        elif c == curses.KEY_END:
            self.top = len(self.lines) - 1
        elif c == curses.KEY_HOME:
            self.top = 0


class LineView(Control):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.json = None
        self.lines = []
        self.top = 0
        self.head = None
        self.highlight = None
        self.findStr = None
        self.findList = []
        self.findHistory = []

    def serialize(self):
        return {
            'top': self.top,
            'head': self.head,
            'highlight': self.highlight,
            'findStr': self.findStr,
        }

    def restore(self, state):
        self.top = state['top']
        self.head = state['head']
        self.highlight = state['highlight']
        self.findStr = state['findStr']

    def update(self):
        if self.rect.width == 0 or self.rect.height == 0:
            return

        maxtop = len(self.lines) - self.rect.height + 1
        if self.head != None:
            maxtop += 1
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
        while y <= self.rect.height - 1:

            attr = 0
            if i == self.highlight:
                attr = curses.A_STANDOUT

            if i < len(self.lines):
                line = self.lines[i]
                formatted = self.format_line(line)
                strlen = self.app.printStyleLine(y, x, formatted, maxlen, attr)
                if strlen < maxlen:
                    rlen = maxlen - strlen
                    self.app.stdscr.addnstr(y, x + strlen, "".ljust(rlen), rlen, 0)
            else:
                self.app.stdscr.addnstr(y, x, "".ljust(maxlen), maxlen, 0)

            y += 1
            i += 1

        if y <= self.rect.height:
            lastLine = i if i < len(self.lines) else len(self.lines)
            statusString = "Line {} to {} of {}".format(self.top + 1, lastLine, len(self.lines))

            if not self.findStr == None:
                statusString += "; total {} occurences of `{}`".format(len(self.findList), self.findStr[0:10])

                if len(self.findList) > 0:
                    aboveCount = len(self.findList) - bisect_left(self.findList, self.top)
                    statusString += "; {} below, {} above top line".format(aboveCount, len(self.findList) - aboveCount)

            self.app.stdscr.addnstr(y, x, statusString.ljust(maxlen), maxlen, curses.A_BOLD)


    def find(self, string):
        if not string:
            self.reset()
        else:
            self.findStr = string
            self.jsonLines(self.json)
            self.next()
            self.findHistory.append(string)

    def reset(self):
        self.findStr = None
        self.jsonLines(self.json)

    def next(self):
        line = self.top
        for j in self.findList:
            if j > line:
                line = j
                break
        self.top = line

    def prev(self):
        line = self.top
        for j in reversed(self.findList):
            if j < line:
                line = j
                break
        self.top = line

    def input(self, c):
        if c == curses.KEY_UP:
            self.top -= 1
        elif c == curses.KEY_DOWN:
            self.top += 1
        elif c == curses.KEY_NPAGE:
            self.top += self.rect.height
        elif c == curses.KEY_PPAGE:
            self.top -= self.rect.height
        elif c == curses.KEY_END:
            self.top = len(self.lines) - 1
        elif c == curses.KEY_HOME:
            self.top = 0
        elif c == ord('f'):
            findStr = self.app.userStringLine(label = "Find", default = self.findStr, prompt = "> ", history = self.findHistory)
            if not findStr == None:
                self.find(findStr)
        elif c == ord('n'):
            self.next()
        elif c == ord('N'):
            self.prev()

    def searchLines(self):
        if self.findStr is not None:
            self.findList = []
            for i, line in enumerate(self.lines):
                if line.find(self.findStr) != -1:
                    self.findList.append(i)

    def format_line(self, line):
        def intersperse(lst, item):
            result = [item] * (len(lst) * 2 - 1)
            result[0::2] = lst
            return result

        annotation = self.getLineAnnotation(line)
        res = [line]
        if self.findStr is not None:
            split = line.split(self.findStr)
            if len(split) > 1:
                part = intersperse(split, (curses.A_STANDOUT, self.findStr))
                res = part
        if annotation is not None:
            if res is None:
                res = [line]
            assert isinstance(annotation, str)
            res.append((curses.A_ITALIC, " // {}".format(annotation)))
        return res


    def getLineAnnotation(self, line):
        return None

    def jsonLines(self, value):
        self.json = value
        self.lines = json.dumps(value, indent=4, separators=(',', ': ')).splitlines()
        self.searchLines()

    def set(self, value):
        self.json = value


class InputEvent:
    def __init__(self, key):
        self.key = key


class App:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.stop = False
        self.states = dict()
        self.stdscr.nodelay(True)

        self.input_queue = queue.Queue()
        self.input_thread = threading.Thread(target=self.read_input)
        self.input_thread.start()

        self.debug = False
        self.focus = None
        self.layoutWindow()

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

    def update(self):
        self.stdscr.refresh()

    def saveState(self, name):
        # load the specific states if set
        if name in self.states:
            yesNo = self.userStringLine(label = "Overwrite state {}".format(name), prompt = "[Y/n] ")
            if not (yesNo == "Y" or yesNo == "y" or yesNo == ""):
                return
        self.states[name] = self.serialize()
        self.displayMsg("State {} saved".format(name), curses.A_STANDOUT)

    def restoreState(self, name):
        if name in self.states:
            self.restore(self.states[name])
            self.displayMsg("State {} restored".format(name), curses.A_STANDOUT)
        else:
            self.displayMsg("State {} not found".format(name), curses.A_STANDOUT)

    def input(self, c):
        if c == curses.KEY_RESIZE:
            self.resize()
        elif c == ord(':'):
            cmdline = self.userStringLine(prompt = ":").split()

            if len(cmdline) > 0:
                self.execCmd(cmdline)
        else:
            if not self.focus == None:
                self.focus.input(c)

    def resize(self):
        curses.update_lines_cols()
        self.layout()

    def read_input(self):
        try:
            import select, sys
            while not self.stop:
                select.select([sys.stdin], [], [])
                inc = self.stdscr.getch()
                self.input_queue.put(InputEvent(inc))
        except:
            pass

    def clearWindow(self):
        self.stdscr.clear()

    def handleEvent(self, action):
        if isinstance(action, InputEvent):
            self.input(action.key)
        else:
            raise RuntimeError("Unknown action")

    def handle_events(self):
        item = self.input_queue.get()
        self.handleEvent(item)

    def waitForInput(self):
        self.stdscr.refresh()
        while True:
            item = self.input_queue.get()
            if isinstance(item, InputEvent):
                return item.key
            self.handleEvent(item)


    def run(self):
        while not self.stop:
            try:
                self.update()
                self.handle_events()
            except Exception as err:
                raise

    def queueEvent(self, ev):
        self.input_queue.put(ev)

    def __statesAutocomplete(self, user):
        return App.__autocompleteFromList(user, self.states.keys())

    def __autocompleteFromList(string, available):
        def common_prefix_idx(strings):
            if len(strings) == 0:
                return None

            maxlen = min(len(s) for s in strings)

            for i in range(0, maxlen):
                c = strings[0][i]

                if not all(s[i] == c for s in strings):
                    return i

            return maxlen

        valid = [x for x in available if x.startswith(string)]
        if len(valid) == 1:
            return valid[0]
        elif len(valid) == 0:
            return None
        else:
            idx = common_prefix_idx(valid)
            return (string[:idx], valid)


    def execCmd(self, argv):
        cmd = argv[0]

        if cmd == "store" or cmd == "save" or cmd == "s":
            if len(argv) == 2:
                self.saveState(argv[1])
            elif len(argv) == 1:
                name = self.userStringLine(label="Save to state: ", prompt="> ", complete = self.__statesAutocomplete)
                if name:
                    self.saveState(name)
            else:
                self.displayMsg("{} expects one argument".format(cmd), curses.A_STANDOUT)
        elif cmd == "restore" or cmd == "r":
            if len(argv) == 2:
                self.restoreState(argv[1])
            elif len(argv) == 1:
                name = self.userStringLine(label="Restore state: ", prompt="> ", complete = self.__statesAutocomplete)
                if name:
                    self.restoreState(name)
            else:
                self.displayMsg("{} expects one argument".format(cmd), curses.A_STANDOUT)
        else:
            raise NotImplementedError("Unknown command: {}".format(argv[0]))

    def displayMsg(self, msg, attr = 0):
        while True:
            x = self.rect.x
            maxlen = self.rect.width

            # display line by line, wrap long lines
            lines = [ wrap for line in msg.splitlines() for wrap in textwrap.wrap(line, maxlen) ]
            top = self.rect.y + self.rect.height - len(lines)

            # display lines
            self.update()
            for i, line in enumerate(lines):
                self.stdscr.addnstr(top + i, x, line.ljust(maxlen), maxlen, attr)


            c = self.waitForInput()
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
    #   possible completions or a string containing the completed text.
    #   Finally it can return a tuple, the first being the new string,
    #   the second the auto complete list.
    def userStringLine(self, label = None, complete = None, default = None, prompt = "> ", history = []):
        user = default if not default == None else ""
        hints = list()
        historyIdx = 0

        cursorIndex = len(user)
        userDisplayIndex = 0

        curses.curs_set(1)
        try:
            while True:

                # Validate userDisplayIndex and cursorIndex
                #   Make sure we have at least one char at the end to place the cursor
                #   after the last char of the user input.
                #   The userDisplayIndex should be move such that the cursorIndex is visible
                if cursorIndex < 0:
                    cursorIndex = 0

                if cursorIndex < userDisplayIndex:
                    userDisplayIndex = cursorIndex

                visibleLength = self.rect.width - len(prompt)
                if visibleLength < 0:
                    visibleLength = 0

                if cursorIndex > len(user):
                    cursorIndex = len(user)

                if cursorIndex - userDisplayIndex > visibleLength:
                    userDisplayIndex = cursorIndex - visibleLength

                cursorPosY = len(prompt) + cursorIndex - userDisplayIndex
                if cursorPosY >= self.rect.width:
                    cursorPosY = None

                height = 1
                if not label == None:
                    height += 1

                maxHints = min(self.rect.height - height, 20) - 1

                if len(hints) > maxHints:
                    hints = hints[:maxHints] + ["(list truncated)"]
                height += len(hints)


                maxlen = self.rect.width
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

                msg = (prompt + user[userDisplayIndex:])
                self.stdscr.addnstr(y, x, msg, maxlen)
                self.stdscr.clrtoeol()

                if not cursorPosY == None:
                    self.stdscr.move(y, self.rect.y + cursorPosY)

                c = self.waitForInput()
                if c == curses.KEY_RESIZE:
                    self.resize()
                    self.update()
                elif c == curses.KEY_DC:
                    if not cursorIndex == len(user):
                        user = user[:cursorIndex] + user[cursorIndex+1:]
                elif c == curses.KEY_BACKSPACE or c == curses.ascii.DEL:
                    if not cursorIndex == 0:
                        user = user[:cursorIndex-1] + user[cursorIndex:]
                        cursorIndex -= 1
                elif c == ord('\n') or c == ord('\r'):
                    self.update()
                    return user
                elif c == curses.KEY_LEFT:
                    cursorIndex -= 1
                elif c == curses.KEY_RIGHT:
                    cursorIndex += 1
                elif c == curses.KEY_HOME:
                    cursorIndex = 0
                elif c == curses.KEY_END:
                    cursorIndex = len(user)
                elif c == curses.KEY_UP:
                    historyIdx = max(historyIdx - 1, -len(history))
                    if not historyIdx == 0:
                        user = history[historyIdx]
                        cursorIndex = len(user)
                    else:
                        user = ""
                elif c == curses.KEY_DOWN:
                    historyIdx = min(historyIdx + 1, 0)
                    if not historyIdx == 0:
                        user = history[historyIdx]
                        cursorIndex = len(user)
                    else:
                        user = ""
                elif c == ord('\t'):
                    # tabulator, time for auto complete
                    if not complete == None:
                        hints = list()
                        hint = complete(user)
                        if isinstance(hint, list):
                            hints = hint
                        elif isinstance(hint, str):
                            user = hint
                            cursorIndex = len(user)
                        elif isinstance(hint, tuple):
                            user = hint[0]
                            hints = list(hint[1])
                            cursorIndex = len(user)
                elif not curses.has_key(c):
                    user = user[:cursorIndex] + chr(c) + user[cursorIndex:]
                    cursorIndex += 1
        finally:
            curses.curs_set(0)

    def printStyleLine(self, y, x, line, maxlen, defaultAttr = 0):
        if isinstance(line, str):
            line = [line]
        totalLen = 0
        for p in line:
            if isinstance(p, str):
                p = (defaultAttr, p)
            if len(p) < 2:
                raise RuntimeError(f"{p=}")
            strlen = len(p[1])
            totalLen += strlen
            self.stdscr.addnstr(y, x, p[1], maxlen, p[0])
            maxlen -= strlen
            if maxlen <= 0:
                break
            x += strlen
        return totalLen


    def showProgress(self, progress, msg, label = None, rect = None):
        # clamp progress into [0, 1]
        progress = max(0.0, min(1.0, progress))

        if rect == None:
            rect = self.rect

        # If label is set and we have more than one line of space
        # Display the label left aligned.
        # Then display a progress bar, that contains msg string
        # and is highlighted for the percent part
        if rect.height == 0:
            return

        maxlen = rect.width - 1

        if rect.height > 1 and not label == None:
            self.stdscr.addnstr(rect.height - 2, 0, label.ljust(maxlen), maxlen, curses.A_STANDOUT)

        donelen = int(maxlen * progress)
        string = msg.ljust(maxlen)

        self.stdscr.addnstr(rect.height, rect.x, string, donelen, curses.A_STANDOUT)
        self.stdscr.addnstr(rect.height, rect.x + donelen, string[donelen:], maxlen - donelen, 0)

        self.stdscr.refresh()
