"""End-to-end feature tests: RAM sizes, persistence, files, option ROM,
serial/modem TCP bridge, beeper wiring."""

import socket
import sys
import threading
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m100.config import Config
from m100.machine import Machine, CPU_HZ
from m100.files import RamFiles
from m100.uart import PulseDialer
from m100 import rom
from test_keyboard import press, type_text

RESULTS = []


def t(name, cond, detail=""):
    print("  %-52s %s %s" % (name, "ok" if cond else "FAIL", detail))
    RESULTS.append(cond)


def fresh_machine(cfg=None, ram=32768):
    cfg = cfg or Config()
    cfg["ram_size"] = ram
    m = Machine(rom.get_system_rom(cfg), cfg)
    m.run_cycles(CPU_HZ * 2)
    return m


class EchoServer:
    def __init__(self, greeting=b"WELCOME\r\n"):
        self.received = []
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        self.port = srv.getsockname()[1]
        self.greeting = greeting
        self.connections = 0
        threading.Thread(target=self._serve, args=(srv,),
                         daemon=True).start()

    def _serve(self, srv):
        while True:
            conn, _ = srv.accept()
            self.connections += 1
            conn.sendall(self.greeting)
            try:
                while True:
                    d = conn.recv(256)
                    if not d:
                        break
                    self.received.append(d)
                    conn.sendall(d)  # echo back
            except OSError:
                pass


def test_ram_sizes():
    for size, expect_free in ((8192, None), (16384, None), (24576, None)):
        m = fresh_machine(ram=size)
        row = m.screen_text()[7]
        free = row.split()[1] if "Bytes free" in row else "?"
        try:
            n = int(row.split("Bytes free")[0].split(":")[-1].strip()
                    .split()[-1])
        except (ValueError, IndexError):
            n = -1
        t("boots at %dK (%s bytes free)" % (size // 1024, n),
          "Bytes free" in row and 0 < n < 29638)


def test_persistence():
    cfg = Config()
    m = fresh_machine(cfg)
    rf = RamFiles(m)
    tmp = pathlib.Path("/tmp/claude-1000") / "note.do"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("hello from the host\n")
    name = rf.import_file(str(tmp))
    m.cpu.reset()
    m.run_cycles(CPU_HZ)
    t("imported %s appears on menu" % name.strip(),
      "NOTE" in "\n".join(m.screen_text()))
    m.save_ram_image()

    m2 = Machine(rom.get_system_rom(cfg), cfg)
    ok = m2.load_ram_image()
    m2.run_cycles(CPU_HZ)
    files = RamFiles(m2).list_files()
    t("RAM image persists across restart",
      ok and any(b == "NOTE" for b, e, s in files), str(files))


def test_basic_roundtrip():
    m = fresh_machine()
    rf = RamFiles(m)
    src = ('10 REM COUNT\n'
           '20 FOR I=1 TO 3\n'
           '30 PRINT "N=";I\n'
           '40 NEXT I\n')
    tmp = pathlib.Path("/tmp/claude-1000") / "count.ba"
    tmp.write_text(src)
    name = rf.import_file(str(tmp))
    m.cpu.reset()
    m.run_cycles(CPU_HZ)
    menu = "\n".join(m.screen_text())
    t("imported COUNT.BA on menu", "COUNT" in menu)

    # run it from BASIC
    press(m, "ENTER", 0.08, 1.0)  # menu cursor is on BASIC
    type_text(m, 'run "count\r')
    m.run_cycles(CPU_HZ * 2)
    screen = "\n".join(m.screen_text())
    t('RUN "COUNT" prints N=1..3',
      "N= 1" in screen and "N= 3" in screen, repr(screen[:60]))

    out = pathlib.Path("/tmp/claude-1000") / "count_out.ba"
    rf.export_file("COUNT", "BA", str(out))
    text = out.read_text()
    t("exported .BA detokenizes to source",
      'PRINT "N=";I' in text and "REM COUNT" in text, repr(text))


def test_option_rom():
    import io, urllib.request, zipfile
    cart = pathlib.Path("/tmp/claude-1000") / "cart-sup100.bin"
    if not cart.exists():
        scratch = pathlib.Path("/tmp/claude-1000/-home-tazrog-M100e/"
                               "dc0523fd-94c3-46b3-861f-999af4b24978/"
                               "scratchpad/m100.zip")
        if scratch.exists():
            with zipfile.ZipFile(scratch) as z:
                cart.write_bytes(z.read("cart-sup100.bin"))
    if not cart.exists():
        t("option ROM cart available", False, "(skipped)")
        return
    m = fresh_machine()
    m.load_option_rom(cart.read_bytes())
    normal = m.read(0x40)
    m.io_out(0xE8, 0x01)  # select option ROM
    opt = m.read(0x40)
    m.io_out(0xE8, 0x00)
    back = m.read(0x40)
    t("option ROM bank switches in and out",
      opt != normal and back == normal,
      "sys=%02X opt=%02X" % (normal, opt))


def test_serial_telcom():
    srv = EchoServer()
    cfg = Config()
    cfg["serial_host"] = "127.0.0.1:%d" % srv.port
    m = fresh_machine(cfg)
    press(m, "RIGHT")
    press(m, "RIGHT")
    press(m, "ENTER", 0.08, 1.0)     # TELCOM
    press(m, "F3", 0.08, 0.5)        # Stat
    type_text(m, "98N1E\r")
    m.run_cycles(CPU_HZ // 2)
    press(m, "F4", 0.08, 1.0)        # Term
    type_text(m, "HI\r")
    deadline = time.time() + 4
    while time.time() < deadline and b"hi\r" not in b"".join(srv.received):
        m.run_cycles(CPU_HZ // 4)
        time.sleep(0.02)
    m.run_cycles(CPU_HZ)
    got = b"".join(srv.received).lower()
    t("TELCOM transmits over TCP", b"hi\r" in got, repr(got))
    screen = "\n".join(m.screen_text()).lower()
    t("TELCOM shows server greeting", "welcome" in screen)
    t("TELCOM shows echoed input", "hi" in screen)


def test_pulse_dialer():
    d = PulseDialer()
    now = 0.0
    # dial "31": 3 pulses, gap, 1 pulse
    for digit in (3, 1):
        for _ in range(digit):
            d.edge(0, now); now += 0.061
            d.edge(1, now); now += 0.039
        now += 0.7
        d.poll(now)
    number = d.poll(now + 2.0)
    t("pulse dialer decodes 31", number == "31", repr(number))


def test_modem_dial():
    srv = EchoServer(greeting=b"BBS LOGIN\r\n")
    cfg = Config()
    cfg["dial_directory"] = {"31": "127.0.0.1:%d" % srv.port}
    m = fresh_machine(cfg)
    m.serial.select_modem(True)
    now = time.monotonic()
    for digit in (3, 1):
        for _ in range(digit):
            m.io_out(0xA0, 0x02); m.io_out(0xA0, 0x03)
            m.serial.dialer.last_edge = now  # timing driven manually
        m.serial.dialer.poll(now + 0.5)
    m.serial.tick(m.cpu.cycles, now + 3.0)
    time.sleep(0.5)
    carrier = m.io_in(0xD8) & 1
    t("modem dial connects and raises carrier",
      srv.connections == 1 and carrier == 1,
      "conns=%d carrier=%d" % (srv.connections, carrier))


def test_beeper_wiring():
    m = fresh_machine()
    calls = []

    class FakeSound:
        def port_b(self, *a):
            calls.append("pb")

        def timer_state(self, *a):
            calls.append("ts")

        def tick(self, wall):
            pass

    m.sound = FakeSound()
    press(m, "ENTER", 0.08, 1.0)
    type_text(m, "beep\r")
    m.run_cycles(CPU_HZ)
    t("BEEP reaches the sound hook", len(calls) > 0, "%d calls" % len(calls))


def main():
    test_ram_sizes()
    test_persistence()
    test_basic_roundtrip()
    test_option_rom()
    test_serial_telcom()
    test_pulse_dialer()
    test_modem_dial()
    test_beeper_wiring()
    print("PASS" if all(RESULTS) else "FAIL")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
