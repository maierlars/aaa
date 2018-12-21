from controls import Control, ColorPairs
import copy
import curses

# JsonView Control allows to open and close sub objects and arrays. (+/-)
# Additional the syntax of json is highlighted.
# Controls:
#   Up/Down     next/prev property
#   Left/Right  switch name and value
#   :(h)ere     set path to the current selected path



class JsonView(Control):

    # Given the python internal representation of the json data, i.e. via
    # dicts and lists, a list of lines is generated usable for printStyleLine.
    # The line data consists of:
    #   indent: how many cells to clear before printing
    #   keyRange: range of the line pieces representing the key value (None if none)
    #   valueRange: same as above but for values (None if not selectable, i.e. array)
    #   line: the actual string
    #   path: list of strings representing the path to this element, may be none

    class LineData():

        TYPE_NONE = 0
        TYPE_PRIMITIVE = 1
        TYPE_OBJECT = 2
        TYPE_ARRAY = 3

        def __init__(self, indent, path = None):
            self.indent = indent
            self.keyRange = None
            self.valueRange = None
            self.valueLineRange = None
            self.valueType = self.TYPE_NONE
            self.line = []
            self.path = path
            self.collapsed = False
            self.parentLine = None

        def __repr__(self):
            return "{{indent = {}, key = {}, value = {}, line = {}, path = {}}}".format(
                self.indent,
                self.keyRange,
                self.valueRange,
                self.line,
                "/".join(self.path) if not self.path == None else "None")

        def add(self, string):
            self.line += string

        def key(self, string):
            assert self.keyRange == None
            self.keyRange = (len(self.line), len(string))
            self.line += string

        def value(self, string):
            assert self.valueRange == None
            self.valueRange = (len(self.line), len(string))
            self.line += string

        def lineRange(self, lineRange, valueType):
            self.valueLineRange = lineRange
            self.valueType = valueType

        def selectable(self):
            return not self.valueRange == None or not self.keyRange == None

        def setCollapse(self, yesNo):
            if not self.valueLineRange == None:
                self.collapsed = yesNo
            elif not self.parentLine == None:
                self.parentLine.setCollapse(yesNo)

    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.highlight = 3
        self.top = 0
        self.lines = []

    def parseDict(value, lineData, indent, path):
        assert isinstance(value, dict)

        if len(value) == 0:
            lineData[-1].add(["{}"])
            return

        firstIdx = len(lineData) - 1
        first = lineData[-1]
        # append { to the last line
        first.value(["{"])

        for key in value:
            subindent = indent + 2
            subpath = path + [key]
            data = JsonView.LineData(subindent, subpath)
            # add the key
            data.key([(JsonColors.KEY, '"{}"'.format(key))])
            data.add(": ")
            lineData.append(data)

            JsonView.parseValue(value[key], lineData, subindent, subpath)

            # place the comma
            lineData[-1].add([","])

        # add a final line with closing }
        lastIdx = len(lineData)
        last = JsonView.LineData(indent, path)
        last.value(["}"])
        last.parentLine = first
        lineData.append(last)

        first.lineRange(lastIdx - firstIdx, JsonView.LineData.TYPE_OBJECT)

    def parseList(value, lineData, indent, path):
        assert isinstance(value, list)

        if len(value) == 0:
            lineData[-1].add(["[]"])
            return

        firstIdx = len(lineData) - 1
        first = lineData[-1]

        # append [ to the last line
        first.value(["["])

        for idx, subvalue in enumerate(value):
            subindent = indent + 2
            subpath = path + ["[{}]".format(idx)]
            data = JsonView.LineData(subindent, subpath)
            lineData.append(data)
            JsonView.parseValue(subvalue, lineData, subindent, subpath)

            # place the comma
            lineData[-1].add([","])

        # add a final line with closing ]
        lastIdx = len(lineData)
        last = JsonView.LineData(indent, path)
        last.value(["]"])
        last.parentLine = first
        lineData.append(last)

        first.lineRange(lastIdx - firstIdx, JsonView.LineData.TYPE_ARRAY)

    def parsePrimitiveValue(value, lineData, indent, path):
        if isinstance(value, str):
            lineData[-1].value([
                (JsonColors.STRING, '"{}"'.format(value))
            ])
        elif value is False:
            lineData[-1].value([
                (JsonColors.FALSE, "false")
            ])
        elif value is True:
            lineData[-1].value([
                (JsonColors.TRUE, "true")
            ])
        elif value is None:
            lineData[-1].value([
                (JsonColors.NULL, "null")
            ])
        elif isinstance(value, int) or isinstance(value, float):
            lineData[-1].value([
                (JsonColors.NUMBER, str(value))
            ])
        else:
            assert False

    def parseValue(value, lineData, indent, path):
        if isinstance(value, dict):
            JsonView.parseDict(value, lineData, indent, path)
        elif isinstance(value, list):
            JsonView.parseList(value, lineData, indent, path)
        else:
            JsonView.parsePrimitiveValue(value, lineData, indent, path)


    def set(self, value):
        self.highlight = 0
        self.lines = [JsonView.LineData(0)]
        JsonView.parseValue(value, self.lines, 0, [])

    def previousVisibleIndex(self, idx):
        while True:

            idx -= 1
            if idx < 0:
                return None

            line = self.lines[idx]

            parentLine = line.parentLine
            if not parentLine == None and parentLine.collapsed:
                idx -= parentLine.valueLineRange - 1
                continue

            if not line.selectable():
                continue

            return idx

    def nextVisibleIndex(self, idx):
        while True:
            if idx >= len(self.lines):
                return None
            current = self.lines[idx]
            if current.collapsed:
                idx += current.valueLineRange
                continue

            idx += 1
            if idx >= len(self.lines):
                return None
            line = self.lines[idx]
            if not line.selectable():
                continue

            return idx

    def nextHighlight(self):
        idx = self.nextVisibleIndex(self.highlight)
        if not idx == None:
            self.highlight = idx

    def prevHighlight(self):
        idx = self.previousVisibleIndex(self.highlight)
        if not idx == None:
            self.highlight = idx

    def pageDownHighlight(self):
        idx = self.nextVisibleIndex(self.highlight + self.rect.height)
        if not idx == None:
            self.highlight = idx
        else:
            idx = self.previousVisibleIndex(self.highlight + self.rect.height)
            if not idx == None:
                self.highlight = idx

    def pageUpHighlight(self):
        idx = self.previousVisibleIndex(self.highlight - self.rect.height)
        if not idx == None:
            self.highlight = idx
        else:
            idx = self.nextVisibleIndex(self.highlight - self.rect.height)
            if not idx == None:
                self.highlight = idx

    def input(self, c):
        if c == curses.KEY_DOWN:
            self.nextHighlight()
        elif c == curses.KEY_UP:
            self.prevHighlight()
        elif c == curses.KEY_NPAGE:
            self.pageDownHighlight()
        elif c == curses.KEY_PPAGE:
            self.pageUpHighlight()
        elif c == curses.KEY_HOME:
            self.highlight = 0
        elif c == curses.KEY_END:
            self.highlight = len(self.lines) - 1
        elif c == ord('-'):
            self.lines[self.highlight].setCollapse(True)
        elif c == ord('+'):
            self.lines[self.highlight].setCollapse(False)
        elif c == ord('.'):
            line = self.lines[self.highlight]
            line.setCollapse(not line.collapsed)

    def update(self):
        # Update indexes
        self.__updateIndexes()
        # Prepare lines
        self.__updatePaint()

    def __updateIndexes(self):
        if self.top > self.highlight:
            self.top = self.highlight

        elif self.top < self.highlight:
            # This code tries to find the screen distance between top
            # and highlight to adjust top of required
            screenY = 0
            idx = self.top
            while True:
                if idx >= len(self.lines):
                    self.highlight = 0
                    self.top = 0
                    return # break try to recover
                elif idx > self.highlight:
                    self.highlight = idx
                    break
                elif idx == self.highlight:
                    break
                line = self.lines[idx]

                if line.collapsed:
                    idx += line.valueLineRange

                idx += 1
                screenY += 1

            if screenY >= self.rect.height:
                self.top += screenY - self.rect.height + 1
                if self.top > len(self.lines):
                    self.top = len(self.lines) - 1

    def __updatePaint(self):
        # Paint lines, make sure top and highlight are printed lines
        idx = self.top
        x = self.rect.x

        for y in range(0, self.rect.height):

            if idx < len(self.lines):
                lineData = self.lines[idx]
                line = lineData.line

                modifier = None

                # check if this is highlighted
                if idx == self.highlight:
                    # get the required indexes
                    updateRange = None
                    if not lineData.keyRange == None:
                        updateRange = lineData.keyRange
                    elif not lineData.valueRange == None:
                        updateRange = lineData.valueRange
                    # if needed set a line modifier to highlight key parts
                    if not updateRange == None:
                        modifier = lambda i, p: p if not i in range(updateRange[0], updateRange[1]) else (p[0] | curses.A_STANDOUT, p[1])

                suffix = []

                if lineData.collapsed:
                    if lineData.valueType == JsonView.LineData.TYPE_OBJECT:
                        suffix = [" ... },"]
                    elif lineData.valueType == JsonView.LineData.TYPE_ARRAY:
                        suffix += [" ... ],"]
                    idx += lineData.valueLineRange

                self.app.printStyleLine(self.rect.y + y, x, line + suffix, self.rect.width, modifier = modifier, indent = lineData.indent)

            else:
                self.app.stdscr.move(self.rect.y + y, x)
            self.app.stdscr.clrtoeol()
            idx += 1

    def layout(self, rect):
        super().layout(rect)


class JsonColors:
    STRING = 0
    KEY = 0
    NUMBER = 0
    TRUE = 0
    FALSE = 0
    NULL = 0

    def init():
        JsonColors.STRING = curses.color_pair(ColorPairs.GREEN_BLACK)
        JsonColors.KEY = curses.color_pair(ColorPairs.BLUE_BLACK)
        JsonColors.NUMBER = curses.color_pair(ColorPairs.CYAN_BLACK)
        JsonColors.TRUE = curses.A_BOLD
        JsonColors.FALSE = curses.A_BOLD
        JsonColors.NULL = curses.A_BOLD


