#!/usr/bin/env python3

import sys
import os
import json
import datetime, time
import re
import copy
from time import sleep
import argparse
from urllib.parse import urlparse
import bisect
import threading
import queue

import agency
import trie
from controls import *
from client import *

ARANGO_LOG_ZERO = "00000000000000000000"


class HighlightCommand:
    def __init__(self, color, clear, save, regex, expr, only_path):
        self.color = color
        self.clear = clear
        self.save = save
        self.regex = regex
        self.expr = expr
        self.only_path = only_path


class AgencyLogList(Control):
    FILTER_NONE = 0
    FILTER_GREP = 1
    FILTER_REGEX = 2

    def __init__(self, app, rect, args):
        super().__init__(app, rect)
        self.app = app
        self.top = 0
        self.highlight = 0
        self.filterStr = None
        # list contains all displayed log indexes
        self.list = None
        self.filterType = AgencyLogList.FILTER_NONE
        self.filterHistory = []
        self.last_predicate = None
        self.formatString = "[{timestamp}|{term}] {_key} {urls}"
        self.marked = dict()
        self.follow = args.follow
        self.highlight_predicate = dict()
        self.highlight_string = None
        self.highlight_history = []

    def title(self):
        return "Agency Log"

    def serialize(self):
        return {
            'top': self.top,
            'highlight': self.highlight,
            'filterStr': self.filterStr,
            'filterType': self.filterType,
            'filterHistory': self.filterHistory,
            'formatString': self.formatString,
            'marked': copy.deepcopy(self.marked)
        }

    def restore(self, state):
        self.top = state['top']
        self.highlight = state['highlight']
        self.filterStr = state['filterStr']
        self.filterType = state['filterType']
        self.filterHistory = state['filterHistory']
        self.formatString = state['formatString']
        self.marked = copy.deepcopy(state['marked'])
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
        if self.list is not None:
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

        # update highlight if follow
        if self.follow:
            self.highlight = maxPos

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

                is_selected = idx == self.getSelectedIndex()

                text = " ".join(x for x in ent["request"])
                prefix = ">" if is_selected else " "
                msg = prefix + self.formatString.format(**ent, urls=text, i=idx).ljust(self.rect.width)

                attr = 0
                if is_selected:
                    attr |= curses.A_STANDOUT | curses.A_UNDERLINE
                add = self.__get_line_highlight(idx)
                if add is not None:
                    attr |= add

                if not self.app.snapshot is None and not self.app.log[0]["_key"] == ARANGO_LOG_ZERO:
                    if ent["_key"] < self.app.snapshot["_key"]:
                        attr |= curses.A_DIM

                self.app.stdscr.addnstr(y, x, msg.ljust(maxlen), maxlen, attr)
            elif i == 0:
                self.app.stdscr.addnstr(y, x, "Nothing to display".ljust(maxlen), maxlen,
                                        curses.A_BOLD | ColorFormat.CF_ERROR)
            else:
                self.app.stdscr.addnstr(y, x, "".ljust(maxlen), maxlen, 0)

    def __get_line_highlight(self, idx):
        if idx in self.marked:
            return ColorFormat.MARKING_ATTR_LIST[self.marked[idx]]

        ent_string = json.dumps(self.app.log[idx])
        ent_paths = " ".join(x for x in self.app.log[idx]["request"])

        colors = {
            "r": ColorFormat.MARKING_ATTR_LIST[0],
            "g": ColorFormat.MARKING_ATTR_LIST[1],
            "b": ColorFormat.MARKING_ATTR_LIST[2],
            "y": ColorFormat.MARKING_ATTR_LIST[3],
            "c": ColorFormat.MARKING_ATTR_LIST[4],
            "m": ColorFormat.MARKING_ATTR_LIST[5],
        }

        for color in colors:
            # find the first color that matches
            if color not in self.highlight_predicate:
                continue
            pred = self.highlight_predicate[color]
            if pred(ent_string, ent_paths):
                return colors[color]

        return None

    def filter(self, predicate):
        # Make sure that the highlighted entry is the previously selected
        # entry or the closest entry above that one.
        lastHighlighted = self.__getIndex(self.highlight)
        if lastHighlighted == None:
            lastHighlighted = 0

        self.list = []
        self.highlight = 0
        self.last_predicate = predicate
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
        if self.highlight is None:
            self.highlight = 0
        self.list = None
        self.filterStr = None
        self.filterType = AgencyLogList.FILTER_NONE
        self.last_predicate = None

    def filter_new_entries(self, new_entries):
        if self.filterType == AgencyLogList.FILTER_NONE:
            return
        self.filter(self.last_predicate)

    def highlight_entries(self, string):
        color = "r"
        assert len(string) > 0
        if string[0] in ["r", "g", "b", "y", "c", "m"]:
            if len(string) == 1:
                color = string[0]
                string = None
            if len(string) > 2 and string[1] == " ":
                color = string[0]
                string = string[2:]

        cmd = HighlightCommand(color, False, False, False, string, False)
        self.execute_highlight_command(cmd)

    def input(self, c):
        if c == curses.KEY_UP:
            self.follow = False
            self.highlight -= 1
        elif c == curses.KEY_DOWN:
            self.follow = False
            self.highlight += 1
        elif c == curses.KEY_NPAGE:
            self.follow = False
            self.highlight += self.rect.height
            self.top += self.rect.height
        elif c == curses.KEY_PPAGE:
            self.follow = False
            self.highlight -= self.rect.height
            self.top -= self.rect.height
        elif c == curses.KEY_END:
            self.follow = False
            self.highlight = self.__getListLen() - 1
        elif c == curses.KEY_HOME:
            self.follow = False
            self.highlight = 0
        elif False:
            regexStr = self.app.userStringLine(label="Regular Search Expr", default=self.filterStr, prompt="> ",
                                               history=self.filterHistory)
            if not regexStr == None:
                if regexStr:
                    self.filterHistory.append(regexStr)
                self.regexp(regexStr)
        elif c == ord('g') or c == ord('f'):
            self.run_filter_prompt()
        elif c == ord('r'):
            yesNo = self.app.userStringLine(label="Reset all filters", prompt="[Y/n] ")
            if yesNo == "Y" or yesNo == "y" or yesNo == "":
                self.reset()
        elif c == ord('R'):
            self.reset()
        elif c == ord('m'):
            self.toggleMarkLine()
        elif c == ord('M'):
            self.deleteMarkLine()
        elif c == ord('h'):
            string = self.app.userStringLine(label="Highlight Search Expr", prompt="> ", default=self.highlight_string,
                                             history=self.highlight_history)
            if string is not None and len(string) > 0:
                self.highlight_entries(string)
        elif c == ord('H'):
            yesNo = self.app.userStringLine(label="Reset all highlights", prompt="[Y/n] ")
            if yesNo == "Y" or yesNo == "y" or yesNo == "":
                self.highlight_predicate = dict()

    def run_filter_prompt(self, string=None):
        if string is None:
            string = self.app.userStringLine(label="Global Search Expr", default=self.filterStr, prompt="> ",
                                             history=self.filterHistory)
        if not string == None:
            if string:
                self.filterHistory.append(string)
            self.grep(string)

    # Returns the index of the selected log entry.
    #   This value is always with respect to the app.log array.
    #   You do not need to worry about filtering
    def getSelectedIndex(self):
        if not self.list == None:
            if self.highlight < len(self.list):
                return self.list[self.highlight]
            return None
        return self.highlight

    def toggleMarkLine(self):
        idx = self.getSelectedIndex()
        if idx in self.marked:
            self.marked[idx] += 1
            if self.marked[idx] == len(ColorFormat.MARKING_ATTR_LIST):
                del self.marked[idx]
        else:
            self.marked[idx] = 0

    def deleteMarkLine(self):
        idx = self.getSelectedIndex()
        if idx in self.marked:
            del self.marked[idx]

    def selectClosest(self, idx):
        if not self.list == None:
            for i in self.list:
                if i <= idx:
                    self.highlight = i
                    self.top = i
        else:
            self.highlight = idx
            self.top = idx

    def goto(self, idx):
        # get global index of first log entry
        startgidx = int(self.app.log[0]["_key"])
        self.selectClosest(idx - startgidx)

    @staticmethod
    def parse_highlight_command(cmd, argv):
        try:
            cmd = cmd.lower()
            assert len(cmd) >= 2
            assert cmd[0] == "h"
            idx = 1

            # parse color
            color = None
            if cmd[idx] in ["r", "g", "b", "y", "c", "m"]:
                color = cmd[idx]
                idx += 1

            # parse clear
            clear = False
            if idx < len(cmd) and cmd[idx] == "c":
                clear = True
                idx += 1

            # parse save
            save = False
            if idx < len(cmd) and cmd[idx] == "s":
                save = True
                idx += 1

            # parse regex
            regex = False
            if idx < len(cmd) and cmd[idx] == "r":
                regex = True
                idx += 1
            # only consider path names
            only_paths = False
            if idx < len(cmd) and cmd[idx] == "p":
                only_paths = True
                idx += 1

            if idx != len(cmd):
                raise RuntimeError("to many chars")

            expr = None
            if len(argv) > 0:
                expr = argv[0]

            return HighlightCommand(color, clear, save, regex, expr, only_paths)

        except Exception as e:
            raise RuntimeError(
                "Invalid highlight command, expected something that matches h[r|g|b|y|c|m]c?s?r?p? - " + str(e))

    def execute_highlight_command(self, cmd: HighlightCommand):
        if cmd.save or cmd.clear:
            raise RuntimeException("save and clear not yet implemented")

        if cmd.expr is None:
            # delete that highlight
            del self.highlight_predicate[cmd.color]
        else:
            # update
            if cmd.regex:
                pattern = re.compile(cmd.expr)
                find_predicate = lambda x: pattern.search(x) is not None
            else:
                find_predicate = lambda x: cmd.expr in x

            if cmd.only_path:
                select_predicate = lambda json, paths: paths
            else:
                select_predicate = lambda json, paths: json

            self.highlight_predicate[cmd.color] = lambda json, paths: find_predicate(select_predicate(json, paths))


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

        if not self.idx == self.lastIdx:
            if self.idx == None:
                self.jsonLines(None)
            elif not self.idx == None and self.idx < len(self.app.log):
                entry = self.app.log[self.idx]

                fields = ["_key", "_rev", "term", "clientId", "timestamp", "request"]

                json = dict()
                for name in fields:
                    if name in entry:
                        json[name] = entry[name]

                self.head = None  # entry['_key']

                loglist = self.app.list
                if loglist.filterType == AgencyLogList.FILTER_GREP:
                    self.findStr = loglist.filterStr
                else:
                    self.findStr = None
                self.jsonLines(json)

        self.lastIdx = self.idx
        super().update()

    def set(self, idx):
        self.idx = idx


class StoreCache:

    def __init__(self, maxSize):
        self.maxSize = maxSize
        self.cache = dict()
        self.list = list()
        self.indexes = list()

    def refresh(self, idx):
        try:
            self.list.remove(idx)
        except:
            pass
        self.list.append(idx)

    def get(self, idx):
        if idx in self.cache:
            self.refresh(idx)
            return self.cache[idx]
        return None

    def has(self, idx):
        return idx in self.cache

    def closest(self, idx):
        i = bisect_left(self.indexes, idx)
        if i == 0:
            return None
        return self.indexes[i - 1]

    def set(self, idx, store):
        self.refresh(idx)
        if len(self.list) > self.maxSize:
            oldIdx = self.list.pop(0)
            try:
                self.indexes.remove(oldIdx)
            except:
                pass
            del self.cache[oldIdx]
        self.cache[idx] = store
        bisect.insort_left(self.indexes, idx)


class StoreUpdateResult:
    OK = 0
    UPDATE_JSON = 1
    NO_SNAPSHOT = 2
    NOT_COVERED = 3


class StoreProvider:
    def __init__(self, app, rect):
        self.app = app
        self.store = None
        self.cache = StoreCache(512)
        self.lastIdx = None
        self.lastWasCopy = False
        self.rect = rect

    def updateIndex(self, idx):
        updateJson = True
        if self.lastIdx != idx:
            updateJson = True
            # if the id of the first log entry is ARANGO_LOG_ZERO,
            # generate the agency from empty store
            # otherwise check if the log entry is after (>=) the
            log = self.app.log
            if log == None or len(log) == 0:
                return StoreUpdateResult.NO_SNAPSHOT
            snapshot = self.app.snapshot

            startidx = None
            snapshotRequired = True

            if log[0]["_key"] == ARANGO_LOG_ZERO:
                snapshotRequired = False

            # early out for cases where we can not produce a store
            if snapshotRequired:
                if snapshot == None:
                    return StoreUpdateResult.NO_SNAPSHOT
                elif log[idx]["_key"] < snapshot["_key"]:
                    return StoreUpdateResult.NOT_COVERED

            # first check cache
            cache = self.cache.get(idx)
            if not cache == None:
                self.lastWasCopy = False
                self.store = cache
            else:
                # check if we can use last index
                startidx = self.lastIdx + 1 if not self.lastIdx == None else None
                doCopyLastSnapshot = False
                if self.lastIdx == None or self.store == None or idx < self.lastIdx:
                    startidx = self.app.firstValidLogIdx
                    if snapshotRequired:
                        doCopyLastSnapshot = True
                    else:
                        self.store = agency.AgencyStore()
                        startidx = 0
                    self.lastWasCopy = True

                # lets ask cache
                cache = self.cache.closest(idx)
                if not cache == None and not startidx == None:
                    if cache > startidx:
                        startidx = cache + 1
                        self.app.showProgress(0.0, "Copy index {} from cache".format(cache), rect=self.rect)
                        self.store = agency.AgencyStore.copyFrom(self.cache.get(cache))
                        self.lastWasCopy = True
                        doCopyLastSnapshot = False

                if doCopyLastSnapshot:
                    self.app.showProgress(0.0, "Copy from snapshot", rect=self.rect)
                    self.store = agency.AgencyStore(snapshot["readDB"][0])
                elif not self.lastWasCopy:
                    self.store = agency.AgencyStore.copyFrom(self.store)

                lastProgress = time.process_time()

                for i in range(startidx, idx + 1):
                    now = time.process_time()
                    # if log[idx]["_key"] >= snapshot["_key"]:
                    try:
                        self.store.applyLog(self.app.log[i])
                    except Exception as e:
                        raise Exception("In log entry {idx}: {text}".format(idx=i, text=str(e)))
                    storeIntermediate = i % 5000 == 0 and not self.cache.has(i)

                    if not storeIntermediate:
                        didx = idx - i
                        if didx < 500:
                            storeIntermediate = didx % 200 == 0
                        elif didx < 2500:
                            storeIntermediate = didx % 1000 == 0

                    if storeIntermediate:
                        self.app.showProgress((i - startidx) / (idx + 1 - startidx),
                                              "Generating store {}/{} - writing to cache".format(i, idx + 1),
                                              rect=self.rect)
                        self.cache.set(i, agency.AgencyStore.copyFrom(self.store))
                    elif now - lastProgress > 0.1:
                        self.app.showProgress((i - startidx) / (idx + 1 - startidx),
                                              "Generating store {}/{}".format(i, idx + 1), rect=self.rect)
                        lastProgress = now

                self.app.showProgress(1.0, "Generating store done - writing to cache", rect=self.rect)
                self.cache.set(idx, agency.AgencyStore.copyFrom(self.store))
                self.app.showProgress(1.0, "Dumping json", rect=self.rect)

        self.lastIdx = idx
        return StoreUpdateResult.UPDATE_JSON if updateJson else \
            StoreUpdateResult.OK

    def get(self, path):
        return self.store.get(path)

    def _ref(self, path):
        return self.store._ref(path)

    def has_store(self):
        return self.store is not None


class AgencyStoreView(LineView):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.store = app.storeProvider
        self.path = []
        self.pathHistory = []
        self.annotations = dict()
        self.annotationCache = StoreCache(64)
        self.annotationsTrie = None
        self.annotations_format = {
            "server": "{ShortName}, {Endpoint}, {Status}",
            "collection": "Collection `{database}/{name}`",
            "shard": "Shard of `{database}/{name}`"
        }

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
        self.store.rect = rect
        super().layout(rect)

    def updateStore(self, updateJson=False):
        idx = self.app.list.getSelectedIndex()
        if idx == None:
            return
        result = self.store.updateIndex(idx)
        if result == StoreUpdateResult.NO_SNAPSHOT:
            self.head = None
            self.lines = [(ColorFormat.CF_ERROR, "No snapshot available")]
            return
        elif result == StoreUpdateResult.NOT_COVERED:
            self.head = None
            self.lines = [(ColorFormat.CF_ERROR, "Can not replicate agency state. Not covered by snapshot.")]
            return
        elif result == StoreUpdateResult.UPDATE_JSON:
            updateJson = True
        else:
            assert result == StoreUpdateResult.OK

        if updateJson:
            self.load_annotations()
            self.jsonLines(self.store._ref(self.path))

    def update(self):
        self.head = "/" + "/".join(self.path)
        self.updateStore()
        super().update()

    def update_format_string(self, what):
        if what not in self.annotations_format:
            raise ValueError("Unknown format topic `{}`".format(what))
        new_str = self.app.userStringLine(label="Format string for {}".format(what),
                                          default=self.annotations_format[what])
        if new_str is not None:
            self.annotations_format[what] = new_str

    def load_annotations(self, flush=False):
        def format_user_string(format_str, kvs):
            try:
                return format_str.format(**kvs)
            except Exception as ex:
                return "<bad format string: {}>".format(repr(ex))

        idx = self.app.list.getSelectedIndex()
        if idx is None:
            return

        if not flush and self.annotationCache.has(idx):
            self.annotations = self.annotationCache.get(idx)
            return

        new_annotations = dict()
        all_servers = self.store.get(["arango", "Supervision", "Health"])
        if all_servers is not None:
            for serverId, data in all_servers.items():
                new_annotations[serverId] = format_user_string(self.annotations_format["server"], data)
        collections = self.store._ref(["arango", "Plan", "Collections"])
        if collections is not None:
            for dbname, database_collections in collections.items():
                for collection_id, data in database_collections.items():
                    format_dict = {"database": dbname, **data}
                    new_annotations[collection_id] = format_user_string(self.annotations_format["collection"],
                                                                        format_dict)
                    for shardId, servers in data["shards"].items():
                        shard_format_dict = {**format_dict, "servers": servers, "shardId": shardId}
                        new_annotations[shardId] = format_user_string(self.annotations_format["shard"],
                                                                      shard_format_dict)

        self.annotations = new_annotations
        self.annotationsTrie = trie.Trie(['"{}"'.format(x) for x in new_annotations.keys()])
        self.annotationCache.set(idx, new_annotations)

    def getLineAnnotation(self, line):
        if not self.store.has_store():
            return None

        annotation = []
        for w in self.annotationsTrie.find_all(line):
            annotation.append(self.annotations[w[1:-1]])

        if len(annotation) == 0:
            return None
        return "; ".join(annotation)

    def input(self, c):
        if c == ord('p'):
            pathstr = self.app.userStringLine(prompt="> ", label="Agency Path:", default=self.head,
                                              complete=self.completePath, history=self.pathHistory)
            self.path = agency.AgencyStore.parsePath(pathstr)
            self.pathHistory.append(pathstr)
            self.updateStore(updateJson=True)
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


class AgencyDiffView(PureLineView):
    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.store = app.storeProvider

    def layout(self, rect):
        self.store.rect = rect
        super().layout(rect)

    def title(self):
        return "Agency Store Diff"

    def getStoreRef(self, idx):
        result = self.store.updateIndex(idx)
        if result == StoreUpdateResult.NO_SNAPSHOT:
            self.head = None
            self.lines = [(ColorFormat.CF_ERROR, "No snapshot available")]
            return None
        elif result == StoreUpdateResult.NOT_COVERED:
            self.head = None
            self.lines = [(ColorFormat.CF_ERROR, "Can not replicate agency state. Not covered by snapshot.")]
            return None
        else:
            return self.store.store

    def update(self):

        idx = self.app.list.getSelectedIndex()
        if idx == None or idx == 0:
            return

        oldStore = self.getStoreRef(idx - 1)
        newStore = self.getStoreRef(idx)

        if oldStore is None or newStore is None:
            return

        entry = self.app.log[idx]
        lines = []
        for path in entry["request"]:
            lines.append([(curses.A_BOLD, path)])
            parsedPath = agency.AgencyStore.parsePath(path)
            oldLines = AgencyDiffView.split_json(oldStore._ref(parsedPath))
            newLines = AgencyDiffView.split_json(newStore._ref(parsedPath))
            diffLines = self.computeDiff(oldLines, newLines)
            lines.extend(diffLines)
        self.lines = lines
        super().update()

    @staticmethod
    def computeDiff(old, new):
        def estimate(x, y):
            return 0  # abs(len(old)-x+(len(new)-y))

        found = set()
        cred = ColorPairs.getPair(curses.COLOR_RED, curses.COLOR_BLACK)
        cgreen = ColorPairs.getPair(curses.COLOR_GREEN, curses.COLOR_BLACK)
        try:
            queue = [(0, 0, 0, estimate(0, 0), [])]
            i = 0
            while i < 300:
                # i += 1
                queue.sort(key=lambda x: (x[2] + x[3], -x[0]))
                x, y, cost, est, path = queue.pop(0)
                if (x, y) in found:
                    continue
                found.add((x, y))
                # print(x, y, cost + est)
                if x == len(old) and y == len(new):
                    return path
                if x != len(old) and y != len(new) and old[x] == new[y]:
                    queue.append((x + 1, y + 1, cost, estimate(x + 1, y + 1), path + [" " + old[x]]))
                else:
                    if x < len(old):
                        new_est = estimate(x + 1, y)
                        queue.append((x + 1, y, cost + 1, new_est, path + [[(cred, "-" + old[x])]]))
                    if y < len(new):
                        new_est = estimate(x, y + 1)
                        queue.append((x, y + 1, cost + 1, new_est, path + [[(cgreen, "+" + new[y])]]))

            raise RuntimeError(f"diff failed with {old, new=}")

        except Exception as e:
            raise RuntimeError(f"diff failed with {old, new=}")

    @staticmethod
    def split_json(value):
        return json.dumps(value, indent=4, separators=(',', ': '), sort_keys=True).splitlines()


class NewLogEntriesEvent:
    def __init__(self, log):
        self.log = log


class ExceptionInNetworkThread:
    def __init__(self, msg):
        self.msg = msg


class ArangoAgencyAnalyserApp(App):
    def __init__(self, stdscr, provider, args):
        super().__init__(stdscr)
        self.log = None
        self.snapshot = None
        self.firstValidLogIdx = None
        self.args = args

        self.storeProvider = StoreProvider(self, Rect.zero())
        self.list = AgencyLogList(self, Rect.zero(), args)
        self.view = AgencyStoreView(self, Rect.zero())
        self.diffView = AgencyDiffView(self, Rect.zero())
        self.logView = AgencyLogView(self, Rect.zero())
        self.switch = LayoutSwitch(Rect.zero(), [self.logView, self.view, self.diffView])

        self.split = LayoutColumns(self, self.rect, [self.list, self.switch], [4, 6])
        self.focus = self.split

        self.provider = provider
        self.refresh(updateSelection=True, refreshProvider=False)

        if args.execute:
            for cmd in args.execute:
                self.execCmd(cmd.split())

    def serialize(self):
        return {
            'split': self.split.serialize(),
        }

    def restore(self, state):
        self.split.restore(state['split'])

    def refresh(self, updateSelection=False, refreshProvider=True):
        if refreshProvider:
            self.provider.refresh()
            self.clearWindow()
        self.log = self.provider.log()
        self.snapshot = self.provider.snapshot()
        self.firstValidLogIdx = None
        if self.args.live:
            self.provider.start_live_view(int(self.log[-1]['_key']), self)

        if not self.snapshot == None and not self.log[0]["_key"] == ARANGO_LOG_ZERO:
            for i, e in enumerate(self.log):
                if e["_key"] <= self.snapshot["_key"]:
                    self.firstValidLogIdx = i
                else:
                    break

            if updateSelection:
                self.list.selectClosest(self.firstValidLogIdx)

    def dumpJSON(self, filename):
        data = None
        if self.switch.idx == 0:
            data = self.log[self.logView.idx]
        elif self.switch.idx == 1:
            data = self.view.store._ref(self.view.path)

        with open(filename, "w") as f:
            json.dump(data, f)

    def dumpAll(self, logfile, snapshotfile):
        with open(logfile, "w") as f:
            json.dump(self.log, f)
        with open(snapshotfile, "w") as f:
            json.dump(self.snapshot, f)

    def update(self):
        self.split.update()
        super().update()

    def handleEvent(self, ev):
        if isinstance(ev, NewLogEntriesEvent):
            modified = []
            for e in ev.log:
                e2 = dict()
                e2['request'] = e['query']
                e2['term'] = '???'
                e2['_key'] = str(e['index'])
                e2['timestamp'] = '???'
                modified.append(e2)

            self.log.extend(modified)
            self.list.filter_new_entries(modified)
        elif isinstance(ev, ExceptionInNetworkThread):
            self.displayMsg("Network thread: " + ev.msg, curses.A_STANDOUT)
        else:
            super().handleEvent(ev)

    def execCmd(self, argv):
        cmd = argv[0].lower()

        if cmd == "quit" or cmd == "q":
            self.stop = True
        elif cmd in ["f", "follow"]:
            self.list.follow = True
        elif cmd == "debug":
            self.debug = True
        elif cmd == "goto":
            if len(argv) != 2:
                raise ValueError("Goto requires one parameter")
            self.list.goto(int(argv[1]))
        elif cmd == "r" or cmd == "refresh" or cmd == "ref":
            self.refresh()
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
                raise ValueError("View requires either `log`, `diff` or `store`")

            if argv[1] == "log":
                self.switch.select(0)
            elif argv[1] == "store":
                self.switch.select(1)
            elif argv[1] == "diff":
                self.switch.select(2)
            else:
                raise ValueError("Unkown view: {}".format(argv[1]))
        elif cmd == "dump-all":
            if len(argv) != 2:
                raise ValueError("dump-all requires one parameter")
            dumpLogFile = argv[1] + ".log.json"
            dumpSnapshotFile = argv[1] + ".snapshot.json"
            if os.path.isfile(dumpLogFile) or os.path.isfile(dumpSnapshotFile):
                yesNo = self.app.userStringLine(label="Some file already exist. Continue?", prompt="[Y/n] ")
                if not (yesNo == "Y" or yesNo == "y" or yesNo == ""):
                    return
            self.dumpAll(dumpLogFile, dumpSnapshotFile)

        elif cmd == "time":
            self.displayMsg("It is now {}".format(datetime.datetime.now().time()), 0)
        elif cmd == "help":
            self.displayMsg("Nobody can help you now - except maybe README.md")
        elif cmd == "error":
            raise Exception("This is a long error message with \n line breaks")
        elif cmd in ["f", "fmt", "format"]:
            if len(argv) != 2:
                raise ValueError("format <what> <format-string>")
            what = argv[1]
            self.view.update_format_string(what)
            self.view.load_annotations(flush=True)
            self.view.update()
        elif cmd == "filter":
            self.list.run_filter_prompt(argv[1])
        elif cmd[0] == "h":
            # highlight command
            cmd = AgencyLogList.parse_highlight_command(cmd, argv[1:])
            self.list.execute_highlight_command(cmd)
        else:
            super().execCmd(argv)

    def input(self, c):
        if c == ord('\t'):
            self.split.toggleFocus()
        elif c == curses.KEY_F1:
            self.switch.select(0)
        elif c == curses.KEY_F2:
            self.switch.select(1)
        elif c == curses.KEY_F3:
            self.switch.select(2)
        else:
            super().input(c)

    def layout(self):
        super().layout()
        self.split.layout(self.rect)


class ArangoAgencyLogFileProvider:

    def __init__(self, logfile, snapshotFile):
        self.logfile = logfile
        self.snapshotFile = snapshotFile
        self.refresh()

    def log(self):
        return self._log

    def snapshot(self):
        return self._snapshot

    def start_live_view(self, first_index, app):
        pass

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
            log.sort(key=lambda x: x["_key"])

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
        self.process = None
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
            snapshots = self.client.query("for s in compact filter s._key >= @first sort s._key limit 1 return s",
                                          first=self._log[0]["_key"])
            self._snapshot = next(iter(snapshots), None)

    def poll_entries(self, index, app):
        try:
            while True:
                resp = self.client.agentPoll(index + 1)
                log = resp['result']['log']
                if isinstance(log, list) and len(log) > 0:
                    app.queueEvent(NewLogEntriesEvent(log))
                    index = log[-1]['index']
        except Exception as e:
            app.queueEvent(ExceptionInNetworkThread(str(e)))

    def start_live_view(self, first_index, app):
        if self.process is not None:
            return

        role = self.client.serverRole()
        if role == "AGENT":
            self.process = threading.Thread(target=self.poll_entries, args=(first_index, app))
            self.process.start()

    def stop_live_view(self):
        pass


class ColorPairs:
    CACHE = dict()

    def getPair(fg, bg):
        if (fg, bg) in ColorPairs.CACHE:
            return ColorPairs.CACHE[(fg, bg)]
        newid = len(ColorPairs.CACHE) + 1
        curses.init_pair(newid, fg, bg)
        cpair = curses.color_pair(newid)
        ColorPairs.CACHE[(fg, bg)] = cpair
        return cpair

    CP_RED_WHITE = 1
    CP_WHITE_RED = 2


# 1:red, 2:green, 3:yellow, 4:blue, 5:magenta, 6:cyan

class ColorFormat:
    CF_ERROR = None

    MARKING_ATTR_LIST = None


def main(stdscr, provider, args):
    stdscr.clear()
    curses.curs_set(0)

    # Init color formats
    ColorFormat.CF_ERROR = curses.A_BOLD | ColorPairs.getPair(curses.COLOR_RED, curses.COLOR_BLACK);

    ColorFormat.MARKING_ATTR_LIST = [
        ColorPairs.getPair(curses.COLOR_WHITE, curses.COLOR_RED),
        ColorPairs.getPair(curses.COLOR_WHITE, curses.COLOR_GREEN),
        ColorPairs.getPair(curses.COLOR_BLACK, curses.COLOR_BLUE),
        ColorPairs.getPair(curses.COLOR_BLACK, curses.COLOR_YELLOW),
        ColorPairs.getPair(curses.COLOR_BLACK, curses.COLOR_CYAN),
        ColorPairs.getPair(curses.COLOR_BLACK, curses.COLOR_MAGENTA),
    ]

    app = ArangoAgencyAnalyserApp(stdscr, provider, args)
    app.run()


# A = ["0"]
# B = ["A", "B", "C", "D", "A", "B", "C", "D", "A", "B", "C", "D"]
# AgencyDiffView.computeDiff(A, B)
# quit()

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("log", help="log file or endpoint", type=str)
        parser.add_argument('add', nargs='?', type=str, help="optional, snapshot file or jwt")
        parser.add_argument("-k", "--noverify", help="don't verify certs", action="store_true")
        parser.add_argument("-u", "--userpass", help="use username and password instead of jwt", action="store_true")
        parser.add_argument("--live", help="automatically receive updates (experimental)", action="store_true")
        parser.add_argument("--follow", help="start with follow mode on", action="store_true")
        parser.add_argument('-e', '--execute', action='append', help="execute this command during startup")
        args = parser.parse_args()

        o = urlparse(args.log)

        if not o.netloc:
            provider = ArangoAgencyLogFileProvider(o.path, args.add)
        else:
            host = o.netloc
            authstr = args.add
            auth = None

            if not authstr is None:
                if not args.userpass:
                    # jwt string is of the form username:password
                    auth = ArangoJwtAuth(authstr)
                else:
                    # use the jwt string
                    auth = ArangoBasicAuth(authstr)

            if o.scheme in ["http", "tcp", ""]:
                conn = HTTPConnection(host)
            elif o.scheme in ["https", "ssl"]:
                options = dict()
                if args.noverify:
                    options["context"] = ssl._create_unverified_context()

                conn = HTTPSConnection(host, **options)
            else:
                raise Exception("Unknown scheme: {}".format(o.scheme))

            print("Connecting to {}".format(host))
            conn.connect()
            client = ArangoClient(conn, auth)
            provider = ArangoAgencyLogEndpointProvider(client)

        os.putenv("ESCDELAY", "0")  # Ugly hack to enabled escape key for direct use
        curses.wrapper(main, provider, args)
        os._exit(1)
    except Exception as e:
        raise e
