#!/usr/bin/python3

import sys
import json
import textwrap
import datetime
import re
from time import sleep

import agency
from controls import *

ARANGO_LOG_ZERO = "00000000000000000000"


class AgencyLogList(Control):

    FILTER_NONE = 0
    FILTER_GREP = 1
    FILTER_REGEX = 2

    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.app = app
        self.top = 0
        self.highlight = 0
        self.filterStr = None
        # list contains all displayed log indexes
        self.list = None
        self.filterType = AgencyLogList.FILTER_NONE
        self.filterHistory = []
        self.formatString = "[{timestamp}|{term}] {_id} {urls}"

    def layout(self, rect):
        super().layout(rect)

    def __getIndexRelative(self, i):
        idx = self.top + i
        if not self.list == None:
            if idx >= len(self.list):
                return None
            idx = self.list[idx]

        if idx >= len(self.app.log):
            return None
        return idx

    def __getIndex(self, i):
        idx = i
        if not self.list == None:
            if idx >= len(self.list):
                return None
            idx = self.list[idx]
        if idx >= len(self.app.log):
            return None
        return idx


    def __getListLen(self):
        if not self.list == None:
            return len(self.list)
        return len(self.app.log)

    def update(self):
        # Update top
        maxPos = self.__getListLen() - 1
        maxTop = max(0, maxPos - self.rect.height + 1)

        if not self.highlight == None:
            if self.highlight > maxPos:
                self.highlight = maxPos
            if self.highlight < 0:
                self.highlight = 0

            if self.highlight < self.top:
                self.top = self.highlight

            bottom = self.top + self.rect.height - 1
            if self.highlight >= bottom:
                self.top = self.highlight - self.rect.height + 1

        if self.top > maxTop:
            self.top = maxTop

        if self.top < 0:
            self.top = 0

        if self.rect.width == 0:
            return

        maxlen = self.rect.width

        # Paint all lines from top up to height many
        for i in range(0, self.rect.height):
            idx = self.__getIndexRelative(i)

            y = self.rect.y + i
            x = self.rect.x
            if not idx == None:
                ent = self.app.log[idx]

                text = " ".join(x for x in ent["request"])
                msg = self.formatString.format(**ent, urls=text).ljust(self.rect.width)

                attr = 0
                if idx == self.getSelectedIndex():
                    attr |= curses.A_STANDOUT
                if not self.app.snapshot == None:
                    if ent["_key"] < self.app.snapshot["_key"]:
                        attr |= curses.A_DIM

                self.app.stdscr.addnstr(y, x, msg, maxlen, attr)
            elif i == 0:
                self.app.stdscr.addnstr(y, x, "Nothing to display", maxlen, curses.A_BOLD | ColorFormat.CF_ERROR)
            else:
                self.app.stdscr.move(y, x)
            self.app.stdscr.clrtoeol()

    def filter(self, predicate):
        # Make sure that the highlighted entry is the previously selected
        # entry or the closest entry above that one.
        lastHighlighted = self.__getIndex(self.highlight)
        if lastHighlighted == None:
            lastHighlighted = 0

        self.list = []
        self.highlight = 0
        for i, e in enumerate(self.app.log):
            match = predicate(e)
            if match:
                if i <= lastHighlighted:
                    self.highlight = len(self.list)
                self.list.append(i)

    def regexp(self, regexStr):
        self.reset()

        if not regexStr:
            return

        # try to compile the regex
        self.filterStr = regexStr

        pattern = re.compile(regexStr)
        predicate = lambda e: any(not pattern.search(path) == None for path in e["request"])

        self.filterType = AgencyLogList.FILTER_REGEX
        self.filter(predicate)

    def grep(self, string):
        self.reset()
        if not string:
            return

        predicate = lambda e: string in json.dumps(e)

        self.filterStr = string
        self.filterType = AgencyLogList.FILTER_GREP
        self.filter(predicate)


    def reset(self):
        self.list = None
        self.filterStr = None
        self.filterType = AgencyLogList.FILTER_NONE

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
        elif c == curses.KEY_END:
            self.highlight = self.__getListLen() - 1
        elif c == curses.KEY_HOME:
            self.highlight = 0
        elif c == ord('f'):
            regexStr = self.app.userStringLine(label = "Regular Search Expr", default = self.filterStr, prompt = "> ", history = self.filterHistory)
            if not regexStr == None:
                if regexStr:
                    self.filterHistory.append(regexStr)
                self.regexp(regexStr)
        elif c == ord('g'):
            string = self.app.userStringLine(label = "Global Search Expr", default = self.filterStr, prompt = "> ", history = self.filterHistory)
            if not string == None:
                if string:
                    self.filterHistory.append(string)
                self.grep(string)
        elif c == ord('R'):
            yesNo = self.app.userStringLine(label = "Reset all filters", prompt = "[Y/n] ")
            if yesNo == "Y":
                self.reset()

    # Returns the index of the selected log entry.
    #   This value is always with respect to the app.log array.
    #   You do not need to worry about filtering
    def getSelectedIndex(self):
        if not self.list == None:
            if self.highlight < len(self.list):
                return self.list[self.highlight]
            return None
        return self.highlight

    def selectClosest(self, idx):
        if not self.list == None:
            for i in self.list:
                if i <= idx:
                    self.highlight = i
                    self.top = i
        else:
            self.highlight = idx
            self.top = idx

class AgencyLogView(LineView):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.idx = None
        self.head = None

    def update(self):
        self.idx = self.app.list.getSelectedIndex()

        if not self.idx == None and self.idx < len(self.app.log):
            entry = self.app.log[self.idx]
            self.head = entry['_key']
            self.jsonLines(entry)
            self.highlightLines()

        super().update()

    def highlightLines(self):
        def intersperse(lst, item):
            result = [item] * (len(lst) * 2 - 1)
            result[0::2] = lst
            return result

        logList = self.app.list
        if not logList.filterType == AgencyLogList.FILTER_GREP:
            return

        filt = logList.filterStr
        if filt:
            for i, line in enumerate(self.lines):
                part = intersperse(line.split(filt), (curses.A_BOLD, filt))
                self.lines[i] = part

    def jsonLines(self, value):
        self.lines = json.dumps(value, indent=4, separators=(',', ': ')).splitlines()

    def set(self, idx):
        self.idx = idx


class AgencyStoreView(LineView):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.store = None
        self.lastIdx = None
        self.path = []
        self.pathHistory = []

    def layout(self, rect):
        super().layout(rect)

    def updateStore(self):
        idx = self.app.list.getSelectedIndex()
        if idx == None:
            return

        if self.lastIdx == idx:
            return
        self.lastIdx = idx

        # if the id of the first log entry is ARANGO_LOG_ZERO,
        # generate the agency from empty store
        # otherwise check if the log entry is after (>=) the
        log = self.app.log
        if log == None or len(log) == 0:
            return
        snapshot = self.app.snapshot

        self.store = None

        if log[0]["_key"] == ARANGO_LOG_ZERO:
            # just apply all log entries
            self.store = agency.AgencyStore()
            for i in range(0, idx+1):
                self.store.apply(self.app.log[i]["request"])
        elif snapshot == None:
            self.head = None
            self.lines = [[(ColorFormat.CF_ERROR, "No snapshot available")]]
            return
        elif log[idx]["_key"] < snapshot["_key"]:
            self.head = None
            self.lines = [[(ColorFormat.CF_ERROR, "Can not replicate agency state. Not covered by snapshot.")]]
            return
        else:
            self.store = agency.AgencyStore(snapshot["readDB"][0])
            for i in range(self.app.firstValidLogIdx, idx+1):
                if log[idx]["_key"] >= snapshot["_key"]:
                    self.store.apply(self.app.log[i]["request"])

        self.jsonLines(self.store._ref(self.path))


    def update(self):
        self.head = "/" + "/".join(self.path)
        self.updateStore()
        super().update()

    def input(self, c):
        if c == ord('p'):
            pathstr = self.app.userStringLine(prompt = "> ", label = "Agency Path:", default=self.head, complete=self.completePath, history = self.pathHistory)
            self.path = agency.AgencyStore.parsePath(pathstr)
            self.pathHistory.append(pathstr)
            self.lastIdx = None # trigger update
        else:
            super().input(c)

    def set(self, store):
        self.store = store

    def jsonLines(self, value):
        self.lines = json.dumps(value, indent=4, separators=(',', ': ')).splitlines()

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

class ArangoAgencyAnalyserApp(App):
    def __init__(self, stdscr, argv):
        super().__init__(stdscr)
        self.log = None
        self.snapshot = None
        self.firstValidLogIdx = None

        self.list = AgencyLogList(self, Rect.zero())
        self.view = AgencyStoreView(self, Rect.zero())
        self.logView = AgencyLogView(self, Rect.zero())
        self.switch = LayoutSwitch(Rect.zero(), [self.logView, self.view])

        self.split = LayoutColumns(self, self.rect, [self.list, self.switch], [4,6])
        self.focus = self.list

        if len(argv) == 2:
            self.loadLogFromFile(argv[1])
        elif len(argv) == 3:
            self.loadLogFromFile(argv[1])
            self.loadSnapshotFromFile(argv[2], updateSelection = True)
        else:
            raise RuntimeError("Invalid number of arguments")


    def loadLogFromFile(self, filename):
        with open(filename) as f:
            self.log = json.load(f)

    def loadSnapshotFromFile(self, filename, updateSelection = False):
        with open(filename) as f:
            self.snapshot = json.load(f)

            # update the highlighted entry to be the first available in
            # snapshot. Assume log is already loaded.
            self.firstValidLogIdx = None
            for i, e in enumerate(self.log):
                if e["_key"] <= self.snapshot["_key"]:
                    self.firstValidLogIdx = i
                else:
                    break

            if updateSelection:
                self.list.selectClosest(self.firstValidLogIdx)

    def update(self):
        self.split.update()
        super().update()

    def execCmd(self, argv):
        cmd = argv[0]

        if cmd == "quit" or cmd == "q":
            self.stop = True
        elif cmd == "debug":
            self.debug = True
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
            self.displayMsg("Nobody can help you now - except maybe README.md")
        elif cmd == "error":
            raise Exception("This is a long error message with \n line breaks")
        else:
            super().execCmd(argv)

    def input(self, c):
        if c == curses.KEY_RIGHT:
            self.focus = self.switch
        elif c == curses.KEY_LEFT:
            self.focus = self.list
        elif c == curses.KEY_F1:
            self.switch.select(0)
        elif c == curses.KEY_F2:
            self.switch.select(1)
        else:
            super().input(c)

    def layout(self):
        super().layout()
        self.split.layout(self.rect)

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

    app = ArangoAgencyAnalyserApp(stdscr, argv)
    app.run()

if __name__ == '__main__':
    try:
        curses.wrapper(main, sys.argv)
    except Exception as e:
        raise e
