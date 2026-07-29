# 05 — Sources to gather before starting

Note on access: several of these returned **403 to my session** (Bitchin100,
trmm.net, Mouser/DigiKey product pages, alldatasheet PDFs). They are all fine
from an ordinary browser — the block is on my side, not theirs. Where that
happened I have said so, because it means I am relying on secondary description
rather than having read the primary myself.

---

## Schematics and hardware documentation

| What | Where | Notes |
|---|---|---|
| **TRS-80 Model 100 Technical Reference Manual schematics** | [archive.org — main PCB schematic, 600 dpi](https://archive.org/details/trs-80-model-100-main-pcb-schematic-from-tech-ref-manual) | The pull-out sheet, scanned high enough to read. **Primary source for the LCD sheet** — this is the document that would let you confirm Task 0 from paper rather than from the bench. |
| **Model 100 Service Manual** | [ManualsLib](https://www.manualslib.com/manual/4044017/Tandy-Radio-Shack-Trs-80-100.html) | Board-level repair detail, test points, and the bias/contrast section you are replacing. |
| **KiCad transcript of the main board** | [github.com/hzeller/trs80-100-schematic](https://github.com/hzeller/trs80-100-schematic) | Clean, ERC-passing redraw with signal classes colour-coded. **The LCD sheet is not transcribed** — do not expect the connector detail here. |
| **LCD connector pinout (30-pin)** | [github.com/osresearch/model100](https://github.com/osresearch/model100) | The pinout table reproduced in `00-cs-chain-finding.md`. Cross-check against the archive.org scan before you solder. |
| **Bitchin100 DocGarden — Model 100 LCD Programming** | [bitchin100.com wiki](http://bitchin100.com/wiki/index.php?title=Model_100_LCD_Programming) | The community's authoritative LCD programming reference. **403 to me; read it yourself.** Expect it to state the CS port mapping directly. |
| **Bitchin100 DocGarden — Model 100 System Map** | [bitchin100.com wiki](https://bitchin100.com/wiki/index.php?title=Model_100_System_Map_Part_0) | ROM entry points and I/O map; useful when your core diverges and you want to know what routine you are in. |

## Datasheets

| Part | Where | Why you need it |
|---|---|---|
| **HD44102** column driver | [bitchin100.com/files/hardware/HD44102.PDF](https://bitchin100.com/files/hardware/HD44102.PDF) (403 to me), [alldatasheet](https://www.alldatasheet.com/datasheet-pdf/pdf/169418/HITACHI/HD44102.html), [datasheet4u](https://datasheet4u.com/datasheets/Hitachi-Semiconductor/HD44102/572701) | **The most important document in the project.** E pulse width, setup/hold, CS1/CS2/CS3 selection truth table, VIH/VIL, VEE range, status-byte bit definitions, reset requirements. Extract these to a one-page bench cheat sheet. |
| **HD44103** common driver | [alldatasheet](https://www.alldatasheet.com/datasheet-pdf/pdf/116833/HITACHI/HD44103.html) | Confirms the module-side timing arrangement and that no host clock is expected. 8 pages. |
| **Intel 8085A** | Intel/archive.org, widely mirrored | Instruction timing, machine cycles, READY behaviour, RIM/SIM bit layouts, RST 5.5/6.5/7.5 and TRAP semantics. Your READY-gating design lives or dies on the machine-cycle detail here. |
| **Intel 8155/8156** | Intel/archive.org, widely mirrored | Port latch behaviour, timer modes, and **the physical pin numbers for PA0–PA7 / PB0–PB1** that you need for the Task 0 continuity check. |
| **µPD1990AC** RTC | NEC datasheet, mirrored on retro sites | Phase 6. Your `m100/rtc.py` already implements it — the datasheet is for cross-checking the serial protocol. |
| **IM6402** UART | Intersil, mirrored | Phase 6. Same situation: `m100/uart.py` is your working reference. |
| **74HCT245 / 74LVC245A / 74HCT595** | TI / Nexperia | Input threshold verification — the whole level-shifting strategy rests on HCT's VIH being 2.0V on a 5V rail. |
| **ICL7660S / TC1044S** | Renesas / Microchip | Charge-pump external component values and the boost-frequency pin. |
| **Tang Nano 20K schematic + pin list** | [Sipeed wiki](https://wiki.sipeed.com/hardware/en/tang/tang-nano-20k/nano-20k.html), [sipeed_wiki on GitHub](https://github.com/sipeed/sipeed_wiki) | **Needed to close R5.** The wiki page itself does not answer whether the 40-pin RGB FPC pins are separate FPGA I/O; go to the schematic. |

## Toolchain

Working notes and project-specific setup are in `07-toolchain.md`; these are the
reference documents behind it.

| What | Where | Notes |
|---|---|---|
| **Gowin EDA user guides** — IP Core Generator, GAO analyzer, constraint (`.cst`/`.sdc`) syntax | Bundled with your install (`gowin/IDE/doc`), also on the Gowin site | Prefer the bundled copies. Web copies drift across versions, and constraint syntax and Project Settings defaults are exactly where that bites. |
| **GW2AR-18 datasheet / GW2A family user guide** | Gowin site | BSRAM primitives, rPLL parameters, I/O standards and drive-strength options. |
| **openFPGALoader** | [github.com/trabucayre/openFPGALoader](https://github.com/trabucayre/openFPGALoader) | Scriptable programming. Skim the issue tracker for Tang Nano flash-write reports ([#511](https://github.com/trabucayre/openFPGALoader/issues/511), [#241](https://github.com/trabucayre/openFPGALoader/issues/241)) before you rely on flash boot in Phase 7. |
| **Sipeed: flashing on Linux** | [wiki.sipeed.com](https://wiki.sipeed.com/hardware/en/tang/Tang-Nano-Doc/flash-in-linux.html) | Board-specific programming notes. |
| **Verilator / Icarus Verilog + GTKWave** | [verilator.org](https://www.veripool.org/verilator/), [steveicarus.github.io/iverilog](https://steveicarus.github.io/iverilog/) | Where the Phase 3 trace diff runs. Not Gowin's built-in simulator. |

## ROM image

You must dump your own — and this repository's own policy is explicit about that.

- **Preferred:** read the 32K mask ROM off the donor board with a programmer, or
  in-circuit if you can hold the CPU off the bus.
- **Alternative:** if you get access to a working M100, the ROM can be read out
  over the serial port with a small BASIC/machine-code loader.
- **Verify:** the dump is correct when it boots your Python emulator to the menu.
  That is a complete functional checksum and you already have it.

## Existing soft cores — honest assessment

I looked specifically for an 8085 core worth reusing. The landscape is poor.

| Core | Language | Assessment |
|---|---|---|
| [scottlbaker/8085-SOC](https://github.com/scottlbaker/8085-SOC) | VHDL | **The most promising candidate.** A real SOC (CPU + UART + timer + I/O) synthesised for iCE40-hx8k, so it is known to build and run somewhere. The README does **not** state instruction-set completeness, RIM/SIM support, TRAP, or the RST 5.5/6.5/7.5 masks — you must read the source to find out. Do that before committing. |
| [debtanu09/my8085](https://github.com/debtanu09/my8085) / [OpenCores my8085light](https://opencores.org/projects/my8085light) | Verilog | **Not usable.** 18 instructions. A teaching exercise. |
| gl85 (Alex Miczo, via OpenCores mirrors) | VHDL, gate-level, Verilog conversions exist | Gate-level model of the 8085. Reported as having incomplete 8085 functionality. Gate-level structure also makes it awkward to instrument for the trace diff you need. |
| [IITG-Microprocessor-8085](https://github.com/gokart23/IITG-Microprocessor-8085) | VHDL | 8085-*inspired* with a reduced instruction set. Not the real thing. |
| light8080 (OpenCores), T80 (Z80) | VHDL | 8080 and Z80 respectively. Would need 8085 additions (RIM/SIM, the extra interrupts) and, in T80's case, careful attention to where Z80 flag behaviour differs from 8080/8085. |
| [OpenCores soft-core inventory](https://opencores.org/projects/up_core_list) | — | Useful for a last sweep, but I did not find an 8085 in it that changes the picture above. |

**The conclusion that matters:** there is no well-tested, complete, known-good
open 8085 core the way there is for the Z80 or 6502. Weigh that against the fact
that you have already written a working 8085 in `m100/cpu85.py` that runs the
real ROM. See `06-decisions.md`, decision 1.

## Prior art worth reading before you start

| Project | Why |
|---|---|
| [osresearch/model100](https://github.com/osresearch/model100) — "Model iCE100" | Someone else's FPGA board for this exact panel and keyboard. Connector pinout, charge-pump approach, keyboard matrix notes. Closest thing to a reference design you will find. |
| [trmm.net Model 100 writeup](https://trmm.net/TRS80_Model_100/) | The Teensy++ retrofit that preceded it, including the two-diode/two-capacitor PWM charge pump for bias. **403 to me; read in a browser.** |
| [NYC Resistor: TRS-80 Model 100 upgrade](https://www.nycresistor.com/2013/01/06/trs80-model100-upgrade/) and [Hackaday coverage](https://hackaday.com/2013/01/07/building-a-new-motherboard-for-a-trs-80/) | Context and photos of the same surgery you are planning. |
| **This repository** | `m100/lcd.py`, `machine.py`, `keyboard.py`, `cpu85.py` are your specification and your oracle. Do not underrate this — most people doing this project have nothing equivalent. |
