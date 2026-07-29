# 06 — Decision points

Each of these is a stop-and-choose. Where I have a recommendation I give it and
say why; where the call is genuinely yours I say that instead.

---

## D1 — Write your own 8085 core, or use an existing one?

**Decide before:** Phase 3. **Reversible?** Expensively — a swap mid-project
invalidates your trace-diff baseline.

| | Write your own | Reuse (realistically: `scottlbaker/8085-SOC`) |
|---|---|---|
| Starting point | `m100/cpu85.py` — a working, cycle-counted 8085 that runs the real ROM. A de-facto executable specification you wrote and understand. | Unknown completeness. README documents neither RIM/SIM, TRAP, nor the RST 5.5/6.5/7.5 masks. VHDL, iCE40-targeted. |
| Effort | 35–80 h (see `03-schedule.md`) | 10–20 h if it turns out complete; 40+ h if you must audit and repair someone else's core |
| Debuggability | You know every line; instrumenting for the lockstep trace diff is natural | Auditing an unfamiliar core against ROM behaviour is slower than writing one, in my experience |
| Risk profile | Known-shape risk: flags, undocumented opcodes, interrupt timing | Unknown-shape risk: you find the gap in Phase 5, in someone else's style |
| Fidelity to the M100's needs | Exactly what the ROM needs, because it already runs the ROM | Must be verified against the ROM anyway |

**Recommendation: write your own, ported from `cpu85.py`.** The usual argument
for reuse — "don't rebuild a solved problem" — does not hold here, because the
8085 is *not* well served by open cores the way the Z80 and 6502 are, and because
you already own the hard part: a validated behavioural model. The port is
mechanical where the semantics are settled, and every place it is not, your
Python answers the question.

**But spend one evening first** reading `8085-SOC`'s source for instruction
coverage and interrupt handling. If it is genuinely complete, that is 30 hours
you did not spend, and this recommendation flips. Do not decide from its README —
it does not say.

**Third option worth a thought:** port `cpu85.py` semantics but keep the Python
as a co-simulation reference for the whole project, not just Phase 3. That is the
strongest version of the "write your own" path.

---

## D2 — Protoboard, or spin a small PCB?

**Decide before:** Phase 1 build. **Reversible?** Yes, cheaply — this is the
lowest-stakes decision here.

| | Protoboard | Custom PCB |
|---|---|---|
| Cost | ~$7 for five | ~$10–30 for five, incl. shipping |
| Lead time | Zero | 1–2 weeks per spin, and you will do two |
| Signal quality | Adequate. Your fastest edges are E-strobe transitions into a 1980s panel — this is not a signal-integrity problem | Better, and irrelevant at these speeds |
| Iteration | Cut a trace, move a wire, done in minutes | Two weeks per mistake |
| Fitting in the case (Phase 7) | Bulky, tall, fragile under vibration | Purpose-shaped, mounts on donor standoffs |
| Given you have no hot-air | Fine — everything is DIP | Fine too, if you keep it DIP/through-hole |

**Recommendation: protoboard through Phase 5, then decide.** You do not yet know
the final pin assignment (R5 is open), whether the keyboard goes direct or onto a
second 595 chain, or what the contrast network ends up looking like (R3). Freezing
a PCB before those are settled buys you a two-week wait for a board you will cut
traces on anyway.

Revisit at Phase 7. If the protoboard fits the case and survives handling, ship
it. If it does not, you will then be spinning a board whose schematic is *known
good*, which is the only time PCB fabrication is genuinely low-risk.

---

## D3 — Gut the donor motherboard into a passive carrier, or build fresh and harvest only connectors?

**Decide before:** Phase 1 wiring. **Reversible?** **No.** Cutting is permanent,
and the board is your only physical reference (R9).

This is the most consequential decision of the three, and your no-hot-air, sub-$75
situation pushes it in a specific direction.

**Standing constraint that shapes all three options: the LCD assembly stays
mounted and clamped.** The glass, driver PCB and zebra strips are never
separated, the frame screws never come out, and the module's flex tail stays
mated in an original socket. Everything below is evaluated against that.

### Option A — Passive carrier: depopulate the donor board, keep it as the chassis

Desolder or cut away the active silicon, keep the PCB with its connectors, power
section and mounting geometry intact, and tap signals at the CPU/8155 socket
footprints.

**For:** Every connector is already mounted, aligned and mechanically correct —
the LCD flex, the keyboard, the power section, the case standoff pattern, the
port cut-outs. This is exactly the hassle that eats Phase 7. The existing traces
from the 81C55 footprint out to the LCD connector are *already the wiring you
would otherwise hand-build*, which is a genuine saving of tedious, error-prone
point-to-point work.

**Against:** Removing a dozen 40-pin DIPs and gate arrays with braid and a solder
sucker, no hot air, is many hours of grim work with real risk of lifting pads.
The board is known unreliable — the fault is described as bias/contrast, which
is arguably the section you are discarding, but "arguably" is doing work in that
sentence. And you inherit every trace you did not intend to inherit: unpowered
sections, old passives, and parasitic paths that will make you doubt your own
logic during debug.

### Option B — Build fresh, harvest only connectors

**For:** Everything in your new build is known and intentional. No inherited
faults, no ghost traces. Debugging is honest.

**Against:** With no hot air, harvesting the 30-pin LCD socket intact is
genuinely hard, and destroying it is plausible — the replacement is an obsolete
part whose pitch I could not even confirm. You then rebuild the mechanical fit
from scratch in Phase 7.

### Option C — Cut the connector islands out of the PCB (recommended)

Take a rotary tool to the donor board and cut out the *regions* containing the
LCD connector and the keyboard connector, with a generous margin of surrounding
copper. Solder wires directly to the pads and traces on those islands. Mount the
islands where the geometry requires.

**For:** You never desolder the hard part — you keep it soldered to a piece of
its own PCB. It costs a $20 rotary tool (Tier 2 item 22) and no hot air. Connector
alignment is preserved as a mechanical unit. Your new circuit stays clean and
fully intentional. You can cut generously enough to keep the first few
centimetres of the original traces, which gives you comfortable places to land
wires.

**And, decisively, it is the only option that lets the panel assembly stay
sealed.** The module's flex tail mates into its original socket, on its original
pads, at its original insertion depth — once — and then never moves again. You
solder to the island's copper, not to the flex. No heat near the tail, no
reseating, no clamping pressure disturbed. Cut the island large enough to take
two mounting screws, fix it and the case top half to a common base, and run a
300–400 mm wire harness from the island to the protoboard so that all bench
movement is absorbed by wire you can replace in an evening (see R4b).

**Against:** Irreversible, and it consumes the reference board. Requires the
Phase 0 photography and buzz-out discipline to be done properly *first*. The
islands need their own mechanical mounting solution in Phase 7.

**Recommendation: Option C, and the panel-stays-mounted constraint settles it.**
It captures most of Option A's connector benefit at none of its desoldering cost
or inherited-fault confusion, it is the only one of the three comfortable with the
tools you actually own, and it is the only one that never asks you to touch the
flex tail or the zebra stack.

Option B is now clearly the worst of the three, not merely the most laborious:
harvesting the socket loose with braid and a sucker means heat and mechanical
stress right where the flex has to mate, and if the socket is damaged in the
process your sealed panel has nowhere to plug in. Option A remains defensible if
depopulation turns out to be pleasant work — but do not commit to it before you
have removed one 40-pin DIP with braid and a sucker and seen how that evening
goes.

**Precondition on any of these, non-negotiable:** Phase 0's photographs and
connector buzz-out are complete and written down before the tool touches the
board.

---

## D4 — Keyboard on direct GPIO, or on a second 595 chain?

**Decide before:** Phase 2 wiring. **Reversible?** Yes, if you plan for it.

Direct is 9 column pins + 8 row pins = 17, all at 3.3V, nothing between the FPGA
and the matrix. Second chain is 3 + 8 = 11 pins for one $0.60 part and a little
more logic.

**Recommendation: direct, but lay the protoboard out so the swap is a
daughter-module.** Direct removes a whole class of "is it my shift register or my
scan logic" ambiguity from Phase 2. Move to the chain only if R5 resolves against
you and the pin budget will not close.

---

## D5 — What happens to RAM at power-off?

**Decide before:** Phase 6, but the hook must exist before you start relying on
the machine.

Options: (a) flush 32K to microSD on the ROM's power-off signal (Port B bit 4);
(b) periodic dirty-page flush; (c) supercap ride-through; (d) accept volatility.

**Recommendation: (a), with (b) as later hardening.** (d) is not a Model 100 —
persistence is the machine's defining feature. (a) is straightforward because the
ROM tells you exactly when it is shutting down and your emulator already models
the signal.

---

## D6 — Does the HDMI debug path stay in the finished machine?

**Decide before:** Phase 7 case work.

Keeping it costs a case cut-out or an internal header and some fabric. Removing
it reclaims resources and keeps the case original.

**Recommendation: keep it, on an internal header.** It costs almost nothing, it
is the diagnostic that distinguishes bus faults from CS faults (the reason you
wanted it), and the first time something goes wrong after the case is closed you
will want it back. An internal header preserves the case exterior; you open the
machine to use it, which is the right trade for a debug feature.

---

## D7 — Series resistors on the panel lines: yes or no?

Not really a decision, but people talk themselves out of it, so it is written
down: **yes, 33–100 Ω on every line to the panel.** At your edge rates they cost
nothing, and they convert several of R1's kill mechanisms from fatal to
survivable. The part you are protecting cannot be bought.
