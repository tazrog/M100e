"""The Model 100 system: memory map, I/O ports, interrupts, scheduling.

Memory map:
  0x0000-0x7FFF  32K system ROM, bank-switched with the option ROM socket
                 (I/O port 0xE8 bit 0)
  0x8000-0xFFFF  battery-backed RAM; 8/16/24/32K populated from the top down

I/O ports (each decoded in blocks of 16):
  0xA0  modem control: bit0 phone relay, bit1 modem enable
  0xB8  81C55 PIO: B8 command, B9 Port A (LCD CS1-8 / keyboard strobe / RTC
        control lines), BA Port B (bit0 kbd col 9 + LCD CS9, bit1 LCD CS10,
        bit2 beeper source, bit3 modem/RS232 select, bit4 power off,
        bit5 beeper data, bit6 ~DTR, bit7 ~RTS), BB Port C (in: bit0 RTC
        data out, bit1 printer ~busy, bit4 ~CTS, bit5 ~DSR),
        BC/BD timer count (UART 16x baud clock: baud = 153600/count)
  0xC8  UART data
  0xD8  UART/modem status (in), UART word format (out)
  0xE8  in: keyboard rows;  out: bit0 ROM select, bit1 ~printer strobe,
        bit2 RTC command strobe, bit3 cassette remote
  0xF0-0xFF  LCD: even = instruction, odd = data

Interrupts: RST 7.5 = 250 Hz system tick, RST 6.5 = UART receive.
"""

import time

from .config import RAM_IMAGE
from .cpu85 import CPU8085
from .keyboard import Keyboard
from .lcd import LCD
from .rtc import UPD1990AC
from .uart import SerialSystem

CPU_HZ = 2457600
RST75_PERIOD = 9830      # 2457600 / 9830 ~ 250 Hz background tick
SERIAL_SLICE = 1024      # how often the serial system gets polled

ROM_SIZE = 0x8000
ADDR_YEAR = 0xF92D       # ROM keeps the year here (binary ones/tens digits)
ADDR_LCD_TEXT = 0xFE00   # 40x8 character shadow of the screen


class Machine:
    def __init__(self, rom_data, config, on_status=None):
        self.config = config
        self.on_status = on_status or (lambda msg: None)
        self.rom = bytearray(rom_data)
        self.optrom = bytearray(b"\xFF" * ROM_SIZE)
        self.optrom_loaded = False
        self.lo = self.rom  # currently mapped 0x0000-0x7FFF bank

        self.ram = bytearray(0x8000)
        self.ram_base = 0x8000
        self.set_ram_size(config["ram_size"], clear=True)

        self.lcd = LCD()
        self.kbd = Keyboard()
        self.rtc = UPD1990AC()
        self.cpu = CPU8085(self.read, self.write, self.io_in, self.io_out)
        self.serial = SerialSystem(config, self.cpu.set_line65, on_status)
        self.sound = None  # beeper, attached by the UI when audio is up

        # 81C55 and misc latches
        self.pa = 0
        self.pb = 0
        self.e8 = 0
        self.timer_count = 0
        self.timer_running = False

        self.next_rst75 = RST75_PERIOD
        self.next_serial = SERIAL_SLICE
        self.powered_off = False
        self._year_poked = False
        self._boot_cycle = 0

    # ------------------------------------------------------------------ RAM
    def set_ram_size(self, size, clear=False):
        assert size in (8192, 16384, 24576, 32768)
        self.ram_base = 0x10000 - size
        if clear:
            self.ram[:] = bytes(0x8000)
        # unpopulated space reads 0xFF like a floating bus
        for i in range(self.ram_base - 0x8000):
            self.ram[i] = 0xFF

    def load_ram_image(self):
        try:
            data = RAM_IMAGE.read_bytes()
        except OSError:
            return False
        if len(data) != 0x8000:
            return False
        self.ram[:] = data
        for i in range(self.ram_base - 0x8000):
            self.ram[i] = 0xFF
        return True

    def save_ram_image(self):
        try:
            RAM_IMAGE.write_bytes(bytes(self.ram))
        except OSError as e:
            self.on_status("could not save RAM image: %s" % e)

    # --------------------------------------------------------------- memory
    def read(self, a):
        if a < 0x8000:
            return self.lo[a]
        return self.ram[a - 0x8000]

    def write(self, a, v):
        if a >= self.ram_base:
            self.ram[a - 0x8000] = v

    # ------------------------------------------------------------------ I/O
    def io_out(self, port, val):
        hi = port & 0xF0
        if hi == 0xF0:
            if port & 1:
                self.lcd.write_data(val)
            else:
                self.lcd.write_instruction(val)
        elif hi == 0xB0:
            reg = port & 0x07
            if reg == 1:  # Port A
                old = self.pa
                self.pa = val
                self.lcd.set_cs(((self.pb & 0x03) << 8) | val)
                if (val & 0x08) and not (old & 0x08):
                    self.rtc.clk_pulse(val)
            elif reg == 2:  # Port B
                old = self.pb
                self.pb = val
                self.lcd.set_cs(((val & 0x03) << 8) | self.pa)
                self.serial.select_modem(bool(val & 0x08))
                if self.sound:
                    self.sound.port_b(old, val, self.timer_count,
                                      self.timer_running, self.cpu.cycles)
                if (val & 0x10) and not (old & 0x10):
                    self.power_down()
            elif reg == 0:  # command: bits 6-7 control the timer
                mode = val >> 6
                if mode == 3:
                    self.timer_running = True
                elif mode in (1, 2):
                    self.timer_running = False
                if self.sound:
                    self.sound.timer_state(self.timer_running,
                                           self.timer_count, self.pb,
                                           self.cpu.cycles)
            elif reg == 4:
                self.timer_count = (self.timer_count & 0x3F00) | val
            elif reg == 5:
                self.timer_count = ((val & 0x3F) << 8) | \
                                   (self.timer_count & 0xFF)
                self.serial.set_timer_count(self.timer_count)
                if self.sound:
                    self.sound.timer_state(self.timer_running,
                                           self.timer_count, self.pb,
                                           self.cpu.cycles)
        elif hi == 0xE0:
            old = self.e8
            self.e8 = val
            if (val & 0x01) != (old & 0x01):
                self.lo = self.optrom if (val & 0x01) else self.rom
            if (val & 0x04) and not (old & 0x04):
                self.rtc.chip_cmd(self.pa)
            if not (val & 0x02) and (old & 0x02):
                self._printer_byte(self.pa)
        elif hi == 0xA0:
            self.serial.modem_ctrl(val, time.monotonic())
        elif hi == 0xC0:
            self.serial.write_byte(val)
        elif hi == 0xD0:
            self.serial.set_format(val)

    def io_in(self, port):
        hi = port & 0xF0
        if hi == 0xE0:
            return self.kbd.read_rows(self.pa, self.pb)
        if hi == 0xF0:
            if port & 1:
                return self.lcd.read_data()
            return self.lcd.read_status()
        if hi == 0xB0:
            reg = port & 0x07
            if reg == 0:
                return 0x89
            if reg == 1:
                return self.pa
            if reg == 2:
                return self.pb
            if reg == 3:
                # RTC data out; printer not busy; ~CTS/~DSR low (ready)
                return 0x02 | self.rtc.serial_out
            return 0
        if hi == 0xC0:
            return self.serial.read_byte()
        if hi == 0xD0:
            return self.serial.status()
        if hi == 0xA0:
            return 0xA0
        return 0xFF

    # ------------------------------------------------------------- schedule
    def run_cycles(self, budget):
        """Run the CPU for `budget` cycles, firing timers along the way."""
        cpu = self.cpu
        target = cpu.cycles + budget
        while cpu.cycles < target:
            stop = self.next_rst75
            if self.next_serial < stop:
                stop = self.next_serial
            if target < stop:
                stop = target
            cpu.run(stop)
            c = cpu.cycles
            if c >= self.next_rst75:
                cpu.pulse_rst75()
                self.next_rst75 = c + RST75_PERIOD
            if c >= self.next_serial:
                self.serial.tick(c, time.monotonic())
                self.next_serial = c + SERIAL_SLICE
            if self.powered_off:
                return
        if not self._year_poked:
            self._maybe_poke_year()

    def _maybe_poke_year(self):
        """The uPD1990AC has no year register; the ROM keeps the year in
        RAM and cold-boots it to 00.  Stamp the host year once per boot,
        after the ROM has had a second to finish its cold-start init."""
        if self.cpu.cycles - self._boot_cycle < CPU_HZ:
            return
        base = ADDR_YEAR - 0x8000
        if self.ram[base] == 0 and self.ram[base + 1] == 0:
            year = self.rtc.now().tm_year
            self.ram[base] = year % 10
            self.ram[base + 1] = (year % 100) // 10
        self._year_poked = True

    # ---------------------------------------------------------------- power
    def power_down(self):
        """Software power-off (Port B bit 4) - the POWER OFF menu item."""
        self.powered_off = True
        self.on_status("powered off - press any key to power on")

    def wake(self):
        self.powered_off = False
        self.cpu.reset()  # warm boot: RAM (and files) survive

    def reset(self, cold=False):
        if cold:
            self.ram[:] = bytes(0x8000)
            self.set_ram_size(self.config["ram_size"], clear=True)
        self._year_poked = False
        self._boot_cycle = self.cpu.cycles
        self.pa = self.pb = self.e8 = 0
        self.lo = self.rom
        self.lcd.reset()
        self.kbd.reset()
        self.serial.hangup()
        self.cpu.reset()
        self.powered_off = False

    # -------------------------------------------------------------- helpers
    def load_option_rom(self, data):
        self.optrom = bytearray(data)
        self.optrom_loaded = True

    def eject_option_rom(self):
        self.optrom = bytearray(b"\xFF" * ROM_SIZE)
        self.optrom_loaded = False
        if self.lo is not self.rom:
            self.lo = self.rom

    def set_system_rom(self, data):
        self.rom = bytearray(data)
        self.reset()

    def screen_text(self):
        """The ROM's 40x8 character shadow of the LCD (debug/handy)."""
        base = ADDR_LCD_TEXT - 0x8000
        rows = []
        for r in range(8):
            row = self.ram[base + r * 40: base + (r + 1) * 40]
            rows.append("".join(chr(b) if 32 <= b < 127 else " "
                                for b in row))
        return rows

    def _printer_byte(self, b):
        try:
            with open(self.config["printer_file"], "ab") as f:
                f.write(bytes([b]))
        except OSError:
            pass
