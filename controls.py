import curses, curses.ascii

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
        super().update()
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
        super().update()
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
                line = self.lines[i]
                self.app.printStyleLine(y, x, line, maxlen, attr)
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
        elif c == curses.KEY_END:
            self.top = len(self.lines) - 1
        elif c == curses.KEY_HOME:
            self.top = 0


    def head(self, headline):
        self.head = headline

    def set(self, value):
        self.json = value

class App:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.stop = False

        self.debug = True
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

    def userInput(self):
        self.input(self.stdscr.getch())

    def run(self):
        while not self.stop:
            try:
                self.update()
                self.userInput()
            except Exception as err:
                self.displayMsg("Error: {}".format(err), ColorFormat.CF_ERROR)
                if self.debug:
                    raise err

    def execCmd(self, argv):
        raise NotImplementedError("Unkown command: {}".format(argv[0]))


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
                break

    # Allows the user to type a string. Returns non when escape was pressed.
    # Complete is a callback function that is called with the already
    #   provided string and returns either an array of strings containing
    #   possible completions or a string containing the completed text.
    #   Finally it can return a tuple, the first being the new string,
    #   the second the auto complete list.
    def userStringLine(self, label = None, complete = None, default = None, prompt = "> ", history = []):
        user = default if not default == None else ""
        hints = []
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

                if height > self.rect.height:
                    hints = []
                else:
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

                c = self.stdscr.getch()
                if c == curses.KEY_RESIZE:
                    self.resize()
                    self.update()
                elif c == curses.KEY_DC or c == curses.ascii.DEL:
                    if not cursorIndex == len(user):
                        user = user[:cursorIndex] + user[cursorIndex+1:]
                elif c == curses.KEY_BACKSPACE:
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
                        hints = []
                        hint = complete(user)
                        if isinstance(hint, list):
                            hints = hint
                        elif isinstance(hint, str):
                            user = hint
                            cursorIndex = len(user)
                        elif isinstance(hint, tuple):
                            user = hint[0]
                            hints = hint[1]
                            cursorIndex = len(user)
                elif not curses.has_key(c):
                    user = user[:cursorIndex] + chr(c) + user[cursorIndex:]
                    cursorIndex += 1
        finally:
            curses.curs_set(0)

    def printStyleLine(self, y, x, line, maxlen, defaultAttr = 0):
        if isinstance(line, str):
            line = [line]

        for p in line:
            if isinstance(p, str):
                p = (defaultAttr, p)
            strlen = len(p[1])
            self.stdscr.addnstr(y, x, p[1], maxlen, p[0])
            maxlen -= strlen
            if maxlen <= 0:
                break
            x += strlen

    def showProgress(self, progress, msg, label = None):
        # clamp progress into [0, 1]
        progress = max(0.0, min(1.0, progress))

        # If label is set and we have more than one line of space
        # Display the label left aligned.
        # Then display a progress bar, that contains msg string
        # and is highlighted for the percent part
        if self.rect.height == 0:
            return

        maxlen = self.rect.width - 1

        if self.rect.height > 1 and not label == None:
            self.stdscr.addnstr(self.rect.height - 2, 0, label.ljust(maxlen), maxlen, curses.A_STANDOUT)

        donelen = int(maxlen * progress)
        string = msg.ljust(maxlen)

        self.stdscr.addnstr(self.rect.height - 1, 0, string, donelen, curses.A_STANDOUT)
        self.stdscr.addnstr(self.rect.height - 1, donelen, string[donelen:], maxlen - donelen, 0)

        self.stdscr.refresh()
