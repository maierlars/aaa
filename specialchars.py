import curses, curses.ascii
import os, sys


def main(stdscr, argv):
    stdscr.clear()
    curses.curs_set(0)

    y = 0

    while True:
        c = stdscr.getch()

        stdscr.addstr(y, 0, "{} {} {}".format(c, chr(c), curses.keyname(c)))
        c = curses.ascii.unctrl(c)
        y += 1
        stdscr.addstr(y, 0, "{}".format(c))
        y += 1

if __name__ == '__main__':
    try:
        os.putenv("ESCDELAY", "0")  # Ugly hack to enabled escape key for direct use
        curses.wrapper(main, sys.argv)
    except Exception as e:
        raise e
