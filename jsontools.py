import heapq
from fnmatch import fnmatch

class DiffResult:
    ADDED = 0
    MODIFIED = 1
    REMOVED = 2

    def __init__(self, op, value):
        self.op = op
        self.value = value

    def added(value):
        return DiffResult(DiffResult.ADDED, value)

    def modified(old, new):
        return DiffResult(DiffResult.MODIFIED, (old, new))

    def removed(value):
        return DiffResult(DiffResult.REMOVED, value)

    def hasAdded(self):
        return self.op == DiffResult.ADDED or self.op == DiffResult.MODIFIED

    def addedValue(self):
        if self.op == DiffResult.ADDED:
            return self.value
        elif self.op == DiffResult.MODIFIED:
            return self.value[0]
        raise ValueError()

    def hasRemoved(self):
        return self.op == DiffResult.REMOVED or self.op == DiffResult.MODIFIED

    def removedValue(self):
        if self.op == DiffResult.REMOVED:
            return self.value
        elif self.op == DiffResult.MODIFIED:
            return self.value[1]
        raise ValueError()

    def __repr__(self):
        verb = ["ADDED", "MODIFIED", "REMOVED"][self.op]
        return "{} {}".format(verb, str(self.value))

# JsonDiff
# JsonDiff calculates the difference of two json documents
# The diffing algorithm is describe in the following text:
# Given a JSON Document, diff it according to the following rules:
#   If the document is a string/bool/null/int
#       compare the values for equality
#   If the dcouemtn is an object,
#       compare the sorted key spaces
#           compare values of equal keys
#           add/remove new/missing keys
#   If the document is an array,
#       find the longest common subsequence
#       treat objects and arrays as equal
#           and do a inner diff

def diff(a, b):
    OBJECT = 0
    ARRAY = 1
    STRING = 2
    BOOLEAN = 3
    NUMERICAL = 4
    NULL = 5

    def typeof(a):
        if isinstance(a, dict):
            return OBJECT
        elif isinstance(a, list):
            return ARRAY
        elif isinstance(a, str):
            return STRING
        elif a in [True, False]:
            return BOOLEAN
        elif a is None:
            return NULL
        elif isinstance(a, (int, float)):
            return NUMERICAL
        else:
            assert False

    def diffPrimitive(a, b):
        if a == b:
            return a
        return DiffResult.modified(a, b)

    def diffObjects(a, b):
        keys = sorted(set().union(a.keys(), b.keys()))
        result = dict()
        for key in keys:
            if key in a.keys():
                if key in b.keys():
                    result[key] = diff(a[key], b[key])
                else:
                    result[key] = DiffResult.removed(a[key])
            else:
                result[key] = DiffResult.added(b[key])
        return result

    def diffArrays(a, b):
        tx, ty = len(a)-1, len(b)-1
        # Compute the shortest path through the state grid
        heap = [(0, (-1, -1), [])]
        nodes = set()
        target = None

        while len(heap) > 0:
            node = heapq.heappop(heap)
            if node[1] in nodes:
                continue
            nodes.add(node[1])

            # expand right and bottom
            px, py = node[1]
            if py < ty:
                heapq.heappush(heap, (node[0] + 1, (px, py + 1), node[2] + ["+"]))
            if px < tx:
                heapq.heappush(heap, (node[0] + 1, (px + 1, py), node[2] + ["-"]))

            # Now check for diagonal
            if px < tx and py < ty:
                ap, bp = (a[px+1], b[py+1])
                apt, bpt = (typeof(ap), typeof(bp))
                if apt == bpt:
                    equal = False
                    if apt in [OBJECT, ARRAY]:
                        # assume equality
                        equal = True
                    else:
                        equal = ap == bp
                    if equal:
                        heapq.heappush(heap, (node[0], (px + 1, py + 1), node[2] + [None]))

            if node[1] == (tx, ty):
                target = node
                break # Found path

        result = []

        if not target == None:
            ai, bi = (0, 0)
            for l in target[2]:
                if l == "-":
                    result.append(DiffResult.removed(a[ai]))
                    ai += 1
                elif l == "+":
                    result.append(DiffResult.added(b[bi]))
                    bi += 1
                elif l == None:
                    result.append(diff(a[ai], b[bi]))
                    ai += 1
                    bi += 1
            return result
        return None

    atype = typeof(a)
    btype = typeof(b)

    if not atype == btype:
        # This is a change in type
        #   So everything has been modified
        return DiffResult.modified(a, b)

    # Otherwise they are the same type
    if atype == OBJECT:
        return diffObjects(a, b)
    elif atype == ARRAY:
        return diffArrays(a, b)
    elif atype in [STRING, BOOLEAN, NUMERICAL]:
        return diffPrimitive(a, b)
    elif atype == NULL:
        return a    # Both are null

def glob(glob, json):
    def selectValues(glob, json, path = []):
        if len(glob) == 0:
            yield (path, json)
        else:
            level = glob[0]
            iterate = None
            if isinstance(json, dict):
                iterate = json.items()
            elif isinstance(json, list):
                iterate = enumerate(json)

            if not iterate == None:
                for key, value in iterate:
                    if fnmatch(str(key), level):
                        yield from selectValues(glob[1:], value, path + [key])

    split = list(filter(None, glob.split('/')))
    yield from selectValues(split, json)
