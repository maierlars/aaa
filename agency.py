
import json
import copy
import dateutil.parser, datetime
import heapq

class AgencyStore:

    def __init__(self, store = {}, ttlt = []):
        self.store = copy.deepcopy(store)
        self.ttlt = copy.deepcopy(ttlt)

    def __str__(self):
        return json.dumps(self.store)

    def copyFrom(store):
        return AgencyStore(store.store, store.ttlt)

    def set(self, path, value):
        store = self.store
        for x in path[:-1]:
            if not x in store or not isinstance(store[x], dict):
                store[x] = {}
            store = store[x]
        store[path[-1]] = copy.deepcopy(value)

    def delete(self, path):
        store = self.store
        for x in path[:-1]:
            if not isinstance(store, dict) or not x in store:
                return
            store = store[x]
        store.pop(path[-1], None)

    def push(self, path, value):
        ref = self._ref(path[:-1])
        if isinstance(ref, dict):
            key = path[-1]
            if key in ref:
                if isinstance(ref[key], list):
                    ref[key].append(value)
                else:
                    ref[key] = [value]
            else:
                ref[key] = [value]
        else:
            self.set(path, [value])

    def push_queue(self, path, value, max_len):
        default_value = [value][-max_len:] if max_len > 0 else []
        ref = self._ref(path[:-1])
        if isinstance(ref, dict):
            key = path[-1]
            if key in ref:
                if isinstance(ref[key], list):
                    ref[key].append(value)
                    while len(ref[key]) > max_len:
                        ref[key].pop(0)
                else:
                    ref[key] = default_value
            else:
                ref[key] = default_value
        else:
            self.set(path, default_value)

    def pop(self, path):
        ref = self._ref(path)
        if isinstance(ref, list):
            ref.pop()

    def shift(self, path):
        ref = self._ref(path)
        if isinstance(ref, list):
            ref.pop(0)

    def erase(self, path, value):
        ref = self._ref(path)
        if isinstance(ref, list):
            if value in ref:
                ref.remove(value)

    def prepend(self, path, value):
        ref = self._ref(path[:-1])
        if isinstance(ref, dict):
            key = path[-1]
            if key in ref:
                if isinstance(ref[key], list):
                    ref[key].insert(0, value)
                else:
                    ref[key] = [value]
            else:
                ref[key] = [value]
        else:
            self.set(path, [value])

    def add(self, path, delta):
        ref = self._ref(path[:-1])
        if isinstance(ref, dict):
            key = path[-1]
            if key in ref:
                if isinstance(ref[key], int):
                    ref[key] += delta
                else:
                    ref[key] = delta
            else:
                ref[key] = delta
        else:
            self.set(path, delta)

    def applyLog(self, log):
        now = None
        try:
            now = dateutil.parser.parse(log["timestamp"]) if "timestamp" in log else None
        except:
            pass
        self.apply(log["request"], 0 if now is None else datetime.datetime.timestamp(now))


    def readLock(self, path, user):
        self.push(path, user)

    def readUnlock(self, path, user):
        self.erase(path, user)
        ref = self._ref(path)
        if isinstance(ref, list) and len(ref) == 0:
            self.delete(path)

    def writeLock(self, path, user):
        self.set(path, user)

    def writeUnlock(self, path, user):
        self.delete(path)

    def replace(self, path, val, new):
        ref = self._ref(path)
        if isinstance(ref, list):
            for index, entry in enumerate(ref):
                if entry == val:
                    ref[index] = new

    def executeOperation(self, path, op, value):
        if op == "shift":
            self.shift(path)
        elif op == "prepend":
            self.prepend(path, value['new'])
        elif op == "increment":
            delta = value['step'] if 'step' in value else 1
            self.add(path, delta)
        elif op == "decrement":
            delta = value['step'] if 'step' in value else 1
            self.add(path, - delta)
        elif op == "delete" :
                self.delete(path)
        elif op == "set":
            self.set(path, value['new'])
        elif op == "push":
            self.push(path, value['new'])
        elif op == "push-queue":
            self.push_queue(path, value['new'], value['len'])
        elif op == "pop":
            self.pop(path)

        elif op == "read-lock":
            self.readLock(path, value['by'])
        elif op == "read-unlock":
            self.readUnlock(path, value['by'])
        elif op == "write-lock":
            self.writeLock(path, value['by'])
        elif op == "write-unlock":
            self.writeUnlock(path, value['by'])

        elif op == "erase":
            self.erase(path, value['val'])
        elif op == "replace":
            self.replace(path, value['val'], value['new'])
        elif op == "unobserve" or op == "observe":
            pass
        else:
            raise Exception("Unknown operation")

    def apply(self, request, now = None):

        # Lets have a look into the TTL
        if not now == None:
            while len(self.ttlt) > 0:
                top = self.ttlt[0]
                mintime = top[0]
                # remove all entries that are before now
                if mintime < now:
                    self.delete(top[1])
                    heapq.heappop(self.ttlt)
                else:
                    break

        for path in request:
            value = request[path]
            path = AgencyStore.parsePath(path)

            if (not isinstance(value, dict)) or ( not 'op' in value and not 'new' in value ):
                # directly apply value
                self.set(path, value)
            else:
                op = value['op'] if 'op' in value else 'set'
                normalizedPath = "/".join(path)

                if len(self.ttlt) > 0:
                    # delete the old ttl entry
                    for i, x in enumerate(self.ttlt):
                        if x[1] == normalizedPath:
                            del self.ttlt[i]

                if 'ttl' in value and not now == None:
                    heapq.heappush(self.ttlt, (now + value['ttl'], normalizedPath))

                try:
                    self.executeOperation(path, op, value)
                except KeyError as e:
                    raise Exception("{path}: Missing field for operation `{op}`: {text}".format(path=normalizedPath, op=op, text=str(e)))
                except Exception as e:
                    raise Exception("{path}: Exception when executing operation `{op}`: {text}".format(path=normalizedPath, op=op, text=str(e)))



    def parsePath(path):
        return list(filter(None, path.split('/')))

    def _ref(self, path):
        result = self.store
        try:
            for x in path:
                if isinstance(result, list):
                    result = result[int(x)]
                else:
                    result = result[x]
        except:
            return None
        return result

    def get(self, path):
        return copy.deepcopy(self._ref(path))
