# Curses functions

import signal
import curses
import atexit

_Stdscr = None

def _finishCurses():
    curses.nocbreak()
    curses.echo()
    curses.endwin()

def _initCurses():
    global _Stdscr
    atexit.register(_finishCurses)
    _Stdscr = curses.initscr()

def enterCurses():
    if not _Stdscr:
        _initCurses()

    curses.cbreak()
    curses.noecho()
    _Stdscr.nodelay(1)

    signal.signal(signal.SIGWINCH, signal.SIG_IGN)

def leaveCurses():
    curses.reset_shell_mode()
    signal.signal(signal.SIGWINCH, signal.SIG_DFL)

# Check non-blockingly for a key press and returns it, or return None if no
# key is found. enter/leaveCurses must surround the getc() call.
def getCh():
    ch = _Stdscr.getch()

    if ch < 0:
        return None

    return chr(ch)

def clearScreen():
    if not _Stdscr:
        _initCurses()

    _Stdscr.clear()

def printLines(lines):
    y = 0
    for line in lines:
        try:
            _Stdscr.insnstr(y, 0, line, len(line))
        except:
            pass
        y += 1

    try:
        _Stdscr.insnstr(y, 0, "", 0)
    except:
        pass

