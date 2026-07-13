"""uPD1990AC real-time clock chip.

The ROM talks to the clock serially through 81C55 Port A: bits 0-2 select
the chip command, bit 3 is the shift clock, bit 4 is serial data in.  The
command is latched when the ROM strobes port 0xE8 bit 2.  Serial data out
is read back on 81C55 Port C bit 0.

The chip holds a 40-bit shift register: seconds, minutes, hours, day of
month (all BCD) and a packed month/day-of-week byte.  There is no year
register - the ROM keeps the year in RAM.  We follow host time plus an
offset that TIME$/DATE$ assignments can adjust.
"""

import time

MODE_HOLD = 0
MODE_SHIFT = 1
MODE_SET = 2
MODE_READ = 3


def _bcd(v):
    return ((v // 10) << 4) | (v % 10)


class UPD1990AC:
    def __init__(self):
        self.mode = MODE_HOLD
        self.sr = [0, 0, 0, 0, 0]  # sec, min, hour, mday, month<<4|wday
        self.serial_out = 0
        self.offset = 0.0  # emulated time - host time

    def now(self):
        return time.localtime(time.time() + self.offset)

    def chip_cmd(self, port_a):
        """Command strobe (port 0xE8 bit 2 rising); port_a bits 0-2 = mode."""
        self.mode = port_a & 0x07
        if self.mode == MODE_SHIFT:
            self.serial_out = self.sr[0] & 1
        elif self.mode == MODE_SET:
            self._apply_set()
        elif self.mode == MODE_READ:
            self._latch_time()

    def clk_pulse(self, port_a):
        """Rising edge on the shift clock (Port A bit 3)."""
        if self.mode != MODE_SHIFT:
            return
        sr = self.sr
        for i in range(4):
            sr[i] = (sr[i] >> 1) | ((sr[i + 1] & 1) << 7)
        sr[4] = (sr[4] >> 1) | (0x80 if port_a & 0x10 else 0)
        self.serial_out = sr[0] & 1

    def _latch_time(self):
        t = self.now()
        self.sr[0] = _bcd(t.tm_sec % 60)
        self.sr[1] = _bcd(t.tm_min)
        self.sr[2] = _bcd(t.tm_hour)
        self.sr[3] = _bcd(t.tm_mday)
        # uPD1990AC day-of-week: 0=Sunday; struct_tm wday: 0=Monday..6=Sunday
        wday = (t.tm_wday + 1) % 7
        self.sr[4] = ((t.tm_mon) << 4) | wday

    def _apply_set(self):
        """TIME$= / DATE$= wrote a new time; keep it as an offset."""
        def unbcd(v):
            return (v >> 4) * 10 + (v & 0x0F)

        # The ROM's cold-boot routine initializes the clock chip to
        # midnight Jan 1.  A real M100 then shows that until the owner sets
        # the time; we keep host time instead and only honor genuine
        # TIME$/DATE$ writes.
        if (self.sr[0] == 0 and self.sr[1] == 0 and self.sr[2] == 0
                and self.sr[3] <= 1 and (self.sr[4] >> 4) <= 1):
            self.offset = 0.0
            return
        try:
            sec = unbcd(self.sr[0])
            minute = unbcd(self.sr[1])
            hour = unbcd(self.sr[2])
            mday = unbcd(self.sr[3])
            month = self.sr[4] >> 4
            host = time.localtime()
            new = time.mktime((host.tm_year, month or host.tm_mon, mday or 1,
                               hour, minute, sec, 0, 0, -1))
            self.offset = new - time.time()
        except (ValueError, OverflowError):
            self.offset = 0.0
