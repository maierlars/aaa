#!/usr/bin/env python3

import sys
import os
import json
import datetime
import re
from time import sleep
import argparse
from urllib.parse import urlparse

import agency
from controls import *
from client import *

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
        self.formatString = "[{timestamp}|{term}] {_key} {urls}"

    def title(self):
        return "Agency Log"

    def serialize(self):
        return {
            'top': self.top,
            'highlight': self.highlight,
            'filterStr': self.filterStr,
            'filterType': self.filterType,
            'filterHistory': self.filterHistory,
            'formatString': self.formatString
        }

    def restore(self, state):
        self.top = state['top']
        self.highlight = state['highlight']
        self.filterStr = state['filterStr']
        self.filterType = state['filterType']
        self.filterHistory = state['filterHistory']
        self.formatString = state['formatString']
        self.__rebuildFilterList()

    def __rebuildFilterList(self):
        if self.filterType == AgencyLogList.FILTER_NONE:
            self.list = None
        elif self.filterType == AgencyLogList.FILTER_GREP:
            self.grep(self.filterStr)
        elif self.filterType == AgencyLogList.FILTER_REGEX:
            self.regexp(self.filterStr)
        else:
            raise NotImplementedError()

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
        # get the current index to keep the selected entry
        self.highlight = self.getSelectedIndex()
        if self.highlight == None:
            self.highlight = 0
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
            if yesNo == "Y" or yesNo == "y":
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
        self.lastIdx = None
        self.head = None

    def title(self):
        key = self.app.log[self.idx]['_key'] if not self.idx == None else ""
        return "Agency Log View {}".format(key)

    def serialize(self):
        return {
            'idx': self.idx,
            'head': self.head
        }

    def restore(self, state):
        self.idx = state['idx']
        self.head = state['head']

    def update(self):
        self.idx = self.app.list.getSelectedIndex()

        if not self.idx == self.lastIdx :
            if self.idx == None:
                self.jsonLines(None)
            elif not self.idx == None and self.idx < len(self.app.log):
                entry = self.app.log[self.idx]
                self.head = None #entry['_key']

                loglist = self.app.list
                if loglist.filterType == AgencyLogList.FILTER_GREP:
                    self.findStr = loglist.filterStr
                else:
                    self.findStr = None
                self.jsonLines(entry)

        self.lastIdx = self.idx
        super().update()

    def set(self, idx):
        self.idx = idx


class AgencyStoreView(LineView):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.store = None
        self.lastIdx = None
        self.path = []
        self.pathHistory = []

    def title(self):
        return "Agency Store View"

    def serialize(self):
        return {
            'path': self.path,
            'pathHistory': self.pathHistory
        }

    def restore(self, state):
        self.path = state['path']
        self.pathHistory = state['pathHistory']
        self.lastIdx = None

    def layout(self, rect):
        super().layout(rect)

    def updateStore(self):
        idx = self.app.list.getSelectedIndex()
        if idx == None:
            return

        if self.lastIdx == idx:
            return

        # if the id of the first log entry is ARANGO_LOG_ZERO,
        # generate the agency from empty store
        # otherwise check if the log entry is after (>=) the
        log = self.app.log
        if log == None or len(log) == 0:
            return
        snapshot = self.app.snapshot

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
            startidx = self.lastIdx
            if self.lastIdx == None or self.store == None or idx < self.lastIdx:
                startidx = self.app.firstValidLogIdx
                self.store = agency.AgencyStore(snapshot["readDB"][0])

            for i in range(startidx, idx+1):
                if log[idx]["_key"] >= snapshot["_key"]:
                    self.store.apply(self.app.log[i]["request"])

        self.lastIdx = idx
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

    def __common_prefix_idx(self, strings):
        if len(strings) == 0:
            return None

        maxlen = min(len(s) for s in strings)

        for i in range(0, maxlen):
            c = strings[0][i]

            if not all(s[i] == c for s in strings):
                return i

        return maxlen


    def completePath(self, pathstr):
        if self.store == None:
            return

        if len(pathstr) == 0:
            return "/"

        path = agency.AgencyStore.parsePath(pathstr)

        if pathstr[-1] == "/":
            ref = self.store._ref(path)
            if not ref == None and isinstance(ref, dict):
                return list(ref.keys())
        else:
            ref = self.store._ref(path[:-1])
            if not ref == None and isinstance(ref, dict):
                word = path[-1]
                # Now find all key that start with word
                keys = [h for h in ref.keys() if h.startswith(word)]

                if len(keys) == 0:
                    return None

                if len(keys) > 1:

                    # first complete to the common sub
                    common = keys[0][:self.__common_prefix_idx(keys)]

                    if path[-1] == common:
                        return list(keys)

                    return "/" + "/".join(path[:-1] + [common])

                elif path[-1] == keys[0] and not pathstr[-1] == "/":
                    ref = self.store._ref(path)
                    if not ref == None and isinstance(ref, dict):
                        return (pathstr + "/", ref.keys())
                else:
                    return "/" + "/".join(path[:-1] + [keys[0]])
        return None

class ArangoAgencyAnalyserApp(App):
    def __init__(self, stdscr, provider):
        super().__init__(stdscr)
        self.log = None
        self.snapshot = None
        self.firstValidLogIdx = None

        self.list = AgencyLogList(self, Rect.zero())
        self.view = AgencyStoreView(self, Rect.zero())
        self.logView = AgencyLogView(self, Rect.zero())
        self.switch = LayoutSwitch(Rect.zero(), [self.logView, self.view])

        self.split = LayoutColumns(self, self.rect, [self.list, self.switch], [4,6])
        self.focus = self.split

        self.provider = provider
        self.refresh(updateSelection = True)
        # if len(argv) == 2:
        #     self.loadLogFromFile(argv[1])
        # elif len(argv) == 3:
        #     self.loadLogFromFile(argv[1])
        #     self.loadSnapshotFromFile(argv[2], updateSelection = True)
        # else:
        #     raise RuntimeError("Invalid number of arguments")

    def serialize(self):
        return {
            'split': self.split.serialize(),
        }

    def restore(self, state):
        self.split.restore(state['split'])

    def refresh(self, updateSelection = False):
        self.provider.refresh()
        self.log = self.provider.log()
        self.snapshot = self.provider.snapshot()
        self.firstValidLogIdx = None

        msg = "Loaded {count} log entries, ranging from\n{first[timestamp]} ({first[_key]}) to {last[timestamp]} ({last[_key]}).".format(count = len(self.log), first = self.log[0], last = self.log[-1])

        if not self.snapshot == None:
            for i, e in enumerate(self.log):
                if e["_key"] <= self.snapshot["_key"]:
                    self.firstValidLogIdx = i
                else:
                    break

            if updateSelection:
                self.list.selectClosest(self.firstValidLogIdx)

            msg += "\nUsing snapshot {snapshot[_id]}.".format(snapshot = self.snapshot)

        self.displayMsg(msg, curses.A_STANDOUT)

    def dumpJSON(self, filename):
        if self.switch.idx == 0:
            entry = self.log[self.logView.idx]
            with open(filename, "w") as f:
                json.dump(entry, f)
        elif self.switch.idx == 1:
            store = self.view.store._ref(self.view.path)
            with open(filename, "w") as f:
                json.dump(store, f)

    def dumpAll(self, logfile, snapshotfile):
        with open(logfile, "w") as f:
            json.dump(self.log, f)
        with open(snapshotfile, "w") as f:
            json.dump(self.snapshot, f)

    def update(self):
        self.split.update()
        super().update()

    def execCmd(self, argv):
        cmd = argv[0]

        if cmd == "quit" or cmd == "q":
            self.stop = True
        elif cmd == "debug":
            self.debug = True
        elif cmd == "dump":
            if len(argv) != 2:
                raise ValueError("Dump requires one parameter")
            self.dumpJSON(argv[1])
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
        elif cmd == "dump-all":
            if len(argv) != 2:
                raise ValueError("dump-all requires one parameter")
            dumpLogFile = argv[1] + ".log.json"
            dumpSnapshotFile = argv[1] + ".snapshot.json"
            if os.path.isfile(dumpLogFile) or os.path.isfile(dumpSnapshotFile):
                yesNo = self.app.userStringLine(label = "Some file already exist. Continue?", prompt = "[Y/n] ")
                if not (yesNo == "Y" or yesNo == "y"):
                    return
            self.dumpAll(dumpLogFile, dumpSnapshotFile)

        elif cmd == "time":
            self.displayMsg("It is now {}".format(datetime.datetime.now().time()), 0)
        elif cmd == "help":
            self.displayMsg("Nobody can help you now - except maybe README.md")
        elif cmd == "error":
            raise Exception("This is a long error message with \n line breaks")
        else:
            super().execCmd(argv)

    def input(self, c):
        if c == ord('\t'):
            self.split.toggleFocus()
        elif c == curses.KEY_F1:
            self.switch.select(0)
        elif c == curses.KEY_F2:
            self.switch.select(1)
        else:
            super().input(c)

    def layout(self):
        super().layout()
        self.split.layout(self.rect)


class ArangoAgencyLogProvider:

    def __init__(self, logfile, snapshotFile):
        self.logfile = logfile
        self.snapshotFile = snapshotFile
        self.refresh()

    def log(self):
        raise NotImplementedError

    def snapshot(self):
        raise NotImplementedError

    def refresh(self):
        raise NotImplementedError

class ArangoAgencyLogFileProvider:

    def __init__(self, logfile, snapshotFile):
        self.logfile = logfile
        self.snapshotFile = snapshotFile
        self.refresh()

    def log(self):
        return self._log

    def snapshot(self):
        return self._snapshot

    def refresh(self):
        log = None
        snapshot = None

        with open(self.logfile) as f:
            print("Loading log from `{}`".format(self.logfile))
            log = json.load(f)
            if isinstance(log, dict):
                if "result" in log:
                    print("Interpreting object as query result, using `result` attribute")
                    log = log["result"]
                elif "log" in log:
                    print("Interpreting object as agency-dump result, using `log` and `compaction` attribute")
                    snapshot = log.get("compaction")
                    log = log.get("log")
                else:
                    raise Exception("Log file: can not interpret object")

            if not isinstance(log, list):
                raise Exception("Expected log to be a list")
            log.sort(key = lambda x : x["_key"])

        if self.snapshotFile:
            if snapshot == None:
                with open(self.snapshotFile) as f:
                    print("Loading snapshot from `{}`".format(self.snapshotFile))
                    snapshot = json.load(f)
            else:
                print("Ignoring snapshot file")

        self._log = log
        self._snapshot = snapshot

class ArangoAgencyLogEndpointProvider:

    def __init__(self, client):
        self.client = client
        self.refresh()

    def log(self):
        return self._log

    def snapshot(self):
        return self._snapshot

    def refresh(self):
        role = self.client.serverRole()
        print("Server has role {}".format(role))

        if role == "COORDINATOR":
            print("Receiving agency dump")
            dump = self.client.agencyDump()
            if not isinstance(dump, dict):
                raise Exception("Expected object in agency-dump")
            self._log = dump.get("log")
            self._snapshot = dump.get("compaction")
        elif role == "AGENT":
            print("Querying for log")
            self._log = list(self.client.query("for l in log sort l._key return l"))
            print("Querying for snapshot")
            snapshots = self.client.query("for s in compact filter s._key >= @first sort s._key limit 1 return s", first = self._log[0]["_key"])
            self._snapshot = next(iter(snapshots), None)

class ColorPairs:
    CP_RED_WHITE = 1

class ColorFormat:
    CF_ERROR = None


def main(stdscr, provider):
    stdscr.clear()
    curses.curs_set(0)

    # initialise some colors
    curses.init_pair(ColorPairs.CP_RED_WHITE, curses.COLOR_RED, curses.COLOR_BLACK)

    # Init color formats
    ColorFormat.CF_ERROR = curses.A_BOLD | curses.color_pair(ColorPairs.CP_RED_WHITE);


    app = ArangoAgencyAnalyserApp(stdscr, provider)
    app.run()

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("log", help="log file or endpoint", type=str)
        parser.add_argument('add', nargs='?', type=str, help="optional, snapshot file or jwt")
        parser.add_argument("-k", "--noverify", help="don't verify certs", action="store_true")
        args = parser.parse_args()

        o = urlparse(args.log)

        if not o.netloc:
            provider = ArangoAgencyLogFileProvider(o.path, args.add)
        else:
            host = o.netloc
            jwt = args.add

            if o.scheme in ["http", "tcp", ""]:
                conn = HTTPConnection(host)
                print("Connecting to {}".format(host))
                conn.connect()
            elif o.scheme in ["https", "ssl"]:
                options = dict()
                if args.noverify:
                    options["context"] = ssl._create_unverified_context()

                conn = HTTPSConnection(host, **options)
                print("Connecting to {}".format(host))
                conn.connect()
            else:
                raise Exception("Unknown scheme: {}".format(o.scheme))

            client = ArangoClient(conn, jwt)
            provider = ArangoAgencyLogEndpointProvider(client)

        os.putenv("ESCDELAY", "0")  # Ugly hack to enabled escape key for direct use
        curses.wrapper(main, provider)
    except Exception as e:
        raise e
