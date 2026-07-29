# 04 — Risk register

Ranked by likelihood × pain. "Pain" is weighted by irreversibility: anything that
can destroy the panel outranks anything that merely costs evenings.

---

## R1 — You destroy an HD44102 and the project stops

**Likelihood:** medium · **Pain:** project-ending · **Rank: 1**

The panel is irreplaceable in practice. The drivers are obsolete, mounted on a
flex assembly, and a single dead one leaves a 50×32 hole in the display. The
realistic kill mechanisms are: applying VEE with VDD absent (or reversed
polarity from a mis-wired charge pump), driving 5V panel inputs from a
3.3V-powered translator that is unpowered while the panel is live, hot-plugging
the flex, and bus contention when your R/W direction control glitches during a
read.

**Mitigation**
- 33–100 Ω series resistors on **every** signal line to the panel. They cost
  nothing at these speeds and convert several of the above from fatal to survivable.
- Bring VDD up before VEE and take it down after; verify both orders on the bench
  with the panel disconnected before you ever connect it.
- Verify the charge-pump output polarity and magnitude with a DMM into a resistive
  load, panel disconnected, every single time you rewire that section.
- Never plug or unplug the flex with power applied.
- Explicit tri-state discipline on the data bus: the FPGA and the panel must
  never both drive. Make the inbound translator's OE a function of R/W *and* E.

**Fallback:** buy a parts M100 (~$60–150) — Tier 2 item 17, and the only true
insurance on the list.

---

## R2 — The 8085 core is subtly wrong and you find out three phases later

**Likelihood:** high · **Pain:** weeks · **Rank: 2**

A hand-written core that boots the ROM to a menu can still have a wrong AC flag
on `DAA`, a wrong `RIM` bit layout, or an interrupt-mask edge case. These do not
fail loudly; they fail as a corrupted BASIC calculation or a hang after ten
minutes of TELCOM, in Phase 5 or 6, when you also have panel wiring and a bus
sequencer in the frame and no way to tell which is lying.

**Mitigation:** the lockstep trace diff in Phase 3, against `m100/cpu85.py`. Dump
`(pc, regs, flags)` per instruction from both and diff. Run it long — through the
boot, into BASIC, through a program. This is the single highest-value piece of
test infrastructure in the project, and the reason Phase 3 exists as its own
phase with a hard go/no-go instead of being folded into integration.

---

## R3 — Contrast/VEE convention wrong, and it looks like a logic fault

**Likelihood:** high · **Pain:** days · **Rank: 3**

VEE is documented as regulating to −5V on the original board, and repair guides
say to measure it against GND. But the connector's pin 4 (V2 / contrast) is
described in one prior-art source as a *0–5V* range, and the original design
adjusted it with a pot — I could not reconcile whether the contrast tap swings
positive-referenced or between GND and VEE. If you guess wrong you get a blank or
uniformly grey panel, which is indistinguishable from "my E timing is broken."

**Mitigation:** design the contrast tap so the pot can reach **both** conventions —
wire it across +5V to VEE with the wiper to pin 4, so the wiper spans +5V through
0V to −5V. Sweep the whole range slowly during Phase 1 with a static pattern
loaded. Somewhere in that sweep the image appears. Then measure the wiper voltage
at the sweet spot with the DMM and design the final divider around it.

**Verify before building:** read the HD44102 datasheet's LCD drive-voltage
section, and if the donor board's bias section is intact enough to power up
partially, measure its V2 line at both pot extremes.

---

## R4 — Zebra-strip contact faults masquerade as CS-decode bugs

**Likelihood:** medium (downgraded from high — see below) · **Pain:** days ·
**Rank: 4**

This is the single most common M100 display fault: dead or dim columns caused by
the elastomeric connector between glass and driver PCB losing contact after 40
years. The symptom — a rectangular region of the screen wrong or missing — is
*exactly* what a broken chip select looks like.

**Downgraded because the panel assembly stays mounted and clamped for the
duration of the project.** The dominant way hobbyists induce this fault is by
unscrewing the frame, relieving the clamping pressure on the strips, and
reassembling slightly differently. If the stack is never opened, that mechanism
is off the table and you are left only with latent age-related contact
degradation on an assembly that is currently confirmed working.

**Mitigation:** the HDMI shadow framebuffer, built in Phase 4 before the panel is
ever connected. HDMI correct + panel region missing = contact or wiring. Both
wrong = logic. Secondary: a missing region that changes when you press the bezel
is diagnostic on its own — and note that pressing the bezel is a *test*, not a
repair; do not follow it by opening the stack unless you have decided the strips
really are the fault.

**Standing rule for this project: the LCD frame screws do not come out.** If you
reach a point where you believe the strips must be reseated, treat that as a
deliberate, separately planned operation with the replacement strips already in
hand — not as a debugging step taken at 11pm.

---

## R4b — The flex tail and its socket become the new weak point

**Likelihood:** medium-high · **Pain:** hours to project-ending · **Rank: 4b**

Keeping the panel mounted moves the mechanical risk rather than removing it.
With the glass/PCB/zebra stack sealed, the fragile things become the 30-pin flex
tail coming off the module and the socket it mates into — a 40-year-old friction
FFC socket whose contacts were never designed for repeated cycling. During
Phases 1 and 5 the panel will be sitting on the bench next to your protoboard,
tethered by exactly that flex. Every time you drag the board across the bench,
you are working the tail. A cracked flex conductor is as project-ending as a dead
HD44102, and it presents as — again — a missing region that looks like a CS fault.

**Mitigation**
- **Mate the flex into the socket island once, then never again.** All
  bench-side reconfiguration happens on the far side of the wire harness, not at
  the flex. This also removes the hot-plug kill mechanism in R1: your disconnect
  point becomes the harness, which is cheap and replaceable.
- **Fix the socket island down.** Cut it with enough surrounding PCB to take two
  screws or a generous blob of hot glue onto a scrap of plywood or acrylic, and
  mount the case top half to the same base. The flex then never moves relative to
  its socket.
- **Put all flexing in the wire harness.** Run 300–400 mm of ribbon or stranded
  wire from the island's pads to the protoboard, so bench movement is absorbed by
  wire you can replace in an evening.
- **Strain-relieve the tail** with Kapton tape where it leaves the module, before
  you start, not after you notice a problem.
- Photograph and buzz out the flex before mating it, per Phase 0 — once it is in
  and glued down you are not pulling it back out to check a pinout.

**Fallback if the flex is already damaged or a conductor is open:** you are back
to opening the stack or building a harness direct to the module, both worse than
anything above. That is why R4b sits this high despite being cheap to mitigate.

---

## R5 — Pin budget doesn't actually close on the Tang Nano 20K

**Likelihood:** medium · **Pain:** days, plus possible rework · **Rank: 5**

The plan needs ~32 GPIO (15 LCD + 17 keyboard) alongside working HDMI. Sipeed
documents 34 GPIO across the two 20-pin headers, and there is a separate 40-pin
RGB LCD FPC connector — but I could **not** confirm from Sipeed's own wiki
whether those FPC pins are additional FPGA I/O or shared with the headers, nor
confirm that HDMI consumes no header pins. Two spare pins is not much margin, and
you will want a couple for debug.

**Mitigation:** before you cut a single wire, open the Tang Nano 20K schematic
and build the actual pin list — header pins, FPC pins, HDMI pins, and what the
onboard SDRAM/SD/debugger consume. If it is tight, move the keyboard columns onto
a second 74HCT595 chain: 3 pins instead of 9, for one $0.60 part. Design the
protoboard so that swap does not require a rebuild.

---

## R6 — Bus sequencer / READY-gating handshake is intermittently wrong

**Likelihood:** medium-high · **Pain:** days · **Rank: 6**

Stalling the CPU by gating READY is the correct approach and the fiddly one. An
off-by-one on the release edge, or releasing before the E strobe's hold time is
satisfied, gives you corruption that appears only under particular ROM access
patterns — e.g. fine during menu draw, wrong during a fast scroll.

**Mitigation:** simulate the sequencer against HD44102 datasheet timing before it
touches hardware, with assertions on setup/hold. In Phase 4 the fabric-modelled
drivers can enforce the same assertions at runtime and flag violations to the
HDMI console. Capture real E/CS/data with the logic analyzer in Phase 5 and
compare against the datasheet waveform.

---

## R7 — Keyboard rollover diodes bite the scan direction

**Likelihood:** medium · **Pain:** hours to days · **Rank: 7**

Diodes on the key matrix mean current flows one way only; strobing the wrong
sense, or driving two columns to opposite levels simultaneously, produces
phantom keys or reverse-biased nonsense. Your emulator strobes active-low with
`(~port_a)`, which tells you the intended sense but not what buffering sits on
the real board.

**Mitigation:** Phase 2 exists to settle this in isolation. One column asserted
low at a time, others high-Z or high; rows pulled up. Test three-key L-shaped
combinations explicitly — that is the configuration that exposes phantom keys.
Confirm the physical diode orientation on the donor keyboard PCB with the DMM's
diode-test range before writing the scanner.

---

## R8 — Files vanish on power-off (no battery-backed RAM)

**Likelihood:** certain if unaddressed · **Pain:** functional regression · **Rank: 8**

The real machine's defining feature is that your TEXT documents survive being
switched off. FPGA BSRAM does not. A machine that loses everything at power-down
is not a Model 100.

**Mitigation:** Phase 6. The ROM tells you when it is going down — Port B bit 4 is
the power-off line, already modelled in your emulator. Intercept it, flush 32K to
microSD, restore at boot. **Do not defer this to "later"** — the power-off hook
needs to exist before you start using the machine, or you will lose work and stop
trusting it.

**Residual risk:** power yanked without the ROM's power-off path (dead batteries,
pulled plug) still loses everything. Optional hardening: periodic dirty-page
flush, or a supercap giving you the milliseconds needed to write out.

---

## R9 — Cutting up the donor board destroys your reference

**Likelihood:** medium · **Pain:** days · **Rank: 9**

The donor is your only physical source of truth for connector pinouts, signal
polarity, and buffering. Once you take a rotary tool to it, questions you have
not thought to ask yet become unanswerable.

**Mitigation:** Phase 0 requires high-resolution photographs of both sides and a
written buzz-out of both connectors **before** any cutting. Also record the
polarity question in R7 and the CS mapping in `00-cs-chain-finding.md` while the
board is intact.

---

## R10 — Power sequencing at switch-on/off glitches the panel

**Likelihood:** medium · **Pain:** hours, occasionally fatal (folds into R1) · **Rank: 10**

The FPGA's I/O come up in an undefined state during configuration, and the
charge pump reaches −5V on its own schedule. During that window the panel can see
undriven or contended inputs, and RESET may not yet be asserted.

**Mitigation:** hold the panel's RESET asserted from a power-on reset that is
independent of FPGA configuration state; use the translators' OE pins, pulled to
the safe state by resistors, so the panel sees high-impedance until the FPGA
deliberately enables them. Verify the whole sequence with the logic analyzer
triggering on power-up.

---

## R11 — Gowin toolchain friction

**Likelihood:** medium · **Pain:** hours · **Rank: 11**

BSRAM inference for 32K ROM + 32K RAM, timing closure on the bus sequencer, and
IP-core quirks. The GW2AR-18's 828 Kb of block RAM is ample, so capacity is not
the issue — inference style and initialisation from a ROM hex file are.

**Mitigation:** you already have HDMI working on this board, so the toolchain is
not new to you. Move both toolchain unknowns into Phase 0 as standalone
experiments, per `07-toolchain.md`: ROM-into-BSRAM with a readback check, and a
blinky flashed to QSPI NOR that cold-boots with no PC attached.

**The flash test is the one people skip.** openFPGALoader has open reports of
CRC/ID-verify failures and hangs writing flash on Tang Nano boards. If that bites
you it is a Gowin-Programmer-instead annoyance discovered in Phase 0, or a
project-blocking discovery in Phase 7 with the case half-assembled — the end
state is a closed case with no PC attached, so SRAM-only loading is not a
finished machine.

---

## Risks I investigated and am downgrading

| Risk | Verdict |
|---|---|
| **HD44103 may need a host-supplied clock, changing what I must source** | **Low.** The 30-pin connector carries no CL1/CL2/FRM/M lines — display timing is generated entirely on the module. Nothing to source. Confirm visually on the module PCB. |
| **Busy-flag handling blocks bring-up** | **Low.** Your emulator hardcodes "never busy" and the whole ROM runs, so the ROM is using fixed delays, not polling. Pass the real flag through for fidelity, but if readback is electrically awkward you can tie it off and still boot. |
| **Need to replicate a CS shift register in fabric or harvest it** | **Eliminated.** No such register exists — see `00-cs-chain-finding.md`. |
| **74HC154 as a pin-budget mitigation** | **Eliminated, and it was a trap.** The ROM asserts arbitrary multi-bit CS masks (screen clear, and keyboard scanning through the shared port bits). A one-of-N decoder would corrupt the display in ways that look like bus timing faults. |
