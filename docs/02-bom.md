# 02 — Bill of materials

**Price confidence.** Mouser, DigiKey and Bitchin100 product pages returned 403 to
this session, so I could not scrape live carts. Prices below are anchored where I
could get a real figure through search (marked ✓) and are otherwise my best
estimate from recent distributor pricing (marked ~). Treat every ~ figure as
±30% and verify at order time. I would rather you check than get burned.

**Assumed already owned:** Tang Nano 20K, soldering iron, logic analyzer, PC with
Gowin toolchain, LCD panel, keyboard, case, standoffs, flex cables, donor board
passives.

---

## Tier 1 — Bare minimum (target: first character on the panel)

Everything needed to complete Phases 1–5. Phase 7 case/power parts are listed
separately because they are not needed "before it displays a character."

| # | Item | Qty | Why needed | Est. unit | Est. total | Supplier | Flags |
|---|---|---|---|---|---|---|---|
| 1 | **Digital multimeter** (AstroAI / ANENG AN8008 class) | 1 | Non-negotiable. Sets and verifies the −5V VEE rail and contrast range; without it you are guessing at the one voltage that can kill an irreplaceable panel. You listed no DMM. | ~$20 | ~$20 | Amazon | Biggest single line in this tier. If you own one, the tier drops to ~$52 |
| 2 | 74HCT245N, DIP-20 | 4 | 3.3V→5V outbound translation for D0–D7 and for E / R/W / C/D / RESET. HCT input thresholds (VIH 2.0V) accept 3.3V logic directly on a 5V rail — no dedicated translator IC required in this direction. 2 in use, 2 spare. | ✓$0.78–0.85 | ~$3.40 | DigiKey / Mouser | Buy spares; these are what you'll cook if you mis-wire |
| 3 | 74LVC245AN, DIP-20 | 2 | 5V→3.3V inbound for data reads (busy flag, display RAM readback). Run at 3.3V; inputs are 5V tolerant. | ~$1.10 | ~$2.20 | DigiKey / Mouser | **Hard to source in DIP** — Nexperia DIP stock is thinning. Fallbacks: SOIC + breakout adapter (~$1 for 5 adapters, AliExpress), or 8× resistor dividers (1k/2k) which work fine at these speeds |
| 4 | 74HCT595N, DIP-16 | 3 | The 10-bit CS chain (2 cascaded) that replaces 10 FPGA pins with 3. HCT again means no translator on the serial path. 1 spare. | ~$0.60 | ~$1.80 | DigiKey / Mouser | Per `00-cs-chain-finding.md`, this replaces the 74HC154 idea, which would break screen clear |
| 5 | ICL7660S or TC1044S, DIP-8 | 2 | −5V VEE generation. Charge-pump inverter from the 5V rail; the panel needs a regulated −5V and an adjustable contrast tap. | ✓$1.00–2.36 | ~$4.00 | Amazon 10-pk ~$8 / DigiKey | ICL7660**S** (not plain 7660) — higher oscillator frequency, less ripple into the panel |
| 6 | Passives kit: 10 µF + 100 µF electrolytics, 0.1 µF ceramics, resistor assortment (33 Ω, 100 Ω, 1 k, 10 k) | 1 | Charge-pump caps, decoupling on every IC, and 33–100 Ω series resistors on **every** line touching the panel — cheap insurance against a mis-drive destroying an unobtainable HD44102. | ~$10 | ~$10 | Amazon / AliExpress | Harvest what you can from the donor board first and cut this line |
| 7 | 10 kΩ multi-turn trimpot | 2 | Contrast adjust, plus one spare. Multi-turn because the usable contrast window on these panels is narrow. | ~$1.50 | ~$3.00 | Amazon / AliExpress | Replaces the donor's faulty pot entirely, per your plan |
| 8 | Double-sided protoboard, 70×90 mm | 5-pk | The interface board. Two spins expected before you're happy. | ~$7/5 | ~$7.00 | AliExpress / Amazon | |
| 9 | DIP sockets, 8/16/20-pin assortment | 1 set | Never solder a translator directly during bring-up — you will swap them. | ~$5 | ~$5.00 | Amazon / AliExpress | |
| 10 | 2.54 mm headers + F-F jumper leads | 1 set | Tang Nano header to interface board. Keep leads short — these are 5V-edge signals. | ~$6 | ~$6.00 | Amazon / AliExpress | |
| 11 | 24 AWG solid / wire-wrap wire, multi-colour | 1 | Point-to-point wiring on protoboard. | ~$6 | ~$6.00 | Amazon | |
| 12 | Desoldering braid + manual solder sucker | 1 ea | You have no desoldering gear. This is the cheap substitute; the PCB-cutting strategy in `06-decisions.md` is what keeps it sufficient. | ~$8 | ~$8.00 | Amazon | |
| 13 | 5V USB supply, 2 A, with a spare cable | 1 | Bench power for the Tang Nano + panel logic. Panel logic draws tens of mA, so the Nano's 5V pin can feed it — measure before you rely on it. | ~$8 | ~$8.00 | Amazon / on hand | |

**Tier 1 subtotal: ~$84.40** — or **~$64** if you already have a multimeter,
**~$54** if you also raid the donor board for passives and a trimpot.

You said under $75. As listed it overruns by ~$9, entirely because of the
multimeter. Options, in the order I'd take them: harvest passives and sockets
from the donor board (−$10 to −$15), drop to two 74HCT245 and one 74HCT595 with
no spares (−$2.50, and I would not — spares of the parts most likely to die are
the best value on this list), or buy the $12 multimeter tier instead of the $20
one (fine for DC rails; poorer on continuity beep responsiveness, which you will
use constantly in Phase 0).

---

## Tier 1b — Phase 7 case and power (defer until the machine works)

| # | Item | Qty | Why needed | Est. unit | Est. total | Supplier |
|---|---|---|---|---|---|---|
| 14 | Buck-boost module, 5V out (MT3608 / TPS63020 class) | 2 | 4×AA at 4.8–6V → regulated 5V for the Nano and panel logic. | ~$3 | ~$6 | AliExpress |
| 15 | Barrel jack + 6V wall wart, or USB-C breakout | 1 | Mains operation with the case closed. | ~$8 | ~$8 | Amazon |
| 16 | Nylon standoffs / M2.5 hardware assortment | 1 | Mounting the Nano and interface board on donor standoffs. | ~$8 | ~$8 | Amazon |

**Tier 1b subtotal: ~$22.**

---

## Tier 2 — Comfortable (what I'd add, in priority order)

| # | Item | Qty | Why | Est. price | Supplier | Priority |
|---|---|---|---|---|---|---|
| 17 | **Second donor M100 or spare LCD panel** | 1 | The single highest-value insurance on this list. The HD44102 is obsolete; if you destroy a driver, the project stops dead. A parts machine with a good panel restores it. | ~$60–150 | eBay | **Highest** |
| 18 | LCD zebra strips, M100 set | 1 set | The classic M100 "missing columns" fault is contact, not silicon. Having these on hand stops you from misdiagnosing a contact fault as a CS-decode bug for a week. | ~$10–15 | [Soigeneris](https://www.soigeneris.com/trs-80-model-100-lcd-zebra-strips) | **Highest** |
| 19 | Entry oscilloscope (FNIRSI DSO152 / DSO138 kit class) | 1 | A DMM reads the VEE rail fine, so you can start without one. You want a scope the moment you suspect charge-pump ripple, E-strobe edge quality, or contention on the data bus — none of which a logic analyzer shows you. | ~$25–60 | Amazon / AliExpress | High |
| 20 | Custom PCB, 2-layer, ~80×60 mm | 5 | Replaces the protoboard once the design is stable. See `06-decisions.md`. | ~$10–30 inc. shipping | JLCPCB / PCBWay | Medium |
| 21 | Hot-air rework station (858D class) | 1 | Makes connector harvesting realistic instead of destructive. Not required if you take the cut-the-PCB route. | ~$45–60 | Amazon / AliExpress | Medium |
| 22 | Mini rotary tool + cutting discs | 1 | For cutting the connector islands out of the donor board without desoldering. Cheaper than hot air and, for this specific job, better. | ~$20 | Amazon | Medium (High if you skip #21) |
| 23 | SN74LVC8T245 (SMD) + SOIC-24 breakout adapters | 2 ea | Proper dual-supply bidirectional translation in one part; cleaner than the HCT/LVC pair once you spin a PCB. | ✓$0.74 + ~$1 | DigiKey + AliExpress | Medium |
| 24 | 30-pin FFC/FPC connector, pitch TBD | 3 | Only if you decide to build fresh rather than cut the donor's connector island out. **Measure the flex pitch with calipers first** — the original is an obsolete HU-30P-2G-L13 and I could not confirm its pitch. | ~$2 | DigiKey / AliExpress | Low, and blocked on a measurement |
| 25 | Flux pen, tweezers, helping hands, IPA | 1 set | Quality-of-life. | ~$25 | Amazon | Low |

**Tier 2 subtotal: ~$195–375** depending on whether you buy a second donor.

---

## Totals

| Tier | Subtotal |
|---|---|
| Tier 1, bare minimum, to first character | **~$84** (~$64 with a DMM on hand) |
| Tier 1 + 1b, complete machine in the case | **~$106** |
| Tier 1 + 1b + Tier 2, comfortable | **~$300–480** |

---

## Hard-to-source / long-lead items

| Item | Problem | What to do |
|---|---|---|
| **HD44102 / HD44103** | Obsolete, no second source, only eBay/AliExpress pulls of dubious provenance at $10–30 each. Replacing one on the panel means rework on a flex-mounted, possibly COB assembly. | Treat as unobtainable. Protect the panel with series resistors, correct power sequencing, and never hot-plugging. This constraint drives the whole phase order in `01-phased-plan.md`. |
| **M100 LCD zebra strips** | Niche; one or two hobby suppliers. | Buy with the first order, not when you need them. |
| **HU-30P-2G-L13 30-pin connector** | Long obsolete; pitch unconfirmed by me. | Prefer cutting the donor's connector island out of the PCB. If you must buy, measure the flex pitch first. |
| **74LVC245A in DIP** | DIP stock is thinning across vendors. | SOIC + adapter, or resistor dividers. Not a project risk, just an annoyance. |
| **System ROM image** | You must dump your own. | Phase 0. Read it off the donor's mask ROM. |

## Buy spares of

74HCT245 (2 spare), 74HCT595 (1 spare), ICL7660S (1 spare), trimpot (1 spare) —
all cost pennies and all sit on the failure path. The one that matters far more
than any of them is a **spare panel**, which is why it heads Tier 2 despite the
price.
