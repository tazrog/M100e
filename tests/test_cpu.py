"""Self-tests for the 8085 core: hand-verified instruction sequences."""

import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from m100.cpu85 import CPU8085


class FlatMachine:
    def __init__(self):
        self.mem = bytearray(0x10000)
        self.io = {}
        self.cpu = CPU8085(self.rd, self.wr, self.inp, self.outp)

    def rd(self, a):
        return self.mem[a]

    def wr(self, a, v):
        self.mem[a] = v

    def inp(self, p):
        return self.io.get(p, 0xFF)

    def outp(self, p, v):
        self.io[p] = v

    def load(self, addr, code):
        self.mem[addr:addr + len(code)] = bytes(code)

    def run_until_halt(self, max_cycles=1_000_000):
        c = self.cpu
        while not c.halted and c.cycles < max_cycles:
            c.run(c.cycles + 100)
        assert c.halted, "program did not halt"


def t(name, cond):
    status = "ok" if cond else "FAIL"
    print(f"  {name:<44s} {status}")
    return cond


def main():
    ok = True

    # --- basic arithmetic and flags ---
    m = FlatMachine()
    m.load(0, [0x3E, 0x3C,        # MVI A,3Ch
               0x06, 0x69,        # MVI B,69h
               0x80,              # ADD B  -> A5h, S=1 Z=0 AC=1 P=1 CY=0
               0x76])
    m.run_until_halt()
    c = m.cpu
    ok &= t("ADD result", c.a == 0xA5)
    ok &= t("ADD flags", (c.fs, c.fz, c.fa, c.fp, c.fc) == (1, 0, 1, 1, 0))

    # --- subtract / compare / borrow ---
    m = FlatMachine()
    m.load(0, [0x3E, 0x05,        # MVI A,5
               0xD6, 0x07,        # SUI 7 -> FEh, CY=1 (borrow), S=1
               0xFE, 0xFE,        # CPI FEh -> Z=1, CY=0
               0x76])
    m.run_until_halt()
    c = m.cpu
    ok &= t("SUI borrow", c.a == 0xFE)
    ok &= t("CPI equal", (c.fz, c.fc) == (1, 0))

    # --- DAA BCD addition: 19 + 28 = 47 BCD ---
    m = FlatMachine()
    m.load(0, [0x3E, 0x19, 0xC6, 0x28, 0x27, 0x76])
    m.run_until_halt()
    ok &= t("DAA 19+28=47", m.cpu.a == 0x47 and m.cpu.fc == 0)

    # --- DAA with carry: 91 + 82 = 173 BCD ---
    m = FlatMachine()
    m.load(0, [0x3E, 0x91, 0xC6, 0x82, 0x27, 0x76])
    m.run_until_halt()
    ok &= t("DAA 91+82=73 CY", m.cpu.a == 0x73 and m.cpu.fc == 1)

    # --- rotates ---
    m = FlatMachine()
    m.load(0, [0x3E, 0x81,  # MVI A,81h
               0x07,        # RLC -> 03h CY=1
               0x1F,        # RAR -> 81h CY=1
               0x76])
    m.run_until_halt()
    ok &= t("RLC/RAR", m.cpu.a == 0x81 and m.cpu.fc == 1)

    # --- 16-bit ops, stack, call/ret ---
    m = FlatMachine()
    m.load(0, [0x31, 0x00, 0x20,   # LXI SP,2000h
               0x21, 0x34, 0x12,   # LXI H,1234h
               0x11, 0x11, 0x11,   # LXI D,1111h
               0x19,               # DAD D -> 2345h
               0xE5,               # PUSH H
               0xC1,               # POP B -> BC=2345h
               0xCD, 0x00, 0x01,   # CALL 0100h
               0x76])
    m.load(0x0100, [0x3E, 0x77, 0xC9])  # MVI A,77h ; RET
    m.run_until_halt()
    c = m.cpu
    ok &= t("DAD/PUSH/POP", (c.b, c.c) == (0x23, 0x45))
    ok &= t("CALL/RET", c.a == 0x77 and c.sp == 0x2000)

    # --- memory ops, INR/DCR M, loop ---
    m = FlatMachine()
    m.load(0, [0x21, 0x00, 0x30,   # LXI H,3000h
               0x36, 0x0F,         # MVI M,0Fh
               0x34,               # INR M -> 10h, AC=1
               0x06, 0x05,         # MVI B,5
               0x05,               # loop: DCR B
               0xC2, 0x08, 0x00,   # JNZ loop
               0x76])
    m.run_until_halt()
    ok &= t("INR M", m.mem[0x3000] == 0x10)
    ok &= t("DCR/JNZ loop", m.cpu.b == 0 and m.cpu.fz == 1)

    # --- XCHG / XTHL / conditional flavors ---
    m = FlatMachine()
    m.load(0, [0x31, 0x00, 0x20,   # LXI SP,2000h
               0x21, 0xAA, 0xBB,   # LXI H,BBAAh
               0x11, 0xCC, 0xDD,   # LXI D,DDCCh
               0xEB,               # XCHG: HL=DDCCh DE=BBAAh
               0xE5,               # PUSH H
               0x21, 0x22, 0x11,   # LXI H,1122h
               0xE3,               # XTHL: HL=DDCCh, (SP)=1122h
               0xC1,               # POP B: BC=1122h
               0x76])
    m.run_until_halt()
    c = m.cpu
    ok &= t("XCHG", (c.d, c.e) == (0xBB, 0xAA))
    ok &= t("XTHL", (c.h, c.l) == (0xDD, 0xCC) and (c.b, c.c) == (0x11, 0x22))

    # --- PUSH PSW / POP PSW round trip ---
    m = FlatMachine()
    m.load(0, [0x31, 0x00, 0x20,
               0x3E, 0xFF, 0xC6, 0x01,  # ADD sets Z=1 CY=1 AC=1
               0xF5,                     # PUSH PSW
               0x3E, 0x01, 0xC6, 0x01,   # clobber flags
               0xF1,                     # POP PSW
               0x76])
    m.run_until_halt()
    c = m.cpu
    ok &= t("PSW round trip", (c.fz, c.fc, c.fa) == (1, 1, 1) and c.a == 0x00)

    # --- RST 7.5 interrupt ---
    m = FlatMachine()
    m.load(0, [0x31, 0x00, 0x20,   # LXI SP,2000h
               0x3E, 0x0B,         # MVI A,00001011b (MSE, unmask 7.5)
               0x30,               # SIM
               0xFB,               # EI
               0x00, 0x00,         # NOPs (spin)
               0xC3, 0x07, 0x00])  # JMP 7
    m.load(0x3C, [0x3E, 0x42, 0x76])  # ISR: MVI A,42h ; HLT
    m.cpu.run(m.cpu.cycles + 100)
    m.cpu.pulse_rst75()
    m.run_until_halt()
    ok &= t("RST 7.5 vectored", m.cpu.a == 0x42)

    # --- speed benchmark ---
    m = FlatMachine()
    m.load(0, [0x06, 0x00,          # MVI B,0
               0x0E, 0x00,          # MVI C,0
               0x04,                # loop: INR B
               0xC2, 0x04, 0x00,    # JNZ loop
               0x0C,                # INR C
               0xC2, 0x04, 0x00,    # JNZ loop
               0xC3, 0x04, 0x00])
    start = time.perf_counter()
    m.cpu.run(2_457_600)  # one emulated second
    elapsed = time.perf_counter() - start
    speed = 2_457_600 / elapsed / 1e6
    print(f"  benchmark: 1 emulated second in {elapsed:.2f}s host "
          f"({speed:.2f} emulated MHz)")
    ok &= t("full speed (>=2.4576 MHz)", speed >= 2.4576)

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
