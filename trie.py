
def build_trie(words):
    root = dict()
    for word in words:
        current = root
        for c in word:
            current = current.setdefault(c, {})
        current[0] = word
    return root

class Node:
    def __init__(self, root):
        self.prev_match = None
        self.current = root

    def update(self, idx, c):
        if c in self.current:
            self.current = self.current[c]
            if 0 in self.current:
                self.prev_match = (idx, self.current[0])
            return True
        elif self.prev_match is not None:
            return self.prev_match
        else:
            return False

class Trie:
    def __init__(self, words):
        self.data = build_trie(words)

    def find_all(self, string):
        active = []
        found = []

        def update_all_nodes(i, c):
            new_active = list()
            for node in active:
                res = node.update(i, c)
                if isinstance(res, tuple):
                    # we found a match
                    i, match = res
                    found.append(match)
                elif res is True:
                    new_active.append(node)
            return new_active

        i = 0
        while i < len(string):
            c = string[i]
            active.append(Node(self.data))
            active = update_all_nodes(i, c)
            i += 1

        update_all_nodes(len(string), -1)

        return found





if __name__ == "__main__":
    print(Trie(["a", "ab", "cd"]).find_all("abhella abcd"))
