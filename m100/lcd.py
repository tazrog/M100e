"""The Model 100 LCD: ten HD44102 driver chips behind a 240x64 panel.

Each driver owns a 50-column x 4-page (8 pixels per page) region; drivers
0-4 cover the top 32 pixel rows left to right, drivers 5-9 the bottom 32.
The rightmost driver of each half only shows 40 of its 50 columns.

The CPU addresses the drivers through chip-select lines wired to 81C55
Port A bits 0-7 (CS1-8) and Port B bits 0-1 (CS9-10); several drivers can
be selected at once (the ROM clears the screen that way).  I/O port
0xF0-0xFE even = instruction/pointer register, odd = display data.

A pointer byte is page<<6 | column.  Writing a value whose low 6 bits are
< 50 sets the pointer ("fresh", so the next read is a set-up read that
does not advance it); otherwise it is a command - the only one that
matters for the panel image is 0x3E|page<<6 which selects the page shown
on the top row (hardware scrolling).
"""

WIDTH = 240
HEIGHT = 64


class LCD:
    def __init__(self):
        self.ram = [bytearray(256) for _ in range(10)]
        self.ptr = [0] * 10
        self.fresh = [False] * 10
        self.top = [0] * 10
        self.cs = 0  # 10-bit chip select mask
        self.dirty = True

    def reset(self):
        for r in self.ram:
            r[:] = bytes(256)
        self.ptr = [0] * 10
        self.fresh = [False] * 10
        self.top = [0] * 10
        self.dirty = True

    def set_cs(self, bits):
        self.cs = bits & 0x3FF

    def write_instruction(self, val):
        cs = self.cs
        if not cs:
            return
        for c in range(10):
            if cs & (1 << c):
                if (val & 0x3F) < 50:
                    self.ptr[c] = val
                    self.fresh[c] = True
                else:
                    cmd = val & 0x3F
                    if cmd == 0x3E:  # display start page
                        if self.top[c] != val >> 6:
                            self.top[c] = val >> 6
                            self.dirty = True

    def write_data(self, val):
        cs = self.cs
        if not cs:
            return
        for c in range(10):
            if cs & (1 << c):
                p = self.ptr[c]
                if (p & 0x3F) < 50:
                    if self.ram[c][p] != val:
                        self.ram[c][p] = val
                        self.dirty = True
                    p += 1
                    if (p & 0x3F) > 50:
                        p &= 0xC0
                    self.ptr[c] = p
                    self.fresh[c] = False

    def read_data(self):
        cs = self.cs
        for c in range(10):
            if cs & (1 << c):
                p = self.ptr[c]
                ret = self.ram[c][p]
                if not self.fresh[c]:
                    self.ptr[c] = (p + 1) & 0xFF
                self.fresh[c] = False
                return ret
        return 0

    def read_status(self):
        return 0x40  # never busy, counting up

    def pixels(self):
        """Render to a flat bytearray[240*64] of 0/1, row-major."""
        buf = bytearray(WIDTH * HEIGHT)
        for c in range(10):
            ram = self.ram[c]
            x0 = (c % 5) * 50
            ybase = 32 if c >= 5 else 0
            top = self.top[c]
            ncols = 40 if c in (4, 9) else 50
            for page in range(4):
                y0 = ybase + ((page - top) & 3) * 8
                base = page << 6
                row = y0 * WIDTH + x0
                for col in range(ncols):
                    v = ram[base + col]
                    if v:
                        x = row + col
                        if v & 0x01:
                            buf[x] = 1
                        if v & 0x02:
                            buf[x + WIDTH] = 1
                        if v & 0x04:
                            buf[x + 2 * WIDTH] = 1
                        if v & 0x08:
                            buf[x + 3 * WIDTH] = 1
                        if v & 0x10:
                            buf[x + 4 * WIDTH] = 1
                        if v & 0x20:
                            buf[x + 5 * WIDTH] = 1
                        if v & 0x40:
                            buf[x + 6 * WIDTH] = 1
                        if v & 0x80:
                            buf[x + 7 * WIDTH] = 1
        return buf
