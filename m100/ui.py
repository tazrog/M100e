"""Fullscreen skin UI: the case photo, live LCD, hover bubbles, menu.

Everything is measured in photo coordinates (assets/layout.json) and
transformed through one scale factor, so hitboxes and the LCD stay glued
to the artwork at any resolution.
"""

import json
import pathlib
import time

import numpy as np
import pygame as pg

from . import keyboard
from .machine import CPU_HZ

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "assets"

LCD_GLASS = np.array((177, 187, 165), dtype=np.uint8)  # fallback glass green
LCD_INK = np.array((40, 46, 60), dtype=np.uint8)       # lit dot blue-gray
DEFAULT_CONTRAST = 0.55
LCD_INSET_X = 0.012   # active area margin inside the glass rectangle
LCD_INSET_Y = 0.03

BUBBLE_DELAY = 0.30
STATUS_TIME = 4.0


class Skin:
    def __init__(self):
        self.layout = json.loads((ASSETS / "layout.json").read_text())
        self.photo = pg.image.load(str(ASSETS / self.layout["image"]))
        self.photo = self.photo.convert()
        self.scale = 1.0
        self.offset = (0, 0)
        self.base = None
        # sample the artwork's actual glass color so the rendered LCD
        # blends into whatever skin image is in use
        x, y, w, h = self.layout["lcd"]
        probe = pg.Rect(int(x + w * 0.3), int(y + h * 0.3),
                        max(1, int(w * 0.4)), max(1, int(h * 0.4)))
        try:
            self.glass_rgb = pg.transform.average_color(self.photo,
                                                        probe)[:3]
        except (pg.error, ValueError):
            self.glass_rgb = tuple(int(v) for v in LCD_GLASS)

    def fit(self, screen_size):
        sw, sh = screen_size
        iw, ih = self.layout["size"]
        self.scale = min(sw / iw, sh / ih)
        w, h = int(iw * self.scale), int(ih * self.scale)
        self.offset = ((sw - w) // 2, (sh - h) // 2)
        self.base = pg.transform.smoothscale(self.photo, (w, h))

    def to_screen(self, rect):
        s = self.scale
        ox, oy = self.offset
        x, y, w, h = rect
        return pg.Rect(int(ox + x * s), int(oy + y * s),
                       max(1, int(w * s)), max(1, int(h * s)))

    def to_photo(self, pos):
        s = self.scale
        ox, oy = self.offset
        return ((pos[0] - ox) / s, (pos[1] - oy) / s)

    def key_at(self, pos):
        x, y = self.to_photo(pos)
        for name, (kx, ky, kw, kh) in self.layout["keys"].items():
            if kx - 4 <= x <= kx + kw + 4 and ky - 4 <= y <= ky + kh + 4:
                return name
        return None

    def lcd_rect(self):
        x, y, w, h = self.layout["lcd"]
        dx, dy = w * LCD_INSET_X, h * LCD_INSET_Y
        return self.to_screen((x + dx, y + dy, w - 2 * dx, h - 2 * dy))


class LcdRenderer:
    """Renders the 240x64 framebuffer the way the real panel looks: every
    pixel is a discrete square dot with a hairline of bare glass between
    dots, and unlit dots leave the LCD's faint ghost grid."""

    def __init__(self, lcd, glass_rgb=None):
        self.lcd = lcd
        self.glass = np.array(glass_rgb if glass_rgb else LCD_GLASS,
                              dtype=np.int16)
        self.ink = LCD_INK.astype(np.int16)
        self.contrast = DEFAULT_CONTRAST
        self._on_color, self._ghost_color = self._colors()
        self.scaled = None
        self.scaled_size = None
        self.blank = False
        self._cell = None
        self._work = None  # (64*N, 240*N, 3) color buffer
        self._surf = None

    def set_contrast(self, value):
        """0.0 = washed out, ~0.55 = normal, 1.0 = knob cranked so far the
        unlit dots go dark too - just like the real contrast wheel."""
        self.contrast = min(1.0, max(0.0, value))
        self._on_color, self._ghost_color = self._colors()
        self.lcd.dirty = True

    def _colors(self):
        c = self.contrast
        on_f = min(1.0, 0.30 + 0.95 * c)
        ghost_f = min(0.9, 0.055 + max(0.0, c - 0.62) * 1.5)
        on = (self.glass + (self.ink - self.glass) * on_f).astype(np.uint8)
        ghost = (self.glass + (self.ink - self.glass) *
                 ghost_f).astype(np.uint8)
        return on, ghost

    def _prepare(self, size):
        """(Re)build the fixed dot/gap geometry for the target size."""
        n = max(2, min(10, round(size[0] / 240)))
        if self._cell == n and self._work is not None:
            return n
        self._cell = n
        h, w = 64 * n, 240 * n
        self._work = np.empty((h, w, 3), dtype=np.uint8)
        # dot mask: True inside the dot, False on the glass gap between
        # dots (last row/column of every cell)
        line = np.ones(n, dtype=bool)
        line[-1] = False
        self._dot_mask = np.outer(np.tile(line, 64), np.tile(line, 240))
        self._surf = pg.Surface((w, h))
        return n

    def surface(self, size, powered_off):
        if powered_off != self.blank:
            self.blank = powered_off
            self.lcd.dirty = True
        n = self._prepare(size)
        if self.lcd.dirty or self.scaled_size != size:
            work = self._work
            work[:, :] = self.glass.astype(np.uint8)
            if self.blank:
                # a powered-off LCD is just uniform glass
                pass
            else:
                px = np.frombuffer(bytes(self.lcd.pixels()),
                                   dtype=np.uint8).reshape(64, 240)
                on = np.repeat(np.repeat(px, n, 0), n, 1).astype(bool)
                work[self._dot_mask & ~on] = self._ghost_color
                work[self._dot_mask & on] = self._on_color
            pg.surfarray.blit_array(self._surf, work.swapaxes(0, 1))
            self.scaled = pg.transform.smoothscale(self._surf, size)
            self.scaled_size = size
            self.lcd.dirty = False
        return self.scaled


class Bubble:
    """Hover tooltip showing the PC key mapped to a Model 100 key."""

    def __init__(self, font):
        self.font = font
        self.key = None
        self.since = 0.0

    def track(self, key_name, now):
        if key_name != self.key:
            self.key = key_name
            self.since = now

    def draw(self, screen, skin, now):
        if not self.key or now - self.since < BUBBLE_DELAY:
            return
        name = "SHIFT" if self.key == "SHIFT2" else self.key
        label = keyboard.bubble_label(name)
        if not label:
            return
        text = "%s  →  %s" % (name, label)
        surf = self.font.render(text, True, (245, 240, 225))
        pad = 8
        rect = skin.to_screen(skin.layout["keys"][self.key])
        bw, bh = surf.get_width() + 2 * pad, surf.get_height() + 2 * pad
        bx = min(max(rect.centerx - bw // 2, 4), screen.get_width() - bw - 4)
        by = rect.top - bh - 10
        if by < 4:
            by = rect.bottom + 10
        panel = pg.Surface((bw, bh), pg.SRCALPHA)
        pg.draw.rect(panel, (30, 30, 34, 235), panel.get_rect(),
                     border_radius=7)
        pg.draw.rect(panel, (120, 118, 108, 255), panel.get_rect(), 1,
                     border_radius=7)
        panel.blit(surf, (pad, pad))
        screen.blit(panel, (bx, by))
        # little pointer nub
        cx = max(bx + 12, min(rect.centerx, bx + bw - 12))
        if by < rect.top:
            pts = [(cx - 6, by + bh - 1), (cx + 6, by + bh - 1),
                   (cx, by + bh + 7)]
        else:
            pts = [(cx - 6, by + 1), (cx + 6, by + 1), (cx, by - 7)]
        pg.draw.polygon(screen, (30, 30, 34, 235), pts)


class Menu:
    """Right-click overlay menu.  Items are (label_fn, action_fn) pairs;
    action returning "close" closes the menu."""

    def __init__(self, font):
        self.font = font
        self.open = False
        self.items = []
        self.sel = 0
        self.item_rects = []

    def show(self, items):
        self.items = items
        self.sel = 0
        self.open = True

    def close(self):
        self.open = False

    def handle_event(self, ev):
        if ev.type == pg.KEYDOWN:
            if ev.key == pg.K_ESCAPE:
                self.close()
            elif ev.key in (pg.K_UP, pg.K_LEFT):
                self.sel = (self.sel - 1) % len(self.items)
            elif ev.key in (pg.K_DOWN, pg.K_RIGHT):
                self.sel = (self.sel + 1) % len(self.items)
            elif ev.key in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_SPACE):
                self._activate()
            return True
        if ev.type == pg.MOUSEMOTION:
            for i, r in enumerate(self.item_rects):
                if r.collidepoint(ev.pos):
                    self.sel = i
            return True
        if ev.type == pg.MOUSEBUTTONDOWN:
            if ev.button == 1:
                for i, r in enumerate(self.item_rects):
                    if r.collidepoint(ev.pos):
                        self.sel = i
                        self._activate()
                        return True
                self.close()
            elif ev.button == 3:
                self.close()
            return True
        return False

    def _activate(self):
        label, action = self.items[self.sel]
        if action is None:
            return
        if action() == "close":
            self.close()

    def draw(self, screen):
        if not self.open:
            return
        font = self.font
        labels = []
        for label, action in self.items:
            labels.append(label() if callable(label) else label)
        w = max(font.size(t)[0] for t in labels) + 48
        lh = font.get_height() + 10
        h = lh * len(labels) + 24
        x = (screen.get_width() - w) // 2
        y = max(20, (screen.get_height() - h) // 2)
        panel = pg.Surface((w, h), pg.SRCALPHA)
        pg.draw.rect(panel, (24, 24, 28, 242), panel.get_rect(),
                     border_radius=10)
        pg.draw.rect(panel, (130, 126, 112, 255), panel.get_rect(), 1,
                     border_radius=10)
        self.item_rects = []
        for i, text in enumerate(labels):
            iy = 12 + i * lh
            rect = pg.Rect(x + 8, y + iy - 3, w - 16, lh)
            self.item_rects.append(rect)
            enabled = self.items[i][1] is not None
            if i == self.sel and enabled:
                pg.draw.rect(panel, (70, 78, 96, 255),
                             (8, iy - 3, w - 16, lh), border_radius=6)
            color = (240, 236, 222) if enabled else (150, 146, 134)
            panel.blit(font.render(text, True, color), (24, iy))
        screen.blit(panel, (x, y))


class StatusLine:
    def __init__(self, font):
        self.font = font
        self.msg = ""
        self.until = 0.0

    def set(self, msg):
        self.msg = msg
        self.until = time.monotonic() + STATUS_TIME

    def draw(self, screen, persistent):
        now = time.monotonic()
        text = self.msg if now < self.until else persistent
        if not text:
            return
        surf = self.font.render(text, True, (225, 220, 205))
        pad = 5
        panel = pg.Surface((surf.get_width() + 2 * pad,
                            surf.get_height() + 2 * pad), pg.SRCALPHA)
        panel.fill((20, 20, 22, 175))
        panel.blit(surf, (pad, pad))
        screen.blit(panel, (8, screen.get_height() -
                            panel.get_height() - 6))
