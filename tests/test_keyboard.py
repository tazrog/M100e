"""Type into the ROM through the key matrix: enter BASIC, do math, BEEP."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from m100.config import Config
from m100.machine import Machine, CPU_HZ
from m100 import rom

CHAR_KEYS = {
    " ": "SPACE", "\r": "ENTER", "+": ("SHIFT", "="), "*": ("SHIFT", ":"),
    "(": ("SHIFT", "9"), ")": ("SHIFT", "0"), "\"": ("SHIFT", "'"),
    "?": ("SHIFT", "/"), ":": ";", "$": ("SHIFT", "4"), "%": ("SHIFT", "5"),
}


def press(m, name, hold=0.06, settle=0.04):
    m.kbd.press_name(name, True)
    m.run_cycles(int(CPU_HZ * hold))
    m.kbd.press_name(name, False)
    m.run_cycles(int(CPU_HZ * settle))


def type_text(m, text):
    for ch in text:
        spec = CHAR_KEYS.get(ch, ch.upper() if ch.isalpha() else ch)
        if isinstance(spec, tuple):
            mod, key = spec
            m.kbd.press_name(mod, True)
            m.run_cycles(int(CPU_HZ * 0.03))
            press(m, key)
            m.kbd.press_name(mod, False)
            m.run_cycles(int(CPU_HZ * 0.03))
        else:
            press(m, spec)


def main():
    cfg = Config()
    m = Machine(rom.get_system_rom(cfg), cfg)
    m.run_cycles(CPU_HZ * 2)  # boot to menu

    ok = True

    # Menu cursor sits on BASIC: press ENTER
    press(m, "ENTER", 0.08, 1.0)
    screen = "\n".join(m.screen_text())
    got_basic = "Ok" in screen and "Bytes free" in screen
    print("entered BASIC:", "ok" if got_basic else "FAIL")
    print("\n".join("|" + r + "|" for r in m.screen_text()[:3]))
    ok &= got_basic

    type_text(m, "print 2+2\r")
    m.run_cycles(CPU_HZ // 2)
    screen = m.screen_text()
    print("\n".join("|" + r + "|" for r in screen[:5]))
    answered = any(r.strip() == "4" for r in screen)
    print("PRINT 2+2 -> 4:", "ok" if answered else "FAIL")
    ok &= answered

    # exit back to menu with F8
    press(m, "F8", 0.10, 1.5)
    screen = "\n".join(m.screen_text())
    back = "Select:" in screen
    print("F8 back to menu:", "ok" if back else "FAIL")
    ok &= back

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
