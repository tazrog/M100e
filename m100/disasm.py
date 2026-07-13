"""One-instruction-at-a-time 8085 disassembler, for the debugger overlay.

Encodes the same opcode layout a85.py assembles (mnemonic -> (kind, base
opcode)), just inverted into a 256-entry lookup built once at import time.
Kept independent of a85.py since M100e ships as a standalone emulator.
"""

REG = {0: "B", 1: "C", 2: "D", 3: "E", 4: "H", 5: "L", 6: "M", 7: "A"}
RP_SP = {0: "B", 1: "D", 2: "H", 3: "SP"}
RP_PSW = {0: "B", 1: "D", 2: "H", 3: "PSW"}
RP_LDAX = {0: "B", 1: "D"}

N0 = {
    0x00: "NOP", 0x07: "RLC", 0x0F: "RRC", 0x17: "RAL", 0x1F: "RAR",
    0x20: "RIM", 0x27: "DAA", 0x2F: "CMA", 0x30: "SIM", 0x37: "STC",
    0x3F: "CMC", 0x76: "HLT", 0xC0: "RNZ", 0xC8: "RZ", 0xC9: "RET",
    0xD0: "RNC", 0xD8: "RC", 0xE0: "RPO", 0xE3: "XTHL", 0xE8: "RPE",
    0xE9: "PCHL", 0xEB: "XCHG", 0xF0: "RP", 0xF3: "DI", 0xF8: "RM",
    0xF9: "SPHL", 0xFB: "EI",
}
I8 = {
    0xC6: "ADI", 0xCE: "ACI", 0xD6: "SUI", 0xDE: "SBI",
    0xE6: "ANI", 0xEE: "XRI", 0xF6: "ORI", 0xFE: "CPI",
    0xDB: "IN", 0xD3: "OUT",
}
I16 = {
    0x22: "SHLD", 0x2A: "LHLD", 0x32: "STA", 0x3A: "LDA",
    0xC2: "JNZ", 0xC3: "JMP", 0xCA: "JZ", 0xD2: "JNC", 0xDA: "JC",
    0xE2: "JPO", 0xEA: "JPE", 0xF2: "JP", 0xFA: "JM",
    0xC4: "CNZ", 0xCC: "CZ", 0xCD: "CALL", 0xD4: "CNC", 0xDC: "CC",
    0xE4: "CPO", 0xEC: "CPE", 0xF4: "CP", 0xFC: "CM",
}
R8S = {0x80: "ADD", 0x88: "ADC", 0x90: "SUB", 0x98: "SBB",
       0xA0: "ANA", 0xA8: "XRA", 0xB0: "ORA", 0xB8: "CMP"}
R8D = {0x04: "INR", 0x05: "DCR"}
RPSP = {0x01: "LXI", 0x03: "INX", 0x09: "DAD", 0x0B: "DCX"}
RPPSW = {0xC5: "PUSH", 0xC1: "POP"}
LDAX = {0x02: "STAX", 0x0A: "LDAX"}

# unassigned 8085 opcode slots; this core executes them as plain NOPs
# (see cpu85.py), matching a85.py's --undoc mnemonics for reference only
UNDOC = {0x08: "DSUB", 0x10: "ARHL", 0x18: "RDEL", 0x28: "LDHI",
         0x38: "LDSI", 0xCB: "RSTV", 0xD9: "SHLX", 0xDD: "JNK",
         0xED: "LHLX", 0xFD: "JK"}


def _build():
    # table[opcode] = (format_string, length_in_bytes, immediate_bytes_needed)
    table = [None] * 256
    for op, m in N0.items():
        table[op] = (m, 1, 0)
    for op, m in I8.items():
        table[op] = (m + " %02XH", 2, 1)
    for op, m in I16.items():
        table[op] = (m + " %04XH", 3, 2)
    for base, m in R8S.items():
        for r in range(8):
            table[base | r] = ("%s %s" % (m, REG[r]), 1, 0)
    for base, m in R8D.items():
        for r in range(8):
            table[base | (r << 3)] = ("%s %s" % (m, REG[r]), 1, 0)
    for d in range(8):
        for s in range(8):
            if d == 6 and s == 6:  # 0x76 is HLT, already set via N0
                continue
            table[0x40 | (d << 3) | s] = ("MOV %s,%s" % (REG[d], REG[s]), 1, 0)
    for r in range(8):
        table[0x06 | (r << 3)] = ("MVI %s,%%02XH" % REG[r], 2, 1)
    for base, m in RPSP.items():
        for rp in range(4):
            if m == "LXI":
                table[base | (rp << 4)] = ("LXI %s,%%04XH" % RP_SP[rp], 3, 2)
            else:
                table[base | (rp << 4)] = ("%s %s" % (m, RP_SP[rp]), 1, 0)
    for base, m in RPPSW.items():
        for rp in range(4):
            table[base | (rp << 4)] = ("%s %s" % (m, RP_PSW[rp]), 1, 0)
    for base, m in LDAX.items():
        for rp in range(2):
            table[base | (rp << 4)] = ("%s %s" % (m, RP_LDAX[rp]), 1, 0)
    for n in range(8):
        table[0xC7 | (n << 3)] = ("RST %d" % n, 1, 0)
    for op, m in UNDOC.items():
        table[op] = ("NOP   ; %s (unimplemented, runs as NOP)" % m, 1, 0)
    return table


TABLE = _build()


def disasm_one(read, addr):
    """Disassemble the instruction at addr.  `read` is a byte-at-address
    callable (e.g. Machine.read).  Returns (length_in_bytes, text)."""
    addr &= 0xFFFF
    op = read(addr)
    entry = TABLE[op]
    if entry is None:  # unreachable with a fully-populated table, but safe
        return 1, "DB %02XH" % op
    fmt, length, needs = entry
    if needs == 0:
        return length, fmt
    if needs == 1:
        b0 = read((addr + 1) & 0xFFFF)
        return length, fmt % b0
    b0 = read((addr + 1) & 0xFFFF)
    b1 = read((addr + 2) & 0xFFFF)
    return length, fmt % ((b1 << 8) | b0)
