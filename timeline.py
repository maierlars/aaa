from controls import *

class Control:

    def __init__(self, app, rect):
        self.app = app
        self.rect = rect

    def layout(self, rect):
        self.rect = rect

    def update(self):
        pass

    def input(self, c):
        return False

    def serialize(self):
        raise NotImplementedError("Serialize was not implemented by the Control")

    def restore(self, state):
        raise NotImplementedError("Restore was not implemented by the Control")

    def title(self):
        raise NotImplementedError("Title was not implemented by the Control")


class AgencyEvent:

    def __init__(self, time, title, labels, refs):
        self.time = time
        self.title = title
        self.labels = labels
        self.refs = refs

class AgencyTimeline(Control):

    def __init__(self, app, rect):
        super().__init__(app, rect)

    def update(self):
        pass

    def input(self, c):
        return False

    def refresh():
        # Inspect the log and transform log entries into Events
        for l in self.app.log:

            # Inspect all paths that have been touched
            for path in l["request"]:



