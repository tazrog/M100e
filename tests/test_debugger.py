"""Tests for the debugger: the disassembler, breakpoint-aware CPU stepping,
and Machine.step_instruction()."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from m100.cpu85 import CPU8085
from m100.disasm import disasm_one
from m100.config import Config
from m100.machine import Machine, CPU_HZ
from m100 import rom

RESULTS = []


def t(name, cond, detail=""):
    print("  %-52s %s %s" % (name, "ok" if cond else "FAIL", detail))
    RESULTS.append(cond)


class FlatMachine:
    """Bare CPU + flat 64K RAM, no I/O devices - enough to exercise the
    core and the disassembler without booting the ROM."""

    def __init__(self):
        self.mem = bytearray(0x10000)
        self.cpu = CPU8085(self.rd, self.wr, self.inp, self.outp)

    def rd(self, a):
        return self.mem[a]

    def wr(self, a, v):
        self.mem[a] = v

    def inp(self, p):
        return 0xFF

    def outp(self, p, v):
        pass

    def load(self, addr, code):
        self.mem[addr:addr + len(code)] = bytes(code)


def test_disasm_basic():
    m = FlatMachine()
    m.load(0, [
        0x00,                    # NOP
        0x3E, 0x55,              # MVI A,55H
        0x21, 0x34, 0x12,        # LXI H,1234H
        0x7D,                    # MOV A,L
        0xC3, 0x00, 0x00,        # JMP 0000H
        0xCD, 0xAD, 0xDE,        # CALL DEADH
        0xC5,                    # PUSH B
        0xE6, 0x0F,              # ANI 0FH
        0xC7,                    # RST 0
    ])
    cases = [
        (0, 1, "NOP"),
        (1, 2, "MVI A,55H"),
        (3, 3, "LXI H,1234H"),
        (6, 1, "MOV A,L"),
        (7, 3, "JMP 0000H"),
        (10, 3, "CALL DEADH"),
        (13, 1, "PUSH B"),
        (14, 2, "ANI 0FH"),
        (16, 1, "RST 0"),
    ]
    for addr, exp_len, exp_text in cases:
        length, text = disasm_one(m.rd, addr)
        t("disasm @%d -> %r" % (addr, exp_text),
          length == exp_len and text == exp_text,
          "got (%d, %r)" % (length, text))


def test_disasm_undocumented_is_nop():
    m = FlatMachine()
    m.load(0, [0x08, 0x76])  # unassigned slot (DSUB in real hardware), HLT
    length, text = disasm_one(m.rd, 0)
    t("undoc opcode disassembles with a note",
      length == 1 and "DSUB" in text and "NOP" in text, repr(text))
    c = m.cpu
    c.run(c.cycles + 1)
    t("undoc opcode actually executes as NOP (PC advances by 1)",
      c.pc == 1)


def test_cpu_breakpoints():
    m = FlatMachine()
    # 0: NOP  1: NOP  2: NOP  3: HLT
    m.load(0, [0x00, 0x00, 0x00, 0x76])
    c = m.cpu
    hit = c.run(c.cycles + 1000, breakpoints={2})
    t("run() stops exactly at the breakpoint address", hit and c.pc == 2)
    t("breakpoint didn't execute past itself", c.cycles == 8)  # 2 NOPs @ 4T

    # resuming must not immediately retrigger the same breakpoint
    hit2 = c.run(c.cycles + 1000, breakpoints={2})
    t("resuming from a breakpoint doesn't instantly retrigger it",
      not hit2 and c.halted)


def fresh_machine(cfg=None, ram=32768):
    cfg = cfg or Config()
    cfg["ram_size"] = ram
    m = Machine(rom.get_system_rom(cfg), cfg)
    m.run_cycles(CPU_HZ * 2)
    return m


def test_machine_breakpoints_and_step():
    m = fresh_machine()
    # Point PC at a tiny scripted program in RAM instead of relying on
    # wherever the real ROM's boot code happens to be executing - this
    # only needs to prove Machine wires breakpoints/step through to the
    # CPU core correctly, not exercise ROM control flow.
    addr = 0x9000
    for i, b in enumerate([0x00, 0x00, 0x00, 0x76]):  # NOP NOP NOP HLT
        m.write(addr + i, b)
    m.cpu.pc = addr
    m.cpu.halted = False

    bp = addr + 2
    hit = m.run_cycles(CPU_HZ, breakpoints={bp})
    t("Machine.run_cycles honors breakpoints", hit and m.cpu.pc == bp,
      "pc=%04X" % m.cpu.pc)

    cycles_before = m.cpu.cycles
    m.step_instruction()
    t("step_instruction executes exactly one instruction",
      m.cpu.pc == bp + 1 and m.cpu.cycles > cycles_before)


def main():
    test_disasm_basic()
    test_disasm_undocumented_is_nop()
    test_cpu_breakpoints()
    test_machine_breakpoints_and_step()
    print("PASS" if all(RESULTS) else "FAIL")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
