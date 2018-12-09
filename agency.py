
import json
import copy

class AgencyStore:

    def __init__(self):
        self.store = {}

    def __str__(self):
        return json.dumps(self.store)

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
                    ref[key].insert(0, value)
                else:
                    ref[key] = [value]
            else:
                ref[key] = [value]
        else:
            self.set(path, [value])

    def pop(self, path, value):
        ref = self._ref(path)
        if isinstance(ref, list):
            ref.pop()

    def shift(self, path, value):
        ref = self._ref(path)
        if isinstance(ref, list):
            ref.pop(0)

    def prepend(self, path, value):
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

    def apply(self, request):
        for path in request:
            value = request[path]
            path = AgencyStore.parsePath(path)

            if not 'op' in value and not 'new' in value:
                # directly apply value
                self.set(path, value)
            else:
                op = value['op'] if 'op' in value else 'set'

                if op == "set":
                    self.set(path, value['new'])
                elif op == "delete":
                    self.delete(path)
                elif op == "increment":
                    delta = value['new'] if 'new' in value else 1
                    self.add(path, delta)
                elif op == "decrement":
                    delta = value['new'] if 'new' in value else 1
                    self.add(path, - delta)
                elif op == "push":
                    self.push(path, value)
                elif op == "pop":
                    self.pop(path, value)
                elif op == "shift":
                    self.shift(path, value)
                elif op == "prepend":
                    self.prepend(path, value)

    def parsePath(path):
        return list(filter(None, path.split('/')))

    def _ref(self, path):
        result = self.store
        for x in path:
            if not isinstance(result, dict) or not x in result:
                return None
            result = result[x]
        return result

    def get(self, path):
        return copy.deepcopy(self._ref(path))
