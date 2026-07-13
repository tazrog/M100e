"""The Model 100 piezo beeper.

Port B bit 2 selects the beeper's signal source: 0 = the 81C55 timer
square wave (frequency = 2457600 / count), 1 = software bit-banging via
Port B bit 5.  BEEP, keyclick and BASIC SOUND all end up here.

For the software-toggle mode we measure the interval between bit-5 flips
in CPU cycles and synthesize a square wave at that rate; a watchdog stops
the tone shortly after the ROM stops toggling.
"""

import pygame

CPU_HZ = 2457600
RATE = 22050
VOLUME = 0.30


class Beeper:
    def __init__(self):
        self.channel = pygame.mixer.Channel(0)
        self.cache = {}
        self.playing_freq = None
        self.mode_timer = False       # tone gated from the 81C55 timer
        self.last_toggle_cycles = None
        self.soft_deadline = 0.0      # wall time when soft tone expires
        self.soft_active = False

    # ---- machine hooks ---------------------------------------------------
    def port_b(self, old, new, timer_count, timer_running, cycles):
        changed = old ^ new
        if changed & 0x04:  # beeper source select
            if new & 0x04:
                self._stop_timer_tone()
            else:
                self._start_timer_tone(timer_count, timer_running)
        if (new & 0x04) and (changed & 0x20):  # software toggle
            self._soft_toggle(cycles)

    def timer_state(self, running, count, pb, cycles):
        if not (pb & 0x04):  # timer currently drives the beeper
            if running:
                self._start_timer_tone(count, running)
            else:
                self._stop_timer_tone()

    def tick(self, wall):
        """Frame watchdog for the software-toggled tone."""
        if self.soft_active and wall > self.soft_deadline:
            self.soft_active = False
            if not self.mode_timer:
                self._silence()

    # ---- internals -------------------------------------------------------
    def _start_timer_tone(self, count, running):
        if not running or not count:
            return
        freq = CPU_HZ / count
        if 20 <= freq <= 11000:
            self.mode_timer = True
            self._play(freq)

    def _stop_timer_tone(self):
        self.mode_timer = False
        if not self.soft_active:
            self._silence()

    def _soft_toggle(self, cycles):
        import time
        last = self.last_toggle_cycles
        self.last_toggle_cycles = cycles
        if last is None:
            return
        delta = cycles - last
        if delta <= 0 or delta > CPU_HZ // 40:
            return
        freq = CPU_HZ / (2 * delta)
        if 20 <= freq <= 11000:
            self.soft_active = True
            self.soft_deadline = time.monotonic() + 0.06
            self._play(freq)

    def _play(self, freq):
        freq = round(freq / 5) * 5  # quantize to keep the cache small
        if self.playing_freq == freq and self.channel.get_busy():
            return
        snd = self.cache.get(freq)
        if snd is None:
            periods = max(1, round(freq / 10))
            n = int(RATE * periods / freq)
            amp = int(32767 * VOLUME)
            buf = bytearray()
            for i in range(n):
                phase = (i * freq / RATE) % 1.0
                v = amp if phase < 0.5 else -amp
                buf += v.to_bytes(2, "little", signed=True)
            snd = pygame.mixer.Sound(buffer=bytes(buf))
            if len(self.cache) > 64:
                self.cache.clear()
            self.cache[freq] = snd
        self.playing_freq = freq
        self.channel.play(snd, loops=-1)

    def _silence(self):
        self.playing_freq = None
        self.channel.stop()
