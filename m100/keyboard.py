"""Model 100 keyboard: a 9-column x 8-row scanned matrix.

Columns 0-7 are strobed active-low through 81C55 Port A; the modifier
column (8) is selected by pulling Port B bit 0 low.  Row returns are read
at I/O port 0xE8 (active low: 0xFF = nothing pressed).

This module owns the single source of truth for how physical PC keys map
onto Model 100 matrix positions; the hover-bubble UI reads the same table.
"""

import pygame as pg

# name -> (column, row-bit)
MATRIX = {
    "Z": (0, 0), "X": (0, 1), "C": (0, 2), "V": (0, 3),
    "B": (0, 4), "N": (0, 5), "M": (0, 6), "L": (0, 7),
    "A": (1, 0), "S": (1, 1), "D": (1, 2), "F": (1, 3),
    "G": (1, 4), "H": (1, 5), "J": (1, 6), "K": (1, 7),
    "Q": (2, 0), "W": (2, 1), "E": (2, 2), "R": (2, 3),
    "T": (2, 4), "Y": (2, 5), "U": (2, 6), "I": (2, 7),
    "O": (3, 0), "P": (3, 1), "[": (3, 2), ";": (3, 3),
    "'": (3, 4), ",": (3, 5), ".": (3, 6), "/": (3, 7),
    "1": (4, 0), "2": (4, 1), "3": (4, 2), "4": (4, 3),
    "5": (4, 4), "6": (4, 5), "7": (4, 6), "8": (4, 7),
    "9": (5, 0), "0": (5, 1), "-": (5, 2), "=": (5, 3),
    "LEFT": (5, 4), "RIGHT": (5, 5), "UP": (5, 6), "DOWN": (5, 7),
    "SPACE": (6, 0), "BKSP": (6, 1), "TAB": (6, 2), "ESC": (6, 3),
    "PASTE": (6, 4), "LABEL": (6, 5), "PRINT": (6, 6), "ENTER": (6, 7),
    "F1": (7, 0), "F2": (7, 1), "F3": (7, 2), "F4": (7, 3),
    "F5": (7, 4), "F6": (7, 5), "F7": (7, 6), "F8": (7, 7),
    "SHIFT": (8, 0), "CTRL": (8, 1), "GRPH": (8, 2), "CODE": (8, 3),
    "NUM": (8, 4), "CAPS": (8, 5), "PAUSE": (8, 7),
}

# name -> (list of pygame keys, label shown in the hover bubble)
PC_MAP = {
    "SHIFT": ([pg.K_LSHIFT, pg.K_RSHIFT], "Shift"),
    "CTRL": ([pg.K_LCTRL, pg.K_RCTRL], "Ctrl"),
    "GRPH": ([pg.K_LALT], "Left Alt"),
    "CODE": ([pg.K_RALT], "Right Alt"),
    "NUM": ([pg.K_NUMLOCK], "Num Lock (hold)"),
    "CAPS": ([pg.K_CAPSLOCK], "Caps Lock"),
    "PAUSE": ([pg.K_F12, pg.K_PAUSE], "F12 / Pause  (Shift = BREAK)"),
    "PASTE": ([pg.K_F9], "F9"),
    "LABEL": ([pg.K_F10], "F10"),
    "PRINT": ([pg.K_F11], "F11"),
    "ENTER": ([pg.K_RETURN, pg.K_KP_ENTER], "Enter"),
    "BKSP": ([pg.K_BACKSPACE, pg.K_DELETE], "Backspace / Delete"),
    "SPACE": ([pg.K_SPACE], "Space"),
    "TAB": ([pg.K_TAB], "Tab"),
    "ESC": ([pg.K_ESCAPE], "Esc"),
    "LEFT": ([pg.K_LEFT], "Left arrow"),
    "RIGHT": ([pg.K_RIGHT], "Right arrow"),
    "UP": ([pg.K_UP], "Up arrow"),
    "DOWN": ([pg.K_DOWN], "Down arrow"),
    "[": ([pg.K_LEFTBRACKET, pg.K_RIGHTBRACKET], "[ or ]"),
    ";": ([pg.K_SEMICOLON], ";"),
    "'": ([pg.K_QUOTE], "'"),
    ",": ([pg.K_COMMA], ","),
    ".": ([pg.K_PERIOD], "."),
    "/": ([pg.K_SLASH], "/"),
    "-": ([pg.K_MINUS], "-"),
    "=": ([pg.K_EQUALS], "="),
}
for _n in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    PC_MAP[_n] = ([getattr(pg, "K_" + _n.lower())], _n)
for _n in "0123456789":
    PC_MAP[_n] = ([getattr(pg, "K_" + _n)], _n)
for _i in range(1, 9):
    PC_MAP["F%d" % _i] = ([getattr(pg, "K_F%d" % _i)], "F%d" % _i)

# pygame key -> (column, row-bit)
KEY_TO_MATRIX = {}
for _name, (_keys, _label) in PC_MAP.items():
    for _k in _keys:
        KEY_TO_MATRIX[_k] = MATRIX[_name]


def bubble_label(name):
    """Hover-bubble text for a Model 100 key name."""
    if name in PC_MAP:
        return PC_MAP[name][1]
    return None


class Keyboard:
    def __init__(self):
        self.scan = [0xFF] * 9  # active low

    def reset(self):
        self.scan = [0xFF] * 9

    def set_matrix(self, col, bit, down):
        if down:
            self.scan[col] &= ~(1 << bit) & 0xFF
        else:
            self.scan[col] |= 1 << bit

    def handle_key(self, key, down):
        """Feed a pygame key event.  Returns True if the key is mapped."""
        pos = KEY_TO_MATRIX.get(key)
        if pos is None:
            return False
        self.set_matrix(pos[0], pos[1], down)
        return True

    def press_name(self, name, down):
        col, bit = MATRIX[name]
        self.set_matrix(col, bit, down)

    def read_rows(self, port_a, port_b):
        """Row read at port 0xE8 for the current strobe state."""
        if (port_b & 0x01) == 0:
            return self.scan[8]
        rows = 0xFF
        strobe = (~port_a) & 0xFF
        if strobe:
            scan = self.scan
            for c in range(8):
                if strobe & (1 << c):
                    rows &= scan[c]
        return rows
