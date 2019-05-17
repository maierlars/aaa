
from agency import AgencyStore
from controls import *
import jsontools

# Use enter to go into selection mode
# Use escape to exit selection mode
#   In selection mode one can select keys and values of objects and arrays
#   Collaps and Expand objects and arrays
#   Each line should store its path
#       and its actual line number within the json document
#
#   The line class has to keep track of the following data:
#       lineno      - line number
#       data        - the actual string data
#       path        - path of that element
#       span        - length in lines of that element, negative if closing tag
#       selectables - tuples of indexes of selectables, first is key if object, empty if nonselectable line
#       attributes  - triples of (start, end, attr) defining style, overlapping syles are or'ed
#       parent      - index of parent line
#       collapsed   - true if collapsed
#
# Additionally allow search with next and prev semantics and highlight matches
# Additionally allow selection of subtrees of the json using globs
#   Tab completion
#
# The "selected line"
#   is either the line on top or it is the line the
#   cursor is in, when mode is selection.
#
# The path line displays the path or the selected line
#


def rangeSubset(begin, end, first, last):
    return (
        begin + first if first >= 0 else end + first,
        begin + last if last >= 0 else end + last,
    )


class AnnotateJson:
    def __init__(self, json):
        self.json           = json
        self.annotations    = []
        self.selectables    = []


class JsonLine:
    def __init__(self, lineno, path):
        self.lineno = lineno
        self.path = path.copy()
        self.string = ""
        self.span = 1
        self.selectables = []
        self.attributes = []
        self.collapsed = False
        self.collapsable = False
        self.parent = None

    def __str__(self):
        prefix = "" if self.prefix == None else self.prefix
        path = "/".join((x[0] for x in self.path))
        string = prefix.ljust(len(self.path) * 4) + self.string
        return string.ljust(100) + "// " + path


    # def addString(self, text, attr, selection = True):
    #     start = len(self.string)
    #     end = start + len(text)
    #     self.string += text

    #     if not attr == None:
    #         self.attributes.append((start, end, attr))

    #     if not selection == None:
    #         if selection is True:
    #             self.selectables.append((start, end))
    #         elif isinstance(selection, tuple):
    #             self.selectables.append(rangeSubset(start, end, *selection))
    #         else:
    #             raise TypeError()


        # class PrintState:
        #     def __init__(self):
        #         self.lineno = 0
        #         self.indent = 0
        #         self.path = []
        #         self.lines = []

        #     def newline(self, sibling = None):
        #         self.lineno += 1
        #         line = JsonView.JsonLine(self.lineno, self.path)
        #         if not sibling == None:
        #             line.prefix = sibling.prefix
        #         self.lines.append(line)
        #         return line

        #     def push(self, level, parent):
        #         self.path.append((level, parent))

        #     def pop(self):
        #         self.path.pop()

        #     def lastLine(self):
        #         return self.lines[-1]

        # def printString(string, line, attr):
        #     line.addString("\"{}\"".format(string), attr, (1, -1))

        # def printPrimitive(value, line, state):
        #     if isinstance(value, str):
        #         printString(value, line, 0)
        #     elif value is True:
        #         line.addString("true", 0)
        #     elif value is False:
        #         line.addString("false", 0)
        #     elif value is None:
        #         line.addString("null", 0)
        #     elif isinstance(value, (int, float)):
        #         line.addString(str(value), 0)

        # def printObjectKeyValue(key, value, line, state):
        #     state.push(key, line)
        #     subline = state.newline()
        #     printString(ḱey, subline, 0)
        #     subline.text += ": "
        #     printValue(value, path, subline)
        #     state.pop()

        # def printObject(obj, line, state):
        #     line.addString("{", 0)
        #     line.collapsable = True
        #     start = line.lineno
        #     first = False
        #     print(obj)
        #     for key, value in obj.items():
        #         if not first:
        #             state.lastLine().string += ","
        #         first = False



        #     closer = state.newline()
        #     closer.addString("}", 0)
        #     line.span = closer.lineno - start

        # def printArrayValue(value, tailingComma, line, state, prefix = None):
        #     if isinstance(value, jsondiff.DiffResult):
        #         if value.hasAdded():
        #             printArrayValue(value.addedValue(), tailingComma, line, state, "+")
        #         if value.hasRemoved():
        #             printArrayValue(value.removedValue(), tailingComma, line, state, "-")
        #     else:
        #         subline = state.newline(line)
        #         subline.prefix = prefix
        #         printValue(value, state, subline)

        #         if tailingComma:
        #             state.lastLine().string += ","

        # def printArray(arr, line, state):
        #     line.addString("[", 0)
        #     line.collapsable = True
        #     start = line.lineno
        #     first = False

        #     for idx, value in enumerate(arr):
        #         state.push(str(idx), line)
        #         printArrayValue(value, idx < len(arr) - 1, line, state)
        #         state.pop()

        #     closer = state.newline()
        #     closer.addString("]", 0)
        #     line.span = closer.lineno - start

        # def printAnnotation(ann, line, state):
        #     # Here we want to either generate n new lines
        #     # at the current indention level
        #     # or behind the top most generated line if the annotation
        #     # is inlined.



        # def printValue(json, state, line):
        #     if isinstance(json, dict):
        #         printObject(json, line, state)
        #     elif isinstance(json, list):
        #         printArray(json, line, state)
        #     elif isinstance(json, jsontools.DiffResult):
        #         printDiffResult(json, line, state)
        #     elif isinstance(json, AnnotatedLine):
        #         printAnnotation(json, line, state)
        #     else:
        #         printPrimitive(json, line, state)

        # def printDiffResult(value, line, state):
        #     if value.hasAdded():
        #         line = state.newline()
        #         line.prefix = "+"
        #         printValue(value.addedValue(), state, line)
        #     if value.hasRemoved():
        #         line = state.newline()
        #         line.prefix = "-"
        #         printValue(value.addedValue(), state, line)

        # state = PrintState()
        # printValue(json, state, state.newline())
        # for line in state.lines:
        #     print(str(line))


class JsonLineParser:

    # Returns a list of json lines representing the
    # given input.
    def parse(json):

        class State:
            def __init__(self):
                self.lines = []

        def parseValue(json, state):
            if isinstance(json, dict):
                parseObject(json, state)
            else:
                # bad value
                pass

        state = State()
        parseValue(json, state)
        return state.lines




class JsonView(Control):

    def __init__(self, app, rect):
        super().__init__(app, rect)
        self.lines = None
        self.idx = None
        self.top = None
        self.selectionMode = False

    def update(self):
        # Normalize the input
        # Calculate new top line depending on mode
        # Dump as many lines as possible

        if self.lines == None:
            # nothing to display
            return

    def input(self, c):
        return False

    def set(self, jsonlines):
        self.lines = None


def pdiff(a, b):
    view = JsonView(None, None)
    view.set(jsontools.diff(a, b))


def annotateLogEntry(log):

    keys = ["_key", "_rev", "term", "clientId", "timestamp", "requests"]

    result = dict()
    for key in keys:
        if not key in log:
            continue
        value = log[key]

        if key == "clientId":
            # try to extract server information
            off = value.find(':')
            if off != -1:
                result[key] = AnnotateJson(value).annotatAbove("send by {}".format(key[off:]))
        elif key == "requests":
            # parse all requests and extract information about the paths
            # finally generate selectables and annotations
            for path, op in value:
                pathSplit = AgencyStore.parsePath(path)




        else:
            # otherwise just copy the value
            result[key] = log[key]

    return result

