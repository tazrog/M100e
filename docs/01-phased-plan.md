# 01 — Phased plan

Target end state (confirmed): a working machine inside the original M100 case,
self-powered, closes up.

**Standing mechanical constraint: the LCD assembly is never opened.** Glass,
driver PCB and zebra strips stay clamped as a unit for the life of the project;
the frame screws stay in; the flex tail mates into its socket once and then stays
put. Every phase below assumes it. The corollary is that the tail and socket
become the fragile items instead — see R4b — so Phase 1 includes building a rig
that keeps them motionless.

Ordering rule applied throughout: **each phase introduces exactly one class of
unknown.** Where a phase would introduce two, it is split. The panel is brought
up before the CPU exists, and the CPU is brought up before it is allowed near the
panel, so that when they meet in Phase 5 both halves are already known good.

Phase 1 is deliberately *not* the CPU. The riskiest assumption in this project is
not "can I write an 8085" — you have already written one in Python and it runs
the ROM. It is **"can 3.3V FPGA logic, my own level shifting, and my own negative
bias supply drive a 40-year-old panel I cannot replace, without destroying it."**
That is what Phase 1 attacks, with zero CPU in the picture.

---

## Phase 0 — Gather, dump, instrument

**Work**
- Collect every document in `05-sources.md`. Read the HD44102 datasheet
  end to end; extract E pulse width, setup/hold, and the CS1/CS2/CS3 selection
  truth table into a one-page cheat sheet you keep at the bench.
- Dump the system ROM from the donor board. Do not download it.
- Instrument the Python emulator to emit a **bus trace oracle**: for every LCD
  access, log `(cs_mask, c/d, r/w, data)`; for every CPU instruction in the first
  few million cycles, log `(pc, a, bc, de, hl, sp, flags)`. Both become the
  golden references for Phases 3 and 4.
- Run the Task 0 step-4 popcount check. Confirm multi-bit CS masks.
- **Gowin toolchain groundwork** (details in `07-toolchain.md`): write
  `tools/rom2mi.py`, load the ROM into BSRAM and read known bytes back out to
  prove initialisation works; flash a blinky to the QSPI NOR and confirm the
  board cold-boots with no PC attached; stand up the Makefile and `.gitignore`
  additions; record the Gowin EDA version. All of this is cheap now and
  expensive to discover later — particularly the flash test, since the end state
  is a closed case with no PC attached.
- Photograph the donor board, both sides, high resolution, before any cutting.
- Buzz out and record: LCD connector pin-to-81C55 map, keyboard connector
  pin-to-matrix map, and the polarity of the keyboard column drive (the
  emulator says active low — confirm there is or is not an inverting buffer).
- **Buzz the flex tail's 30 conductors end to end while it is still unmated**,
  and record the result. Once it is seated in the glued-down island in Phase 1
  you are not pulling it back out to check a pinout, and an open conductor found
  later will look exactly like a chip-select bug.

**Go / no-go:** you have a ROM image that boots your own emulator, a trace file
you can diff against, a verified wiring map from both connectors, and a board
that boots a trivial design from its own flash. If the ROM dump fails, stop and
solve that — everything downstream needs it.

---

## Phase 1 — Panel alive, no CPU

The riskiest assumption, attacked with the least machinery.

**Work**
- **Build the bench rig first, before any electronics.** Cut the LCD socket
  island out of the donor board (per `06-decisions.md` D3), screw or glue it to a
  rigid base — plywood, acrylic, whatever — and fix the case top half carrying
  the mounted panel to that same base. Mate the flex tail into the socket **once**.
  Kapton-tape the tail where it leaves the module. Run a 300–400 mm wire harness
  from the island's pads out to where the protoboard will live, and put a
  connector on the *protoboard* end. From here on, everything you plug, unplug,
  rewire or accidentally yank happens on that far end. The flex never moves again.
- Build the −5V VEE supply on protoboard: ICL7660/TC1044S charge pump, plus a
  contrast pot. Bring it up **disconnected from the panel**, verify −5V and the
  contrast range with a DMM, and load it with a resistor to confirm it holds.
- Build the level-shift layer: 74HCT245 outbound (3.3V logic in, 5V out) for data
  and control, 74LVC245A inbound at 3.3V for reads, 2× 74HCT595 for the CS chain.
  Series resistors (33–100 Ω) on every line that touches the panel.
- Write a small FPGA state machine — no CPU, no ROM — that resets the panel, then
  walks a checkerboard / diagonal / all-on / all-off pattern into all ten
  drivers, then reads the display RAM back.
- First real `.cst`: panel pins at `LVCMOS33`, conservative `DRIVE`, and
  unused/dual-purpose pins set to input tri-state so the panel is not driven
  during FPGA configuration (R10). Bring up the NCO clock enable here too — see
  `07-toolchain.md`.
- Power sequencing: bring VDD up before VEE, and confirm the panel's behaviour at
  power-off ordering too.

**Go / no-go:**
1. Stable, correct pattern on all 240×64, all ten drivers, no dropouts.
2. Contrast sweeps smoothly across the pot range without ghosting or streaking.
3. **Readback matches what was written** — this proves the bidirectional path,
   the inbound translator, and R/W handling in one test.
4. Nothing above ambient temperature after 30 minutes.

**If it fails, the fault is electrical — bias, translation, or E timing.** There
is no CPU, no ROM and no CS decode logic in the picture to blame. Missing or
faint columns that change under *light* thumb pressure on the bezel are the
classic zebra-strip contact fault, not your logic — press gently, treat it purely
as a diagnostic reading, and do not follow it by opening the stack (R4).

---

## Phase 2 — Keyboard alive, no CPU

**Work**
- Drive the nine columns and read eight rows directly from FPGA pins at 3.3V,
  rows constrained `PULL_MODE=UP` for the internal pull-ups.
- Scan active-low, one column asserted at a time, others driven high or
  tri-stated — never two columns low, or you fight the rollover diodes.
- Report results over the onboard USB-serial debugger, or as a simple key-name
  overlay on the HDMI output you already have working.

**Go / no-go:** every key on the physical keyboard, including SHIFT, CTRL, GRPH,
CODE, NUM, CAPS and PAUSE/BREAK, produces exactly the matrix position listed in
`m100/keyboard.py`'s `MATRIX` table, with no phantoms when three keys in an L are
held. That table is your expected-value oracle — it already encodes the answer.

---

## Phase 3 — CPU core + ROM + RAM, no peripherals

**Work**
- 8085 core in fabric (see `06-decisions.md` for build-vs-reuse), 32K ROM and 32K
  RAM in BSRAM — 512 Kbit of the GW2AR-18's 828 Kbit, no SDRAM required.
- HDMI debug console showing PC, registers, and a scrolling instruction window.
- **Build the Verilator/Icarus trace harness before the core is finished**, not
  after: same per-instruction dump format as the instrumented `cpu85.py`, one
  `make` target, diff. This is the single decision that separates a 35-hour
  Phase 3 from an 80-hour one.
- Lockstep trace compare against the Phase 0 oracle: run N instructions, diff.

**Go / no-go:** the core matches the Python emulator's PC and register trace for
the entire boot sequence up to the first LCD port access — no divergence, not
"close." Undocumented opcodes, RIM/SIM behaviour and the RST 5.5/6.5/7.5 masks
are where a divergence will show up; the diff tells you the exact instruction.

---

## Phase 4 — 8155 + LCD bridge, on HDMI only

The panel stays disconnected. This is the phase where the HDMI shadow
framebuffer earns its keep.

**Work**
- 8155 model in fabric: port latches, timer, and the shared PA/PB semantics.
- LCD register-level bridge: the 10-bit CS mask, ten HD44102 models in fabric
  each with display RAM, pointer, and start-page register.
- Bus sequencer implementing HD44102 E-strobe timing and **stalling the CPU by
  gating READY**, not by completing the write in one clock.
- HDMI shadow framebuffer that renders the ten fabric-modelled driver RAMs
  through the exact same geometry as `lcd.py`'s `pixels()`, including the
  hardware-scroll start page.
- GAO instrumentation on the sequencer, and HD44102 setup/hold assertions in the
  simulation testbench so violations fail loudly in sim rather than subtly on
  glass. `.sdc` gets a two-FF synchroniser and `set_false_path` on the busy input.

**Go / no-go:** the boot menu, then BASIC, render correctly on HDMI, pixel-identical
to the Python emulator's screen for the same ROM and keystrokes. Because this
runs against fabric-modelled drivers, any error here is *logic* — CS decode,
pointer wrap at column 50, page addressing, scroll. None of it can be blamed on
wiring or bias.

---

## Phase 5 — Real panel, real keyboard, real machine

Now, and only now, the two proven halves meet.

**Work**
- Swap the fabric HD44102 models for the real panel behind the bus sequencer.
  Keep the HDMI shadow live *in parallel* — driven from writes as they go out to
  the panel.
- Bring the real keyboard in behind the Phase 2 scanner.
- Wire the real busy flag through instead of synthesising it.

**Go / no-go:** cold boot to the menu on the real panel, enter BASIC, type and run
a program, save it to a RAM file, list it back. **HDMI and the panel must agree.**
Where they disagree is your diagnostic: HDMI correct + panel wrong is a wiring,
timing or bias fault; both wrong is logic. This is exactly the discrimination you
asked for, and it is only possible because Phase 4 established HDMI as trusted.

---

## Phase 6 — Peripherals and persistence

**Work**
- RTC (µPD1990AC), beeper, UART/RS-232, printer strobe, option-ROM bank switch.
- **RAM persistence.** A real M100 keeps files in battery-backed RAM; your FPGA
  RAM is volatile, so files vanish on power-off unless you handle it. The ROM
  already tells you when: Port B bit 4 is the power-off line, which your emulator
  models. Intercept it, flush 32K to microSD, restore at boot.

**Go / no-go:** power-cycle the machine and find your BASIC program and TEXT
documents still there. Set the clock, confirm it survives. Beeper sounds on
BEEP/error.

---

## Phase 7 — Into the case

**Work**
- Mount the Tang Nano and the interface board on the donor standoffs; route the
  LCD flex and keyboard connector at their original lengths.
- Power: the case must run from a wall wart and/or the AA compartment. You need a
  regulated 5V rail for the panel logic and the Tang Nano; 4×AA at 4.8–6V needs a
  small buck-boost module.
- Cut-outs, if any, for USB/JTAG access and HDMI debug — decide whether HDMI stays
  permanently accessible or becomes an internal header.
- **Write the bitstream to QSPI NOR flash** so the machine boots itself with no
  PC attached. A design that only lives in SRAM is not a finished machine — and
  this is why `07-toolchain.md` has you prove flash programming works back in
  Phase 0.

**Go / no-go:** case closes, runs on its own power for an hour, boots and takes
keystrokes with the lid shut, and nothing inside exceeds hand-warm.

---

## Phase dependency map

```
P0 gather/dump/instrument
 ├─> P1 panel alive (electrical unknowns)      ─┐
 ├─> P2 keyboard alive (matrix unknowns)       ─┤
 └─> P3 CPU + ROM (core-correctness unknowns)  ─┤
        └─> P4 8155 + LCD bridge on HDMI       ─┤ (logic unknowns)
                                                └─> P5 integration
                                                      └─> P6 peripherals
                                                            └─> P7 case
```

P1, P2 and P3 are independent of each other and can be interleaved when you are
blocked or bored — they share no unknowns. P4 must not begin before P3 passes,
and P5 must not begin before P1 and P4 both pass. Resist the temptation to plug
the panel in early: the panel is the one component you cannot replace.
