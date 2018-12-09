
import sys

class Log:

    f = sys.stdout

    def intoFile(filename):
        Log.f = open(filename, 'w')

    def fmt(msg, *args):
        if Log.f != None:
            Log.f.write((msg + "\n").format(*args))
