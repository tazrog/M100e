"""Measure the LCD rectangle and key hitboxes on the case photo.

The keycap tops sit in a mid-dark brightness band while the keyboard tray
between them is nearly black, so keys segment cleanly with row/column
projections.  The LCD glass is the greenish region inside the very-dark
bezel.  Writes assets/layout.json plus an overlay image for eyeballing.
"""

import json
import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMG_NAME = sys.argv[1] if len(sys.argv) > 1 else "m100.jpg"
IMG = ROOT / "assets" / IMG_NAME
OUT = ROOT / "assets" / "layout.json"
OVERLAY = ROOT / "assets" / "layout_check.png"

ROW_NAMES = [
    ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8",
     "PASTE", "LABEL", "PRINT", "PAUSE", "LEFT", "RIGHT", "UP", "DOWN"],
    ["ESC", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
     "-", "=", "BKSP"],
    ["TAB", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "ENTER"],
    ["CTRL", "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'"],
    ["CAPS", "SHIFT", "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/",
     "SHIFT2"],
    ["GRPH", "SPACE", "CODE", "NUM"],
]


def find_bezel(bright):
    """Bounding box of the biggest very-dark blob in the top half."""
    h, w = bright.shape
    ds = 4
    mask = (bright < 60)[: h // ds * ds, : w // ds * ds]
    small = mask.reshape(h // ds, ds, w // ds, ds).any(axis=(1, 3))
    sh, sw = small.shape
    labels = np.zeros((sh, sw), dtype=np.int32)
    best = None
    nxt = 0
    for sy in range(sh // 2):
        for sx in range(sw):
            if small[sy, sx] and not labels[sy, sx]:
                nxt += 1
                stack = [(sy, sx)]
                labels[sy, sx] = nxt
                x0 = x1 = sx
                y0 = y1 = sy
                n = 0
                while stack:
                    y, x = stack.pop()
                    n += 1
                    x0 = min(x0, x); x1 = max(x1, x)
                    y0 = min(y0, y); y1 = max(y1, y)
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < sh and 0 <= xx < sw and \
                                small[yy, xx] and not labels[yy, xx]:
                            labels[yy, xx] = nxt
                            stack.append((yy, xx))
                if best is None or n > best[4]:
                    best = (x0 * ds, y0 * ds, (x1 + 1) * ds, (y1 + 1) * ds, n)
    return best[:4]


def _largest_run(flags):
    """(start, length) of the longest True run."""
    best = (0, 0)
    start = None
    for i, v in enumerate(list(flags) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start > best[1]:
                best = (start, i - start)
            start = None
    return best


def find_glass(img, bezel):
    """The glass is the big contiguous light region inside the bezel."""
    bx0, by0, bx1, by1 = bezel
    sub = img[by0:by1, bx0:bx1].astype(int)
    light = sub.max(axis=2) > 110
    y0, yl = _largest_run(light.mean(axis=1) > 0.55)
    x0, xl = _largest_run(light[y0:y0 + yl].mean(axis=0) > 0.7)
    return [bx0 + x0, by0 + y0, xl, yl]


def find_key_rows(mask, top):
    """Row bands below `top`, then keys as column runs inside each band."""
    kb = mask[top:, :]
    prof = kb.sum(axis=1)
    bands = []
    start = None
    for y, v in enumerate(prof):
        if v > 120 and start is None:
            start = y
        elif v <= 120 and start is not None:
            if y - start >= 12:
                bands.append((start + top, y + top))
            start = None
    rows = []
    for y0, y1 in bands:
        colprof = mask[y0:y1, :].mean(axis=0)
        runs = []
        s = None
        for x, v in enumerate(colprof > 0.35):
            if v and s is None:
                s = x
            elif not v and s is not None:
                if x - s > 13:
                    runs.append((s, y0, x - s, y1 - y0))
                s = None
        rows.append(runs)
    return rows


def main():
    img = np.asarray(Image.open(IMG).convert("RGB"))
    h, w, _ = img.shape
    bright = img.max(axis=2).astype(int)

    bezel = find_bezel(bright)
    lcd = find_glass(img, bezel)

    # Key caps vs. their surroundings differ per artwork: on the museum
    # photo the tray between keys is darker than the caps (mid-band mask),
    # on light-body artwork the gaps are lighter (simple dark mask).  Try
    # candidates and keep the one that yields the Model 100 row pattern.
    want = [len(names) for names in ROW_NAMES]
    rows = None
    for mask in (
        (bright >= 40) & (bright <= 108),
        bright < 110,
        bright < 80,
        (bright >= 25) & (bright <= 130),
    ):
        cand = find_key_rows(mask, bezel[3] + 20)
        counts = [len(r) for r in cand]
        # the L-shaped ENTER may add one run to the CTRL row, and the
        # function-key bars may merge into their four groups of four
        ok = len(counts) == len(want) and all(
            c == w or (w == 12 and c == 13) or (w == 16 and c == 4)
            for c, w in zip(counts, want))
        print("mask candidate rows:", counts, "->", "ok" if ok else "no")
        if ok:
            rows = cand
            break
    if rows is None:
        print("ERROR: no mask candidate matched the key row pattern")
        return 1

    if len(rows[0]) == 4:  # split merged function-key groups into 4 bars
        split = []
        for gx, gy, gw, gh in rows[0]:
            bw = gw / 4.0
            for i in range(4):
                split.append((int(gx + i * bw), gy, int(bw) - 2, gh))
        rows[0] = split

    problems = False
    layout = {"image": IMG_NAME, "size": [w, h], "lcd": lcd,
              "keys": {}}
    if len(rows) != len(ROW_NAMES):
        print("ERROR: got %d rows, expected %d" % (len(rows), len(ROW_NAMES)))
        problems = True
    for i, (runs, names) in enumerate(zip(rows, ROW_NAMES)):
        # the L-shaped ENTER key also pokes into the CTRL row; merge it
        if names[0] == "CTRL" and len(runs) == len(names) + 1:
            ex, ey, ew, eh = layout["keys"]["ENTER"]
            lx, ly, lw, lh = runs[-1]
            x0 = min(ex, lx)
            x1 = max(ex + ew, lx + lw)
            layout["keys"]["ENTER"] = [x0, ey, x1 - x0, ly + lh - ey]
            runs = runs[:-1]
        if len(runs) != len(names):
            print("ERROR: row %s: %d keys, expected %d"
                  % (names[0], len(runs), len(names)))
            problems = True
            continue
        for name, rect in zip(names, runs):
            layout["keys"][name] = list(rect)

    OUT.write_text(json.dumps(layout, indent=1))
    print("wrote", OUT, " lcd:", lcd)

    im = Image.open(IMG).convert("RGB")
    dr = ImageDraw.Draw(im)
    x, y, lw_, lh_ = lcd
    dr.rectangle([x, y, x + lw_, y + lh_], outline=(255, 0, 0), width=4)
    for name, (x, y, kw, kh) in layout["keys"].items():
        dr.rectangle([x, y, x + kw, y + kh], outline=(0, 220, 0), width=2)
    im.save(OVERLAY)
    print("wrote", OVERLAY)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
