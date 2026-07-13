# M100e — a TRS-80 Model 100 emulator

An original, written-from-scratch emulator of the Radio Shack TRS-80
Model 100 portable computer.  The screen shows the actual machine: the
photo is the case, the LCD area is the live 240×64 display, and your
keyboard is wired straight into the Model 100's key matrix.

![layout check](assets/layout_check.png)

## Running

Requirements: Python 3.10+, `pygame`, `numpy` (and `tkinter` for the file
dialogs — normally part of Python).

```
python3 m100e.py          # fullscreen (Alt-Tab still works)
python3 m100e.py -w       # windowed
```

On first run the emulator downloads the community-preserved 32K Model 100
system ROM from the Internet Archive, verifies its checksum, and caches it
in `~/.m100e/`.  Then it cold-boots to the familiar menu: BASIC, TEXT,
TELCOM, ADDRSS, SCHEDL — all the real ROM software, running on an emulated
2.4576 MHz 80C85.

## Using it

- **Type normally.**  The PC keyboard maps positionally onto the Model 100
  matrix.  Hover the mouse over any key in the picture and a bubble shows
  which real key drives it (GRPH = Left Alt, CODE = Right Alt,
  PASTE/LABEL/PRINT/PAUSE = F9–F12, BREAK = Shift+F12, …).  Clicking a key
  with the mouse presses it too.
- **Right-click** (or Ctrl+F1) opens the emulator menu.
- **Ctrl+Up / Ctrl+Down** turn the LCD contrast wheel (persisted).  Crank
  it too far and the unlit dots darken, just like the real knob.
- Files live in battery-backed RAM, exactly like the real machine; the RAM
  image is saved to `~/.m100e/ram.bin` on exit and restored at startup.
  `POWER OFF` in BASIC really powers the machine down (press any key to
  power back on — files intact).

## Emulator menu

- **Load program** — `.BA` (ASCII BASIC is tokenized with the ROM's own
  keyword table; tokenized images are relocated), `.DO` text, `.CO`
  machine code.  Injected directly into the RAM file system, so they
  appear on the menu instantly.  **Export** goes the other way (.BA files
  are detokenized to readable source).
- **Option ROM** — load a 32K option ROM image into the socket (TS-DOS,
  Super ROM, …).  The archive.org item the system ROM comes from also
  contains several option ROM carts.  Eject it from the same menu.
- **Load system ROM** — run a custom 32K main ROM.
- **Memory** — 8K / 16K / 24K / 32K, populated from the top down like real
  RAM modules (changing it cold-starts the machine).
- **Serial & modem → internet:**
  - The **RS-232 port** bridges to `host:port` (menu-settable).  In TELCOM
    set `STAT 98N1E`, press `Term`, and you are online — the connection
    opens automatically.  Works with real telnet BBSes (telnet negotiation
    is handled).
  - The **modem** really pulse-dials: TELCOM clicks the phone relay and
    the emulator counts the pulses.  Map "phone numbers" to hosts in the
    dial directory (e.g. `1 → telehack.com:23`), set `STAT M7I1E`, and
    dial.  Carrier detect asserts while the socket is up; hanging up
    drops it.
  - Baud pacing can be authentic (characters arrive at the programmed
    baud rate) or fast.
- LPRINT/PRINT output is captured to `~/.m100e/printer.txt`.

## What's emulated

| Hardware | Implementation |
|----------|----------------|
| 80C85 CPU @ 2.4576 MHz | full instruction set incl. RIM/SIM, RST 5.5/6.5/7.5, cycle-counted |
| LCD | ten HD44102 drivers, chip-selects, pages, hardware scroll, read-modify-write |
| Keyboard | real 9×8 scanned matrix, strobed through the 81C55 |
| 81C55 PIO/timer | ports A/B/C, timer as UART baud clock and beeper tone source |
| Clock | uPD1990AC bit-banged serial protocol, follows host time (TIME$/DATE$ writes honored) |
| Beeper | timer tone mode and software-toggle mode, synthesized square wave |
| UART IM6402 | RX interrupts on RST 6.5, per-character pacing, modem/RS-232 mux |
| Modem | relay pulse-dial decoding, carrier detect, TCP bridge |
| RAM | 8–32K battery-backed, persisted across runs |
| ROM | genuine 32K system ROM + option ROM socket bank-switching |

Yes, the year shows 19xx — the ROM hardcodes the "19"; that's the Model
100's own famous Y2K quirk, faithfully reproduced.

## Tests

```
python3 tests/test_cpu.py         # 8085 core self-test + speed benchmark
python3 tests/test_boot.py        # boots the real ROM to the menu
python3 tests/test_keyboard.py    # types into BASIC through the matrix
python3 tests/test_features.py    # RAM sizes, files, option ROM, TELCOM/TCP, dialer
```

`tools/gen_layout.py` regenerates `assets/layout.json` (LCD rectangle and
key hitboxes) from the case photo, plus `layout_check.png` to eyeball the
result.
