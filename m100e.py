#!/usr/bin/env python3
"""M100e - an original TRS-80 Model 100 emulator.

Run it and you are looking at a Model 100: the photo is the machine, the
LCD area is the live 240x64 display, and your keyboard is wired into the
key matrix.  Hover any key on the picture to see which real key drives it.
Right-click (or Ctrl+F1) for the emulator menu: load programs and ROMs,
change memory size, configure the modem/serial internet bridge. Ctrl+F2
opens a debugger overlay (registers, disassembly, memory, breakpoints).

    python3 m100e.py            fullscreen
    python3 m100e.py -w         windowed
    python3 m100e.py -w --load prog.co         load a file at startup
    python3 m100e.py -w --load prog.co --debug   ...with the debugger open
"""

import argparse
import os
import sys
import time

import pygame as pg

from m100 import rom
from m100.config import Config
from m100.files import RamFiles, FileError
from m100.machine import Machine, CPU_HZ
from m100.sound import Beeper
from m100.ui import Skin, LcdRenderer, Bubble, Menu, StatusLine, Debugger

FRAME_HZ = 60
RAM_SIZES = [8192, 16384, 24576, 32768]


class App:
    def __init__(self, windowed, load=None, debug=False):
        self.config = Config()
        self.status_cb = None  # set after StatusLine exists

        pg.mixer.pre_init(22050, -16, 1, 512)
        pg.init()
        pg.display.set_caption("TRS-80 Model 100")

        if windowed:
            self.screen = pg.display.set_mode((1360, 932), pg.RESIZABLE)
        else:
            # Borderless window at desktop resolution instead of exclusive
            # fullscreen: SDL's FULLSCREEN asks X11 for a video-mode switch,
            # which some window managers time out on ("no window becoming
            # fullscreen; reverting").  A borderless desktop-sized window
            # looks identical and needs no mode switch.
            os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
            info = pg.display.Info()
            self.screen = pg.display.set_mode(
                (info.current_w, info.current_h), pg.NOFRAME)

        font_size = max(14, self.screen.get_height() // 54)
        path = pg.font.match_font("dejavusans,freesans,liberationsans,arial")
        if path:
            self.font = pg.font.Font(path, font_size - 2)
            self.small_font = pg.font.Font(path, font_size - 5)
        else:  # bundled font: no U+2192 arrow, but never missing
            self.font = pg.font.Font(None, font_size + 6)
            self.small_font = pg.font.Font(None, font_size)

        mono_path = pg.font.match_font(
            "dejavusansmono,firacode,couriernew,consolas,monospace")
        mono_size = max(13, self.screen.get_height() // 62)
        self.mono_font = pg.font.Font(mono_path, mono_size) if mono_path \
            else pg.font.Font(None, mono_size + 4)

        self.skin = Skin()
        self.skin.fit(self.screen.get_size())
        self.status = StatusLine(self.small_font)

        try:
            rom_data = rom.get_system_rom(self.config)
        except rom.RomError:
            rom_data = self._first_run_rom_dialog()
        self.machine = Machine(rom_data, self.config,
                               on_status=self.on_status)
        if self.machine.load_ram_image():
            self.on_status("RAM contents restored")
        try:
            self.machine.sound = Beeper()
        except pg.error as e:
            print("[m100e] no audio: %s" % e)
        self.files = RamFiles(self.machine)
        self.debugger = Debugger(self.font, self.mono_font)
        self.debugger.open = debug

        if load:
            try:
                name = self.files.import_file(load)
                self.machine.cpu.reset()  # warm boot so the menu picks it up
                self.on_status("loaded %s" % name.strip())
            except (FileError, OSError) as e:
                self.on_status("load failed: %s" % e)

        opt = self.config["option_rom"]
        if opt:
            try:
                self.machine.load_option_rom(rom.load_rom_file(opt))
            except (OSError, rom.RomError) as e:
                self.on_status("option ROM: %s" % e)

        self.lcd_r = LcdRenderer(self.machine.lcd, self.skin.glass_rgb)
        self.lcd_r.set_contrast(self.config["contrast"])
        self.bubble = Bubble(self.small_font)
        self.menu = Menu(self.font)
        self.mouse_key = None
        self.running = True
        self.last_save = time.monotonic()

    # ------------------------------------------------------------- status
    def on_status(self, msg):
        print("[m100e]", msg)
        self.status.set(msg)

    # ----------------------------------------------------------- first run
    def _first_run_rom_dialog(self):
        """No system ROM installed: ask the user for their own dump.
        M100e never downloads ROMs."""
        from tkinter import messagebox
        while True:
            path = self.ask_open(
                "Select your Model 100 system ROM (32K image)",
                [("ROM images", "*.bin *.rom *.m12"), ("All files", "*")])
            if not path:
                print(
                    "\nM100e needs a TRS-80 Model 100 system ROM to run,\n"
                    "and does not download or include one.  Provide your\n"
                    "own 32K dump (e.g. from your machine, or from the\n"
                    "community archives) and either:\n"
                    "  - run m100e.py again and pick it in the dialog, or\n"
                    "  - copy it to ~/.m100e/m100rom.bin\n")
                pg.quit()
                sys.exit(1)
            try:
                data = rom.install_system_rom(path)
            except (OSError, rom.RomError) as e:
                root = self._tk_root()
                try:
                    messagebox.showerror("Not a Model 100 ROM", str(e),
                                         parent=root)
                finally:
                    root.destroy()
                continue
            if not rom.looks_like_m100_rom(data):
                print("[m100e] warning: image doesn't look like the "
                      "standard Tandy ROM; running it anyway")
            return data

    # ------------------------------------------------------------ dialogs
    def _tk_root(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return root

    def ask_open(self, title, filetypes):
        from tkinter import filedialog
        root = self._tk_root()
        try:
            return filedialog.askopenfilename(title=title,
                                              filetypes=filetypes,
                                              parent=root) or None
        finally:
            root.destroy()

    def ask_save(self, title, initial):
        from tkinter import filedialog
        root = self._tk_root()
        try:
            return filedialog.asksaveasfilename(
                title=title, initialfile=initial, parent=root) or None
        finally:
            root.destroy()

    def ask_string(self, title, prompt, initial=""):
        from tkinter import simpledialog
        root = self._tk_root()
        try:
            return simpledialog.askstring(title, prompt,
                                          initialvalue=initial, parent=root)
        finally:
            root.destroy()

    def ask_yesno(self, title, prompt):
        from tkinter import messagebox
        root = self._tk_root()
        try:
            return messagebox.askyesno(title, prompt, parent=root)
        finally:
            root.destroy()

    # ------------------------------------------------------------- actions
    def act_load_program(self):
        path = self.ask_open("Load program into the Model 100",
                             [("Model 100 files", "*.do *.DO *.ba *.BA "
                               "*.co *.CO *.txt"), ("All files", "*")])
        if not path:
            return "close"
        try:
            name = self.files.import_file(path)
        except (FileError, OSError) as e:
            self.on_status("load failed: %s" % e)
            return "close"
        self.machine.cpu.reset()  # warm boot so the menu picks it up
        self.on_status("loaded %s" % name.strip())
        return "close"

    def act_export(self):
        entries = self.files.list_files()
        if not entries:
            self.on_status("no files in the Model 100")
            return "close"
        items = []
        for base, ext, size in entries:
            label = "%s.%s   (%d bytes)" % (base, ext, size)
            items.append((label, self._make_exporter(base, ext)))
        items.append(("Back", lambda: "close"))
        self.menu.show(items)
        return None

    def _make_exporter(self, base, ext):
        def do():
            initial = "%s.%s" % (base.lower(), ext.lower())
            path = self.ask_save("Export %s.%s" % (base, ext), initial)
            if path:
                try:
                    self.files.export_file(base, ext, path)
                    self.on_status("exported %s" % path)
                except (FileError, OSError) as e:
                    self.on_status("export failed: %s" % e)
            return "close"
        return do

    def act_option_rom(self):
        if self.machine.optrom_loaded:
            self.machine.eject_option_rom()
            self.config["option_rom"] = None
            self.config.save()
            self.on_status("option ROM ejected")
            return "close"
        path = self.ask_open("Load option ROM (32K image)",
                             [("ROM images", "*.bin *.rom *.BX *.m12"),
                              ("All files", "*")])
        if not path:
            return "close"
        try:
            self.machine.load_option_rom(rom.load_rom_file(path))
            self.config["option_rom"] = path
            self.config.save()
            self.on_status("option ROM loaded (start it from the menu "
                           "or BASIC: CALL 63012)")
        except (OSError, rom.RomError) as e:
            self.on_status("option ROM: %s" % e)
        return "close"

    def act_system_rom(self):
        path = self.ask_open("Load system ROM (32K image)",
                             [("ROM images", "*.bin *.rom *.m12"),
                              ("All files", "*")])
        if not path:
            return "close"
        try:
            data = rom.load_rom_file(path)
            self.machine.set_system_rom(data)
            self.files = RamFiles(self.machine)
            self.config["system_rom"] = path
            self.config.save()
            self.on_status("system ROM replaced; machine reset")
        except (OSError, rom.RomError) as e:
            self.on_status("system ROM: %s" % e)
        return "close"

    def act_memory(self):
        cur = self.config["ram_size"]
        nxt = RAM_SIZES[(RAM_SIZES.index(cur) + 1) % len(RAM_SIZES)]
        if not self.ask_yesno(
                "Change memory",
                "Change RAM to %dK?\n\nThis cold-starts the Model 100 "
                "and erases all files (like swapping RAM modules)."
                % (nxt // 1024)):
            return None
        self.config["ram_size"] = nxt
        self.config.save()
        self.machine.config["ram_size"] = nxt
        self.machine.reset(cold=True)
        self.on_status("RAM set to %dK (cold start)" % (nxt // 1024))
        return "close"

    def act_serial_host(self):
        cur = self.config["serial_host"]
        new = self.ask_string("Serial port", "RS-232 connects to host:port:",
                              cur)
        if new:
            self.config["serial_host"] = new.strip()
            self.config.save()
            self.on_status("serial port -> %s" % new.strip())
        return "close"

    def act_dial_dir(self):
        entry = self.ask_string(
            "Dial directory",
            "number=host:port   (dial the number in TELCOM;\n"
            "empty host deletes the entry)\n\nCurrent:\n%s" %
            "\n".join("  %s -> %s" % kv
                      for kv in sorted(self.config["dial_directory"].items())),
            "")
        if entry and "=" in entry:
            num, _, host = entry.partition("=")
            num = "".join(c for c in num if c.isdigit())
            host = host.strip()
            if num:
                if host:
                    self.config["dial_directory"][num] = host
                else:
                    self.config["dial_directory"].pop(num, None)
                self.config.save()
                self.on_status("dial directory updated")
        return "close"

    def act_pacing(self):
        cur = self.config["baud_pacing"]
        self.config["baud_pacing"] = "fast" if cur == "authentic" \
            else "authentic"
        self.config.save()
        self.machine.serial.set_timer_count(self.machine.timer_count)
        return None

    def act_hangup(self):
        self.machine.serial.hangup()
        self.on_status("all connections closed")
        return "close"

    def act_reset(self):
        self.machine.reset()
        self.on_status("reset")
        return "close"

    def act_cold_reset(self):
        if self.ask_yesno("Cold restart",
                          "Cold-start the Model 100?\n\nAll files in RAM "
                          "will be erased."):
            self.machine.reset(cold=True)
            self.on_status("cold restart")
        return "close"

    def act_quit(self):
        self.running = False
        return "close"

    def act_toggle_breakpoint(self):
        addr = self.ask_string(
            "Breakpoint",
            "Toggle breakpoint at address (hex, blank = current PC):", "")
        if addr is None:
            return
        addr = addr.strip()
        try:
            a = self.machine.cpu.pc if not addr else int(addr, 16)
        except ValueError:
            self.on_status("not a hex address: %s" % addr)
            return
        self.debugger.toggle_breakpoint(a)
        self.on_status("breakpoint %s @ %04X" % (
            "set" if (a & 0xFFFF) in self.debugger.breakpoints else "cleared",
            a & 0xFFFF))

    def open_menu(self):
        c = self.config
        m = self.machine
        items = [
            ("Load program (.BA / .DO / .CO)...", self.act_load_program),
            ("Export file to host...", self.act_export),
            (lambda: "Eject option ROM" if m.optrom_loaded
             else "Load option ROM...", self.act_option_rom),
            ("Load system ROM...", self.act_system_rom),
            (lambda: "Memory: %dK  (change...)" %
             (c["ram_size"] // 1024), self.act_memory),
            (lambda: "Serial port: %s" % c["serial_host"],
             self.act_serial_host),
            ("Modem dial directory...", self.act_dial_dir),
            (lambda: "Baud pacing: %s" % c["baud_pacing"], self.act_pacing),
            ("Hang up connections", self.act_hangup),
            ("Reset (warm)", self.act_reset),
            ("Cold restart (erase files)", self.act_cold_reset),
            ("Quit  (files are saved)", self.act_quit),
        ]
        self.menu.show(items)

    # -------------------------------------------------------------- events
    def handle_event(self, ev):
        if ev.type == pg.QUIT:
            self.running = False
            return
        if self.menu.open and self.menu.handle_event(ev):
            return
        if ev.type == pg.VIDEORESIZE:
            self.skin.fit(ev.size)
            return
        if ev.type == pg.KEYDOWN:
            if ev.key == pg.K_F1 and ev.mod & pg.KMOD_CTRL:
                self.open_menu()
                return
            if ev.key == pg.K_F2 and ev.mod & pg.KMOD_CTRL:
                self.debugger.toggle_open()
                self.on_status("debugger %s" %
                              ("opened" if self.debugger.open else "closed"))
                return
            if ev.key == pg.K_F5 and ev.mod & pg.KMOD_CTRL:
                if self.debugger.open:
                    self.debugger.toggle_pause()
                    self.on_status("PAUSED" if self.debugger.paused
                                  else "RUNNING")
                return
            if ev.key == pg.K_F10 and ev.mod & pg.KMOD_CTRL:
                if self.debugger.open:
                    self.debugger.paused = True
                    self.machine.step_instruction()
                return
            if ev.key == pg.K_F9 and ev.mod & pg.KMOD_CTRL:
                if self.debugger.open:
                    self.act_toggle_breakpoint()
                return
            if ev.key == pg.K_TAB and ev.mod & pg.KMOD_CTRL:
                if self.debugger.open:
                    self.debugger.next_tab()
                return
            if self.debugger.open and ev.key == pg.K_PAGEUP:
                self.debugger.scroll_mem(-0x80)
                return
            if self.debugger.open and ev.key == pg.K_PAGEDOWN:
                self.debugger.scroll_mem(0x80)
                return
            if self.debugger.open and ev.key == pg.K_HOME:
                self.debugger.jump_mem_to(self.machine.cpu.pc)
                return
            if ev.key in (pg.K_UP, pg.K_DOWN) and ev.mod & pg.KMOD_CTRL:
                step = 0.05 if ev.key == pg.K_UP else -0.05
                c = min(1.0, max(0.0, self.config["contrast"] + step))
                self.config["contrast"] = round(c, 2)
                self.config.save()
                self.lcd_r.set_contrast(c)
                self.on_status("LCD contrast: %d%%" % round(c * 100))
                return
            if self.machine.powered_off:
                self.machine.wake()
                return
            self.machine.kbd.handle_key(ev.key, True)
        elif ev.type == pg.KEYUP:
            self.machine.kbd.handle_key(ev.key, False)
        elif ev.type == pg.MOUSEBUTTONDOWN:
            if ev.button == 3:
                self.open_menu()
            elif ev.button == 1:
                if self.debugger.open and self.debugger.click(ev.pos):
                    return
                name = self.skin.key_at(ev.pos)
                if name:
                    if self.machine.powered_off:
                        self.machine.wake()
                        return
                    mname = "SHIFT" if name == "SHIFT2" else name
                    self.machine.kbd.press_name(mname, True)
                    self.mouse_key = mname
        elif ev.type == pg.MOUSEBUTTONUP:
            if ev.button == 1 and self.mouse_key:
                self.machine.kbd.press_name(self.mouse_key, False)
                self.mouse_key = None

    # ---------------------------------------------------------------- main
    def run(self):
        clock = pg.time.Clock()
        budget = CPU_HZ // FRAME_HZ
        while self.running:
            for ev in pg.event.get():
                self.handle_event(ev)

            if not self.machine.powered_off and not self.debugger.paused:
                bps = self.debugger.breakpoints if self.debugger.open else None
                if self.machine.run_cycles(budget, bps):
                    self.debugger.paused = True
                    self.on_status("breakpoint hit @ %04X" %
                                  self.machine.cpu.pc)

            now = time.monotonic()
            if self.machine.sound:
                self.machine.sound.tick(now)
            self.machine.printer.tick(now)  # even while paused/powered off
            if now - self.last_save > 30:
                self.machine.save_ram_image()
                self.last_save = now

            self.draw(now)
            clock.tick(FRAME_HZ)

        self.machine.printer.flush()  # tear off any half-finished printout
        self.machine.save_ram_image()
        self.config.save()
        pg.quit()

    def draw(self, now):
        screen = self.screen
        screen.fill((12, 12, 14))
        screen.blit(self.skin.base, self.skin.offset)

        lcd_rect = self.skin.lcd_rect()
        surf = self.lcd_r.surface(lcd_rect.size, self.machine.powered_off)
        screen.blit(surf, lcd_rect.topleft)

        if not self.menu.open:
            self.bubble.track(self.skin.key_at(pg.mouse.get_pos()), now)
            self.bubble.draw(screen, self.skin, now)
        self.menu.draw(screen)
        self.debugger.draw(screen, self.machine)

        persistent = self.machine.serial.connection_state()
        if self.machine.powered_off:
            persistent = "powered off - press any key"
        self.status.draw(screen, persistent)
        pg.display.flip()


def main():
    ap = argparse.ArgumentParser(description="TRS-80 Model 100 emulator")
    ap.add_argument("-w", "--windowed", action="store_true",
                    help="run in a window instead of fullscreen")
    ap.add_argument("--load", metavar="FILE",
                    help="load a .BA/.DO/.CO file into RAM at startup "
                         "(e.g. a program just built by an IDE)")
    ap.add_argument("--debug", action="store_true",
                    help="open the debugger panel at startup")
    args = ap.parse_args()
    App(args.windowed, load=args.load, debug=args.debug).run()


if __name__ == "__main__":
    sys.exit(main())
