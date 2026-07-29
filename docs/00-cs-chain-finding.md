# 00 — Task 0: Where does the 10-bit LCD chip-select chain live?

## Answer

**Neither. There is no CS shift register anywhere in a TRS-80 Model 100.**

The ten HD44102 chip selects are ten *parallel, latched* outputs of the 81C55
(Intel 8155-family PIO), wired straight from the motherboard to the LCD's 30-pin
connector:

| Source | Destination |
| --- | --- |
| 81C55 Port A, PA0–PA7 | LCD connector pins 7–14 → CS of drivers 1–8 |
| 81C55 Port B, PB0 | LCD connector pin 15 → CS of driver 9 |
| 81C55 Port B, PB1 | LCD connector pin 16 → CS of driver 10 |

The 81C55's port output latches *are* the CS register. Nothing shifts. The ROM
writes a 10-bit mask across two port registers (I/O `0xB9` = Port A,
`0xBA` = Port B) and the mask appears at the panel on the next write.

**Confidence: high (~90%).** The remaining 10% is that I have not personally read
the LCD sheet of the service-manual schematic — the one public KiCad transcript
explicitly leaves the LCD sheet unstarted. The bench check below closes that gap
in about ten minutes.

## Evidence

1. **Your own emulator, which runs the unmodified ROM.** `m100/lcd.py` and
   `m100/machine.py` in this repository model CS as a flat 10-bit mask assembled
   from `pa` and `pb & 0x03`, applied combinationally on every port write:

   ```python
   self.lcd.set_cs(((self.pb & 0x03) << 8) | val)   # machine.py, Port A write
   ```

   There is no shift state, no clock bit, no serial data bit — and BASIC, TEXT,
   TELCOM and the boot menu all render correctly. If a shift register sat in the
   path, a flat-mask model would produce garbage on screen, not a working
   machine. This is the strongest single piece of evidence available, because it
   is behavioural rather than documentary.

2. **The 30-pin connector carries ten discrete CS conductors.** The pinout
   published by the `osresearch/model100` FPGA-board project
   ([github.com/osresearch/model100](https://github.com/osresearch/model100)):

   | Pin | Signal | Pin | Signal |
   | --- | --- | --- | --- |
   | 1 | VDD (+5V) | 17 | RESET |
   | 2 | Buzzer | 18 | CS1 (common to all ten drivers) |
   | 3 | VEE (−5V) | 19 | E (enable strobe) |
   | 4 | Contrast (V2) | 20 | R/!W |
   | 5, 6 | GND | 21 | D/!I (data / instruction) |
   | 7–16 | CS20…CS29 (per-driver select) | 22–29 | AD0–AD7 |
   | | | 30 | NC |

   Ten dedicated per-driver select pins on the connector means the selection is
   already decoded before it reaches the module. A module-resident shift register
   would need two pins, not ten.

   Note also what is *absent*: no CL1, CL2, FRM, or M. All display timing is
   generated on the module. See "Second finding" below.

3. **The public schematic transcript colour-codes exactly ten periphery lines.**
   [hzeller/trs80-100-schematic](https://github.com/hzeller/trs80-100-schematic)
   labels its signal classes with *"Blue: Periphery IO lines from 81C55:
   `PA[0..7]`, `PB[0..1]`"* — precisely the ten lines, and named as a group.

4. **Prior art drives the panel the same way.** Both Trammell Hudson's Teensy++
   retrofit and his later iCE40 board describe *"ten Hitachi HD44102 LCD
   controllers, each with its own select line and shared control lines."* Nobody
   who has physically driven this panel reports a serial select path.

## Consequences — this is the part that matters

### Your pin budget problem is real and stands

Ten CS + eight data + E + R/W + C/D + RESET = **22 signals**, matching your
estimate. Nothing about the finding makes it disappear.

### But a 74HC154 is the wrong mitigation, and would silently break the ROM

A 4-to-16 decoder can only ever assert **one** select. The Model 100 asserts
**many at once**, routinely, on two independent paths:

- **Screen clear.** Your own `lcd.py` header says it outright: *"several drivers
  can be selected at once (the ROM clears the screen that way)."* The ROM sets a
  wide mask and writes zeros to every selected driver in one pass.
- **Keyboard scanning.** PA0–PA7 and PB0 are *shared* between LCD chip selects
  and keyboard column strobes, at opposite polarity. `keyboard.py` strobes
  `(~port_a) & 0xFF` (active low) while `lcd.py` selects on bits that are *set*
  (active high). So scanning column 0 writes `0xFE` to Port A — which
  simultaneously asserts seven LCD chip selects. Harmless on real hardware
  because E is never strobed during a scan, but it means the CS lines carry
  arbitrary 10-bit patterns, not one-hot codes, most of the time.

A decoder would turn both of those into corruption that looks exactly like a bus
timing fault. **Do not use a 74HC154 here.**

### The right mitigation is to build the shift register you thought existed

Two cascaded **74HCT595** (HCT input thresholds accept 3.3V logic directly on a
5V supply — no separate translator for this path) give you an arbitrary latched
10-bit mask for **three** FPGA pins: SER, SRCLK, RCLK. The mask only changes when
the ROM writes Port A or Port B — a few hundred times a second at most — so the
serial load never touches the E-strobe critical path. Load the chain, then run
the bus cycle.

Revised LCD pin cost: **15** (8 data + E + R/W + C/D + RESET + 3 chain).

### Keyboard follows from the same finding

Because columns and CS share port bits at inverted polarity, you have a choice:

- **Direct drive (recommended for bring-up):** 9 column outputs + 8 row inputs =
  17 FPGA pins, all at 3.3V, no translators. A pressed key pulls a row through a
  rollover diode; 3.3 − 0.7 = 2.6V still clears LVCMOS33 VIH of 2.0V. Total
  system pin count 15 + 17 = **32 of 34 header GPIO**. Fits, barely.
- **Second 595 chain if you run short:** 3 pins instead of 9, saving 6.

Verify the Tang Nano 20K's usable GPIO count before committing: Sipeed's
marketing says 34 GPIO across the two 20-pin headers, and there is an additional
40-pin RGB LCD FPC connector whose pins I could **not** confirm are separate FPGA
I/O rather than shared with the headers. Check the board schematic pin list
before you assume you have 32+ free pins alongside HDMI.

## Second finding (unasked, but it kills one of your risks)

The 30-pin connector has **no CL1/CL2/FRM/M pins**. The HD44103 common driver and
the HD44102 timing chain are clocked entirely from the module. Your worry that
"the HD44103 may self-oscillate rather than accept a host clock, changing what I
must source" resolves in your favour: the host never supplies display timing, and
there is nothing for you to source. Confidence: high, on connector evidence.
Confirm visually by looking for the timing RC or master/slave strapping on the
module PCB.

## Third finding (affects your busy-flag decision)

Your emulator's `read_status()` returns a hardcoded `0x40` — **never busy** — and
the entire ROM runs. That is strong evidence the ROM uses fixed delay loops
rather than polling the busy flag on the critical path.

This does not change your stated design intent (passing the real busy flag
through is still the correct, faithful thing to do, and costs little). It does
change your *debugging* posture: if the panel misbehaves, busy handling is very
unlikely to be the cause, so do not spend evenings there. It also gives you a
safe fallback — if busy readback proves electrically awkward, you can tie it off
and still boot.

## Bench verification — under an hour, no power required for the first two steps

Do these in order. Stop as soon as step 1 gives a clean answer.

### Step 1 — Continuity, donor unpowered (10 min)

You need the 81C55's pin numbers from the 8155/8156 datasheet — do not trust my
recollection of which physical pins PA0–PA7 and PB0–PB1 land on; read them off
the datasheet pinout (see `05-sources.md`).

1. Meter in continuity mode. One probe on LCD connector pin 7, walk the other
   across the 81C55's Port A pins.
2. **< 1 Ω to a Port A pin → direct wire → finding confirmed, no shift register,
   you are done.**
3. Repeat for pins 8–16 (expect PA1…PA7, then PB0, PB1 in order).
4. If any pin instead reads open, or reads through a resistance, or lands on a
   14/16-pin IC rather than the 81C55, go to step 2.

Also buzz pin 18 (CS1) — expect it to go to a common enable, likely gated by the
LCD chip-select address decode, not to a port bit.

### Step 2 — Visual, donor unpowered (10 min)

Look at the ICs physically between the 81C55 and the LCD connector. A CS shift
register would be a 74xx164 or 74xx595 (14/16 pins) sitting right at the
connector. If the only things in the path are the 81C55 and passives, the finding
is confirmed a second way. Photograph the area before you cut anything —
`06-decisions.md` has you potentially sawing this board up.

### Step 3 — Logic analyzer, donor powered, only if steps 1–2 disagree (20 min)

Only meaningful if the donor's CPU section still executes (the fault is described
as bias/contrast, so it may well run blind).

1. Eight channels on LCD connector pins 7–14, one on pin 19 (E), common ground to
   pin 5.
2. Power up, capture ~200 ms of boot.
3. **Multiple CS lines high simultaneously → parallel mask confirmed, and the
   74HC154 option is formally dead.**
4. A single line walking through positions in step with a clock edge → shift
   register present, and you would then locate its clock and data pins.

### Step 4 — Zero hardware, five minutes, do this tonight (5 min)

The cheapest confirmation of the load-bearing sub-claim (arbitrary masks, not
one-hot) uses the emulator already in this repository. Add a temporary counter in
`LCD.set_cs` that logs any mask with a population count greater than one, then
cold-boot the emulator and clear the screen.

If multi-bit masks appear — and they will — you have proven, without touching the
donor, that a one-of-N decoder cannot drive this panel. That single test is worth
more than any datasheet on this specific question.

## Where the two branches you asked about diverge

Both of your hypothesised branches are wrong, so the divergence is different from
what you expected:

| Your branch | Reality | Impact |
| --- | --- | --- |
| Chain on the LCD module → FPGA supplies data + clock, pin problem vanishes | Does not exist | Pin problem stays |
| Chain on the motherboard → replicate or harvest | Does not exist either | Nothing to harvest; the 81C55 latches are what you replicate, and you already replicate them in fabric as part of the 8155 model |
| — | **Actual: parallel latched mask** | Build a *new* 595 chain purely as a pin-count optimisation, not as fidelity. It is your choice, not the ROM's |

The practical upshot is pleasant: the shift register becomes an implementation
detail entirely under your control, sitting between your fabric-modelled 8155
port latches and the panel. If it misbehaves you can bypass it by wiring CS
directly during debug, which is not true of anything the ROM depends on.

## Sources

- [github.com/osresearch/model100](https://github.com/osresearch/model100) — iCE40 Model 100 board; 30-pin connector pinout, VEE and keyboard notes
- [github.com/hzeller/trs80-100-schematic](https://github.com/hzeller/trs80-100-schematic) — KiCad transcript of the main board (LCD sheet not yet transcribed)
- [trmm.net/TRS80_Model_100](https://trmm.net/TRS80_Model_100/) — Teensy++ retrofit writeup (returned 403 to this session; reachable from a browser)
- [Bitchin100 DocGarden, Model 100 LCD Programming](http://bitchin100.com/wiki/index.php?title=Model_100_LCD_Programming) — (403 to this session; the authoritative programming reference, read it in a browser)
- [TRS-80 Model 100 schematics, Internet Archive](https://archive.org/details/trs-80-model-100-main-pcb-schematic-from-tech-ref-manual) — 600 dpi scans of the tech-ref pull-out
- This repository: `m100/lcd.py`, `m100/machine.py`, `m100/keyboard.py`
