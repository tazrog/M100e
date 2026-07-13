"""IM6402 UART, direct-connect modem and RS-232 - bridged to TCP.

Real hardware: one UART feeds either the 300-baud direct-connect modem or
the RS-232 jack, selected by 81C55 Port B bit 3 (1 = modem).  The 81C55
timer output is the UART's 16x baud clock (baud = 153600 / count).  A
received character raises RST 6.5; reading port 0xC8 fetches it.  Port
0xD8 reads line status; port 0xA0 controls the modem's phone relay -
TELCOM pulse-dials by clicking that relay, exactly like a rotary phone.

Here both paths terminate in TCP connections.  The pulse dialer is decoded
for real: relay clicks are counted into digits, the resulting "phone
number" is looked up in the user's dial directory, and the socket opens as
the "carrier".  Direct host:port serial connections are made lazily when
software uses the RS-232 side.  Minimal telnet IAC negotiation keeps real
telnet BBSes happy.
"""

import socket
import threading
import time
from collections import deque

CPU_HZ = 2457600

IAC = 255
DONT, DO, WONT, WILL = 254, 253, 252, 251
SB, SE = 250, 240
OPT_ECHO, OPT_SGA, OPT_BINARY = 1, 3, 0


class TcpLink:
    """A background TCP connection with telnet filtering."""

    def __init__(self, host, port, on_status=None):
        self.host = host
        self.port = port
        self.rx = deque()
        self.tx = deque()
        self.connected = False
        self.finished = False
        self.error = None
        self.on_status = on_status
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def send(self, byte):
        with self._lock:
            self.tx.append(byte)

    def close(self):
        self.finished = True

    def _status(self, msg):
        if self.on_status:
            self.on_status(msg)

    def _run(self):
        try:
            sock = socket.create_connection((self.host, self.port), timeout=15)
        except OSError as e:
            self.error = str(e)
            self.finished = True
            self._status("connect failed: %s" % e)
            return
        sock.settimeout(0.05)
        self.connected = True
        self._status("connected to %s:%d" % (self.host, self.port))
        state = 0  # 0=data, 1=IAC, 2=IAC+verb, 3=subnegotiation
        verb = 0
        try:
            while not self.finished:
                with self._lock:
                    out = bytes(self.tx)
                    self.tx.clear()
                if out:
                    # double any literal 0xFF bytes for telnet
                    sock.sendall(out.replace(b"\xff", b"\xff\xff"))
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                reply = bytearray()
                for b in data:
                    if state == 0:
                        if b == IAC:
                            state = 1
                        else:
                            self.rx.append(b)
                    elif state == 1:
                        if b == IAC:
                            self.rx.append(b)
                            state = 0
                        elif b in (DO, DONT, WILL, WONT):
                            verb = b
                            state = 2
                        elif b == SB:
                            state = 3
                        else:
                            state = 0
                    elif state == 2:
                        if verb == DO:
                            # we'll do binary/SGA, refuse everything else
                            ok = b in (OPT_SGA, OPT_BINARY)
                            reply += bytes((IAC, WILL if ok else WONT, b))
                        elif verb == WILL:
                            ok = b in (OPT_ECHO, OPT_SGA, OPT_BINARY)
                            reply += bytes((IAC, DO if ok else DONT, b))
                        state = 0
                    elif state == 3:
                        if b == SE:
                            state = 0
                if reply:
                    sock.sendall(bytes(reply))
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass
        self.connected = False
        self.finished = True
        self._status("disconnected from %s:%d" % (self.host, self.port))


class PulseDialer:
    """Decode rotary pulse dialing from phone-relay transitions."""

    DIGIT_GAP = 0.35   # seconds of relay silence that ends a digit
    NUMBER_GAP = 1.5   # seconds of silence that ends the number

    def __init__(self):
        self.reset()

    def reset(self):
        self.pulses = 0
        self.digits = ""
        self.last_edge = None
        self.relay = 0

    def edge(self, relay_closed, now):
        if relay_closed == self.relay:
            return
        self.relay = relay_closed
        if relay_closed:  # end of a break pulse
            self.pulses += 1
        self.last_edge = now

    def poll(self, now):
        """Returns a completed number string, or None."""
        if self.last_edge is None:
            return None
        idle = now - self.last_edge
        if self.pulses and idle > self.DIGIT_GAP:
            digit = self.pulses % 10
            self.digits += str(digit)
            self.pulses = 0
        if self.digits and not self.pulses and idle > self.NUMBER_GAP:
            number = self.digits
            self.digits = ""
            self.last_edge = None
            return number
        return None


class SerialSystem:
    """UART + modem/RS-232 mux, feeding RST 6.5."""

    def __init__(self, config, set_rx_int, on_status=None):
        self.config = config
        self.set_rx_int = set_rx_int
        self.on_status = on_status or (lambda msg: None)
        self.modem_selected = False   # Port B bit 3
        self.modem_enabled = False    # port 0xA0 bit 1
        self.relay = 0                # port 0xA0 bit 0
        self.links = {"modem": None, "rs232": None}
        self.rx_ready = False
        self.rx_byte = 0
        self.baud = 300
        self.char_cycles = CPU_HZ * 10 // 300
        self.next_rx = 0
        self.dialer = PulseDialer()
        self._relay_open_since = None

    # ---- wiring from the machine --------------------------------------
    def select_modem(self, modem):
        if modem != self.modem_selected:
            self.modem_selected = modem
            self._drop_rx()

    def set_timer_count(self, count):
        if count:
            self.baud = max(1, 153600 // count)
            if self.config["baud_pacing"] == "fast":
                self.char_cycles = 1500
            else:
                self.char_cycles = CPU_HZ * 10 // self.baud

    def modem_ctrl(self, val, now):
        relay = val & 1
        self.modem_enabled = bool(val & 2)
        if relay != self.relay:
            self.relay = relay
            self.dialer.edge(relay, now)
            if relay:
                self._relay_open_since = None
            else:
                self._relay_open_since = now

    # ---- UART register interface ---------------------------------------
    def write_byte(self, val):
        # bytes sent while the socket is still connecting are queued by
        # the link and flushed as soon as it comes up
        link = self._active_link(create=True)
        if link:
            link.send(val)

    def read_byte(self):
        v = self.rx_byte
        self.rx_ready = False
        self.set_rx_int(False)
        return v

    def status(self):
        """Port 0xD8: bit0 carrier data, 1 overrun, 2 framing, 3 parity,
        4 tx empty, 5 ring, 7 power OK."""
        s = 0x90  # power OK + tx buffer empty
        if self.modem_selected:
            link = self.links["modem"]
            if link and link.connected:
                s |= 0x01  # energy on the phone line = carrier present
        return s

    def set_format(self, val):
        pass  # data bits/parity are meaningless over TCP

    # ---- pacing / dial handling ------------------------------------------
    def tick(self, cycles, wall):
        """Called every few thousand CPU cycles."""
        number = self.dialer.poll(wall)
        if number:
            self._dial(number)

        # hanging up: relay held open >2s drops the modem call
        if (self._relay_open_since is not None
                and wall - self._relay_open_since > 2.0
                and self.links["modem"]):
            self._relay_open_since = None
            self.hangup("modem")

        if not self.rx_ready and cycles >= self.next_rx:
            link = self._active_link()
            if link and link.rx:
                self.rx_byte = link.rx.popleft()
                self.rx_ready = True
                self.set_rx_int(True)
                self.next_rx = cycles + self.char_cycles

    # ---- connections ---------------------------------------------------
    def _active_link(self, create=False):
        name = "modem" if self.modem_selected else "rs232"
        link = self.links[name]
        if link and link.finished:
            self.links[name] = link = None
        if link is None and create and name == "rs232":
            link = self._connect(name, self.config["serial_host"])
        return link

    def _connect(self, name, hostport):
        try:
            host, port = hostport.rsplit(":", 1)
            port = int(port)
        except ValueError:
            self.on_status("bad host:port %r" % hostport)
            return None
        self.on_status("connecting to %s:%d ..." % (host, port))
        link = TcpLink(host, port, self.on_status)
        self.links[name] = link
        return link

    def _dial(self, number):
        directory = self.config["dial_directory"]
        target = directory.get(number)
        if target is None:
            self.on_status("dialed %s: no dial-directory entry" % number)
            return
        self.on_status("dialed %s" % number)
        self.hangup("modem")
        self._connect("modem", target)

    def hangup(self, name=None):
        for n in ([name] if name else ["modem", "rs232"]):
            if self.links[n]:
                self.links[n].close()
                self.links[n] = None
        self._drop_rx()

    def _drop_rx(self):
        self.rx_ready = False
        self.set_rx_int(False)

    def connection_state(self):
        parts = []
        for name in ("modem", "rs232"):
            link = self.links[name]
            if link and link.connected:
                parts.append("%s: %s:%d" % (name, link.host, link.port))
        return ", ".join(parts)
