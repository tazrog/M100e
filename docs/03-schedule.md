# 03 — Schedule

Basis: 6–8 hours per week, split roughly as two weekday evenings (~2.5 h each,
of which the first 20 minutes is re-loading context) and one weekend block
(~3 h). Ranges are **realistic to pessimistic**, not best case. A hobbyist
evening reliably yields less than its clock time, and I have priced that in.

| Phase | Work | Low (h) | High (h) | Evenings/weekends | Calendar at 7 h/wk | Blowout risk |
|---|---|---:|---:|---|---|---|
| **P0** | Gather docs, dump ROM, instrument emulator as trace oracle, buzz out both connectors, photograph donor | 8 | 16 | 3–6 sessions | 1–2 weeks | Low — unless the ROM dump fights you |
| **P1** | VEE supply, level-shift layer, CS chain, FPGA pattern generator, panel alive | 18 | 40 | 7–16 sessions | 3–6 weeks | **High** |
| **P2** | Keyboard scan, full matrix verified against `keyboard.py` | 6 | 14 | 2–6 sessions | 1–2 weeks | Low |
| **P3** | 8085 core + ROM/RAM in BSRAM, HDMI debug console, lockstep trace diff vs. Python | 35 | 80 | 14–32 sessions | 5–11 weeks | **Highest** |
| **P4** | 8155 model, LCD register bridge, READY-gated CPU stall, HDMI shadow framebuffer | 18 | 40 | 7–16 sessions | 3–6 weeks | **High** |
| **P5** | Real panel + real keyboard integration, busy pass-through | 10 | 28 | 4–11 sessions | 1.5–4 weeks | Medium |
| **P6** | RTC, beeper, UART, printer strobe, option ROM, RAM→SD persistence | 14 | 30 | 6–12 sessions | 2–4 weeks | Medium |
| **P7** | Case, mounting, power from AA/wall wart, thermal check | 10 | 24 | 4–10 sessions | 1.5–3.5 weeks | Medium |
| | **Total** | **119** | **272** | | **17–39 weeks** | |

**Bottom line: 4 to 9 months of calendar time**, most likely landing around
6 months. The spread is wide because two phases genuinely can double.

---

## Which phases will blow past estimate, and why

### P3 — the 8085 core. Expect the high end, plan for worse.

This is the classic soft-core trap: the core reaches 95% correct in the first
15 hours and then you spend 40 more on the last 5%. Specifically:

- **Flags.** The 8085's auxiliary carry semantics on `DAA`, `INR/DCR`, and the
  arithmetic path are where every home-grown 8080/8085 core bleeds. The ROM will
  execute millions of instructions before a wrong AC bit surfaces as a visible
  fault, and by then the trace is long.
- **Undocumented behaviour.** The 8085 has undocumented opcodes and the X5/K
  flag. Whether the M100 ROM touches any is unknown to me — your Python emulator
  is the authority, and if it implements them, they matter.
- **Interrupt timing.** RST 5.5/6.5/7.5, the RIM/SIM mask semantics, and the
  250 Hz tick interact with the ROM's keyboard and serial handling in ways that
  do not show up until Phase 5.
- **Trace diffing is slow work.** Building the harness that compares fabric
  execution against `cpu85.py` is itself a solid evening or three, and it is the
  thing that saves you from a month of blind debugging. Do not skip it.

Mitigating factor unique to you: you have a working reference implementation in
this repository. That is worth a great deal — most people attempting this have no
oracle. It moves the low end down, not the high end.

### P1 — the panel. Bimodal, not merely uncertain.

Either the panel lights up in the first evening after your bias supply is right,
or you spend three weekends distinguishing a bias problem from a translation
problem from a 40-year-old contact problem. There is not much middle. What drives
the high end:

- Contrast on these panels has a narrow usable window, and "wrong VEE" and "dead
  panel" look identical.
- The V2/contrast pin's expected range is documented inconsistently (see
  `04-risks.md`); if your first assumption about its polarity is wrong you will
  chase it.
- Zebra-strip contact faults on a 40-year-old assembly produce missing columns
  that mimic a CS fault exactly.

### P4 — the bus sequencer and CPU stall.

Gating READY correctly, rather than faking the write, is the right call and also
the fiddly one. Expect to iterate on the handshake between "CPU asserts an I/O
write," "sequencer runs an E-strobe cycle at HD44102 timing," and "CPU is
released." Off-by-one on the release edge produces intermittent corruption that
only appears under specific ROM access patterns.

### P7 — mechanical. Always underestimated.

Fitting a Tang Nano plus an interface board into an M100 shell alongside the
original flex routing is a fitting-and-refitting job. Every "it's nearly in"
costs another evening. The 10–24 h range is honest.

---

## Phases that will likely come in at or under estimate

- **P2 keyboard.** You already have the definitive matrix table in
  `m100/keyboard.py`. The only real work is rollover-diode-safe strobing.
- **P0.** Bounded, mechanical work, with a clear finish line.

---

## Scheduling advice

- **Interleave P1, P2 and P3.** They share no unknowns. When P3 has you stuck on
  a flag bug, an evening on the keyboard is genuinely productive rather than
  procrastination.
- **Do not start P5 on a weeknight.** First contact between the real panel and
  the CPU wants a full weekend block and a clear head; it is the session where a
  tired mis-wire costs you the panel.
- **Budget one full session per phase for writing down what you learned.**
  Six-month hobby projects die at the re-entry cost after a two-week gap.
