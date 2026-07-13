"""Boot the real ROM headless and verify the machine reaches the main menu."""

import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from m100.config import Config
from m100.machine import Machine, CPU_HZ
from m100 import rom


def lcd_ascii(lcd):
    """Render the LCD framebuffer as ASCII art (2x4 pixels per char)."""
    px = lcd.pixels()
    out = []
    for y in range(0, 64, 4):
        line = []
        for x in range(0, 240, 2):
            n = 0
            for dy in range(4):
                for dx in range(2):
                    n += px[(y + dy) * 240 + (x + dx)]
            line.append(" .:#@"[min(4, n // 2)])
        out.append("".join(line))
    return "\n".join(out)


def main():
    cfg = Config()
    data = rom.get_system_rom(cfg, progress=print)
    m = Machine(data, cfg)

    start = time.perf_counter()
    for _ in range(6):  # six emulated seconds
        m.run_cycles(CPU_HZ)
    elapsed = time.perf_counter() - start
    print(f"6 emulated seconds in {elapsed:.2f}s host "
          f"({6 / elapsed:.1f}x real speed)")

    text = m.screen_text()
    print("--- screen text shadow (RAM 0xFE00) ---")
    for row in text:
        print("|" + row + "|")
    print("--- LCD framebuffer ---")
    print(lcd_ascii(m.lcd))

    joined = "\n".join(text)
    ok = True
    for needle in ("Microsoft", "BASIC", "TEXT", "TELCOM", "ADDRSS",
                   "SCHEDL", "Bytes free"):
        present = needle in joined
        print(f"  menu shows {needle!r}: {'ok' if present else 'FAIL'}")
        ok &= present

    px = m.lcd.pixels()
    lit = sum(px)
    print(f"  LCD lit pixels: {lit}")
    ok &= lit > 500

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
