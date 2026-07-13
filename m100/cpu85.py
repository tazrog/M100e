"""Intel 80C85 CPU core.

The Model 100 runs an 80C85 at 2.4576 MHz.  This core implements the full
documented 8085 instruction set (including RIM/SIM and the RST 5.5/6.5/7.5
interrupt system) with per-opcode cycle counts.  Opcode handlers are
generated as small standalone functions at import time so the dispatch loop
stays fast enough to run the machine at real speed in pure Python.

Flag storage: fs/fz/fa/fp/fc are kept as separate 0/1 ints and only packed
into the PSW byte for PUSH PSW / POP PSW.
"""

# Precomputed sign / zero / parity lookup tables.
FS = [1 if i & 0x80 else 0 for i in range(256)]
FZ = [1 if i == 0 else 0 for i in range(256)]
FP = [(bin(i).count("1") & 1) ^ 1 for i in range(256)]

# Interrupt vectors.
VEC_TRAP = 0x24
VEC_55 = 0x2C
VEC_65 = 0x34
VEC_75 = 0x3C

_REG = {0: "b", 1: "c", 2: "d", 3: "e", 4: "h", 5: "l", 7: "a"}
_SZP = "s.fs=FS[a];s.fz=FZ[a];s.fp=FP[a]"


def _gen_source():
    """Generate the source text for all 256 opcode handler functions."""
    src = []
    names = ["_bad"] * 256

    def emit(op, cycles, body):
        fn = "op_%02x" % op
        names[op] = fn
        lines = ["def %s(s):" % fn]
        for ln in body:
            lines.append("    " + ln)
        lines.append("    return %d" % cycles)
        src.append("\n".join(lines))

    def fetch8():
        return ["v = s.rd(s.pc)", "s.pc = (s.pc + 1) & 0xFFFF"]

    def fetch16():
        return [
            "lo = s.rd(s.pc)",
            "hi = s.rd((s.pc + 1) & 0xFFFF)",
            "s.pc = (s.pc + 2) & 0xFFFF",
            "ad = (hi << 8) | lo",
        ]

    # ---- data movement ------------------------------------------------
    for dst in range(8):
        for srcr in range(8):
            op = 0x40 | (dst << 3) | srcr
            if op == 0x76:  # HLT
                continue
            if dst == 6 and srcr == 6:
                continue
            if dst == 6:
                emit(op, 7, ["s.wr((s.h << 8) | s.l, s.%s)" % _REG[srcr]])
            elif srcr == 6:
                emit(op, 7, ["s.%s = s.rd((s.h << 8) | s.l)" % _REG[dst]])
            else:
                emit(op, 4, ["s.%s = s.%s" % (_REG[dst], _REG[srcr])])

    for dst in range(8):  # MVI
        op = 0x06 | (dst << 3)
        if dst == 6:
            emit(op, 10, fetch8() + ["s.wr((s.h << 8) | s.l, v)"])
        else:
            emit(op, 7, fetch8() + ["s.%s = v" % _REG[dst]])

    for i, (hi, lo) in enumerate((("b", "c"), ("d", "e"), ("h", "l"))):
        emit(0x01 | (i << 4), 10, fetch16() + ["s.%s = hi; s.%s = lo" % (hi, lo)])
    emit(0x31, 10, fetch16() + ["s.sp = ad"])

    emit(0x0A, 7, ["s.a = s.rd((s.b << 8) | s.c)"])  # LDAX B
    emit(0x1A, 7, ["s.a = s.rd((s.d << 8) | s.e)"])  # LDAX D
    emit(0x02, 7, ["s.wr((s.b << 8) | s.c, s.a)"])   # STAX B
    emit(0x12, 7, ["s.wr((s.d << 8) | s.e, s.a)"])   # STAX D
    emit(0x3A, 13, fetch16() + ["s.a = s.rd(ad)"])   # LDA
    emit(0x32, 13, fetch16() + ["s.wr(ad, s.a)"])    # STA
    emit(0x2A, 16, fetch16() + [                     # LHLD
        "s.l = s.rd(ad)",
        "s.h = s.rd((ad + 1) & 0xFFFF)",
    ])
    emit(0x22, 16, fetch16() + [                     # SHLD
        "s.wr(ad, s.l)",
        "s.wr((ad + 1) & 0xFFFF, s.h)",
    ])
    emit(0xEB, 4, ["s.h, s.d = s.d, s.h", "s.l, s.e = s.e, s.l"])  # XCHG
    emit(0xE3, 16, [                                 # XTHL
        "lo = s.rd(s.sp); hi = s.rd((s.sp + 1) & 0xFFFF)",
        "s.wr(s.sp, s.l); s.wr((s.sp + 1) & 0xFFFF, s.h)",
        "s.l = lo; s.h = hi",
    ])
    emit(0xF9, 6, ["s.sp = (s.h << 8) | s.l"])       # SPHL
    emit(0xE9, 6, ["s.pc = (s.h << 8) | s.l"])       # PCHL

    # ---- arithmetic / logic -------------------------------------------
    def rd_src(srcr):
        if srcr == 6:
            return ["v = s.rd((s.h << 8) | s.l)"]
        return ["v = s.%s" % _REG[srcr]]

    def add_body(carry_in):
        return [
            "r = s.a + v" + (" + s.fc" if carry_in else ""),
            "s.fa = 1 if ((s.a ^ v ^ r) & 0x10) else 0",
            "s.fc = r >> 8",
            "a = r & 0xFF",
            "s.a = a; " + _SZP,
        ]

    def sub_body(borrow_in, keep):
        body = [
            "v ^= 0xFF",
            "r = s.a + v + " + ("(1 - s.fc)" if borrow_in else "1"),
            "s.fa = 1 if ((s.a ^ v ^ r) & 0x10) else 0",
            "s.fc = 1 - (r >> 8)",
            "a = r & 0xFF",
        ]
        body.append(("s.a = a; " if keep else "") + _SZP)
        return body

    logic = {
        0xA0: ["s.fa = 1 if ((s.a | v) & 0x08) else 0", "a = s.a & v",
               "s.a = a; s.fc = 0; " + _SZP],                       # ANA
        0xA8: ["a = s.a ^ v", "s.a = a; s.fc = 0; s.fa = 0; " + _SZP],  # XRA
        0xB0: ["a = s.a | v", "s.a = a; s.fc = 0; s.fa = 0; " + _SZP],  # ORA
    }
    for srcr in range(8):
        cyc = 7 if srcr == 6 else 4
        emit(0x80 | srcr, cyc, rd_src(srcr) + add_body(False))       # ADD
        emit(0x88 | srcr, cyc, rd_src(srcr) + add_body(True))        # ADC
        emit(0x90 | srcr, cyc, rd_src(srcr) + sub_body(False, True))  # SUB
        emit(0x98 | srcr, cyc, rd_src(srcr) + sub_body(True, True))   # SBB
        emit(0xB8 | srcr, cyc, rd_src(srcr) + sub_body(False, False))  # CMP
        for base, body in logic.items():
            emit(base | srcr, cyc, rd_src(srcr) + body)

    # Immediate versions: ADI ACI SUI SBI ANI XRI ORI CPI
    emit(0xC6, 7, fetch8() + add_body(False))
    emit(0xCE, 7, fetch8() + add_body(True))
    emit(0xD6, 7, fetch8() + sub_body(False, True))
    emit(0xDE, 7, fetch8() + sub_body(True, True))
    emit(0xE6, 7, fetch8() + logic[0xA0])
    emit(0xEE, 7, fetch8() + logic[0xA8])
    emit(0xF6, 7, fetch8() + logic[0xB0])
    emit(0xFE, 7, fetch8() + sub_body(False, False))

    for dst in range(8):  # INR / DCR
        inr = [
            "a = (v + 1) & 0xFF",
            "s.fa = 1 if (a & 0x0F) == 0 else 0",
            _SZP,
        ]
        dcr = [
            "a = (v - 1) & 0xFF",
            "s.fa = 0 if (a & 0x0F) == 0x0F else 1",
            _SZP,
        ]
        if dst == 6:
            pre = ["hl = (s.h << 8) | s.l", "v = s.rd(hl)"]
            emit(0x04 | (dst << 3), 10, pre + inr + ["s.wr(hl, a)"])
            emit(0x05 | (dst << 3), 10, pre + dcr + ["s.wr(hl, a)"])
        else:
            r = _REG[dst]
            emit(0x04 | (dst << 3), 4, ["v = s.%s" % r] + inr + ["s.%s = a" % r])
            emit(0x05 | (dst << 3), 4, ["v = s.%s" % r] + dcr + ["s.%s = a" % r])

    for i, (hi, lo) in enumerate((("b", "c"), ("d", "e"), ("h", "l"))):
        emit(0x03 | (i << 4), 6, [  # INX
            "v = (((s.%s << 8) | s.%s) + 1) & 0xFFFF" % (hi, lo),
            "s.%s = v >> 8; s.%s = v & 0xFF" % (hi, lo),
        ])
        emit(0x0B | (i << 4), 6, [  # DCX
            "v = (((s.%s << 8) | s.%s) - 1) & 0xFFFF" % (hi, lo),
            "s.%s = v >> 8; s.%s = v & 0xFF" % (hi, lo),
        ])
        emit(0x09 | (i << 4), 10, [  # DAD
            "r = ((s.h << 8) | s.l) + ((s.%s << 8) | s.%s)" % (hi, lo),
            "s.fc = r >> 16",
            "s.h = (r >> 8) & 0xFF; s.l = r & 0xFF",
        ])
    emit(0x33, 6, ["s.sp = (s.sp + 1) & 0xFFFF"])
    emit(0x3B, 6, ["s.sp = (s.sp - 1) & 0xFFFF"])
    emit(0x39, 10, [
        "r = ((s.h << 8) | s.l) + s.sp",
        "s.fc = r >> 16",
        "s.h = (r >> 8) & 0xFF; s.l = r & 0xFF",
    ])

    # ---- rotates, accumulator specials --------------------------------
    emit(0x07, 4, ["s.fc = s.a >> 7", "s.a = ((s.a << 1) | s.fc) & 0xFF"])  # RLC
    emit(0x0F, 4, ["s.fc = s.a & 1", "s.a = (s.a >> 1) | (s.fc << 7)"])     # RRC
    emit(0x17, 4, ["c = s.a >> 7", "s.a = ((s.a << 1) | s.fc) & 0xFF",
                   "s.fc = c"])                                             # RAL
    emit(0x1F, 4, ["c = s.a & 1", "s.a = (s.a >> 1) | (s.fc << 7)",
                   "s.fc = c"])                                             # RAR
    emit(0x2F, 4, ["s.a ^= 0xFF"])                                          # CMA
    emit(0x37, 4, ["s.fc = 1"])                                             # STC
    emit(0x3F, 4, ["s.fc ^= 1"])                                            # CMC
    emit(0x27, 4, [                                                         # DAA
        "add = 0; c = s.fc",
        "if (s.a & 0x0F) > 9 or s.fa: add = 0x06",
        "if (s.a >> 4) > 9 or s.fc or ((s.a >> 4) >= 9 and (s.a & 0x0F) > 9):",
        "    add |= 0x60; c = 1",
        "r = s.a + add",
        "s.fa = 1 if ((s.a ^ add ^ r) & 0x10) else 0",
        "a = r & 0xFF",
        "s.a = a; s.fc = c; " + _SZP,
    ])

    # ---- stack ----------------------------------------------------------
    for i, (hi, lo) in enumerate((("b", "c"), ("d", "e"), ("h", "l"))):
        emit(0xC5 | (i << 4), 13, [
            "s.sp = (s.sp - 2) & 0xFFFF",
            "s.wr(s.sp, s.%s); s.wr((s.sp + 1) & 0xFFFF, s.%s)" % (lo, hi),
        ])
        emit(0xC1 | (i << 4), 10, [
            "s.%s = s.rd(s.sp); s.%s = s.rd((s.sp + 1) & 0xFFFF)" % (lo, hi),
            "s.sp = (s.sp + 2) & 0xFFFF",
        ])
    emit(0xF5, 13, [  # PUSH PSW
        "f = (s.fs << 7) | (s.fz << 6) | (s.fa << 4) | (s.fp << 2) | 2 | s.fc",
        "s.sp = (s.sp - 2) & 0xFFFF",
        "s.wr(s.sp, f); s.wr((s.sp + 1) & 0xFFFF, s.a)",
    ])
    emit(0xF1, 10, [  # POP PSW
        "f = s.rd(s.sp); s.a = s.rd((s.sp + 1) & 0xFFFF)",
        "s.sp = (s.sp + 2) & 0xFFFF",
        "s.fs = (f >> 7) & 1; s.fz = (f >> 6) & 1; s.fa = (f >> 4) & 1",
        "s.fp = (f >> 2) & 1; s.fc = f & 1",
    ])

    # ---- control flow ---------------------------------------------------
    conds = ["not s.fz", "s.fz", "not s.fc", "s.fc",
             "not s.fp", "s.fp", "not s.fs", "s.fs"]
    emit(0xC3, 10, fetch16() + ["s.pc = ad"])  # JMP
    emit(0xC9, 10, [                            # RET
        "s.pc = s.rd(s.sp) | (s.rd((s.sp + 1) & 0xFFFF) << 8)",
        "s.sp = (s.sp + 2) & 0xFFFF",
    ])
    emit(0xCD, 18, fetch16() + [                # CALL
        "s.sp = (s.sp - 2) & 0xFFFF",
        "s.wr(s.sp, s.pc & 0xFF); s.wr((s.sp + 1) & 0xFFFF, s.pc >> 8)",
        "s.pc = ad",
    ])
    for i, cond in enumerate(conds):
        emit(0xC2 | (i << 3), 7, fetch16() + [  # Jcond (10 taken / 7 not)
            "if %s:" % cond,
            "    s.pc = ad",
            "    return 10",
        ])
        emit(0xC4 | (i << 3), 9, fetch16() + [  # Ccond (18 / 9)
            "if %s:" % cond,
            "    s.sp = (s.sp - 2) & 0xFFFF",
            "    s.wr(s.sp, s.pc & 0xFF); s.wr((s.sp + 1) & 0xFFFF, s.pc >> 8)",
            "    s.pc = ad",
            "    return 18",
        ])
        emit(0xC0 | (i << 3), 6, [              # Rcond (12 / 6)
            "if %s:" % cond,
            "    s.pc = s.rd(s.sp) | (s.rd((s.sp + 1) & 0xFFFF) << 8)",
            "    s.sp = (s.sp + 2) & 0xFFFF",
            "    return 12",
        ])
    for n in range(8):  # RST n
        emit(0xC7 | (n << 3), 12, [
            "s.sp = (s.sp - 2) & 0xFFFF",
            "s.wr(s.sp, s.pc & 0xFF); s.wr((s.sp + 1) & 0xFFFF, s.pc >> 8)",
            "s.pc = %d" % (n * 8),
        ])

    # ---- I/O, interrupts, misc -------------------------------------------
    emit(0x00, 4, ["pass"])  # NOP
    emit(0x76, 5, ["s.halted = True"])  # HLT
    emit(0xDB, 10, fetch8() + ["s.a = s.inp(v)"])       # IN
    emit(0xD3, 10, fetch8() + ["s.outp(v, s.a)"])       # OUT
    emit(0xF3, 4, ["s.ie = 0"])                          # DI
    emit(0xFB, 4, ["s.ie = 1"])                          # EI
    emit(0x20, 4, [                                      # RIM
        "s.a = ((s.sid << 7) | (s.p75 << 6) | (s.line65 << 5) |"
        " (s.line55 << 4) | (s.ie << 3) | (s.m75 << 2) | (s.m65 << 1) | s.m55)",
    ])
    emit(0x30, 4, [                                      # SIM
        "v = s.a",
        "if v & 0x08:",
        "    s.m55 = v & 1; s.m65 = (v >> 1) & 1; s.m75 = (v >> 2) & 1",
        "if v & 0x10:",
        "    s.p75 = 0",
        "if v & 0x40:",
        "    s.sod = (v >> 7) & 1",
        "s.update_irq()",
    ])

    # Remaining unassigned opcodes (8085 undocumented) behave as NOPs here;
    # the Model 100 ROM never executes them.
    for op in range(256):
        if names[op] == "_bad":
            emit(op, 4, ["pass"])

    return "\n\n".join(src), names


_source, _names = _gen_source()
_ns = {"FS": FS, "FZ": FZ, "FP": FP}
exec(compile(_source, "<cpu85-ops>", "exec"), _ns)
OPS = tuple(_ns[n] for n in _names)


class CPU8085:
    __slots__ = (
        "a", "b", "c", "d", "e", "h", "l", "sp", "pc",
        "fs", "fz", "fa", "fp", "fc",
        "ie", "m55", "m65", "m75", "p75", "line55", "line65",
        "sid", "sod", "halted", "cycles", "irq",
        "rd", "wr", "inp", "outp",
    )

    def __init__(self, rd, wr, inp, outp):
        self.rd = rd
        self.wr = wr
        self.inp = inp
        self.outp = outp
        self.cycles = 0
        self.reset()

    def reset(self):
        self.a = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.pc = 0
        self.sp = 0
        self.fs = self.fz = self.fa = self.fp = self.fc = 0
        self.ie = 0
        self.m55 = self.m65 = self.m75 = 1  # all maskable ints masked at reset
        self.p75 = 0
        self.line55 = self.line65 = 0
        self.sid = 0
        self.sod = 0
        self.halted = False
        self.irq = False

    # -- interrupt lines --------------------------------------------------
    def update_irq(self):
        self.irq = bool(
            (self.p75 and not self.m75)
            or (self.line65 and not self.m65)
            or (self.line55 and not self.m55)
        )

    def pulse_rst75(self):
        """Rising edge on RST7.5 (edge-triggered, latched)."""
        self.p75 = 1
        self.update_irq()

    def set_line65(self, level):
        """RST6.5 is level-triggered (UART character ready)."""
        self.line65 = 1 if level else 0
        self.update_irq()

    def set_line55(self, level):
        self.line55 = 1 if level else 0
        self.update_irq()

    def _service_interrupt(self):
        self.ie = 0
        self.halted = False
        self.sp = (self.sp - 2) & 0xFFFF
        self.wr(self.sp, self.pc & 0xFF)
        self.wr((self.sp + 1) & 0xFFFF, self.pc >> 8)
        if self.p75 and not self.m75:
            self.p75 = 0
            self.pc = VEC_75
        elif self.line65 and not self.m65:
            self.pc = VEC_65
        else:
            self.pc = VEC_55
        self.update_irq()
        self.cycles += 12

    # -- main loop ----------------------------------------------------------
    def run(self, target_cycles, breakpoints=None):
        """Execute until self.cycles >= target_cycles, or (if breakpoints is
        given) until the PC lands on one of those addresses - checked before
        every instruction after the first, so resuming from a breakpoint
        doesn't immediately retrigger it.  Returns True if it stopped on a
        breakpoint, False if it ran out the clock (or halted)."""
        ops = OPS
        rd = self.rd
        first = True
        while self.cycles < target_cycles:
            if self.irq:
                if self.ie:
                    self._service_interrupt()
                elif self.halted:
                    self.halted = False
            if self.halted:
                self.cycles = target_cycles
                return False
            if breakpoints and not first and self.pc in breakpoints:
                return True
            first = False
            op = rd(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.cycles += ops[op](self)
        return False
