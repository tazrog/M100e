"""Simulated printer: spools Model 100 printer-port output to PDF.

The ROM prints by latching a byte on 81C55 Port A and pulsing the printer
strobe (port 0xE8 bit 1) - LPRINT, PRINT (from TEXT), LCOPY all end up
here byte by byte.  We spool bytes into a job; when the port has been
quiet for a couple of seconds the job is "torn off" and rendered as a
PDF (Courier, 80 columns, 60 lines per page, form-feed starts a new
page) named after the moment it finished, in the printer output folder.

The PDF is written by hand - plain text pages need nothing beyond the
stock PDF syntax, so there are no dependencies.
"""

import pathlib
import time

JOB_IDLE_SECONDS = 2.0
COLS = 80
LINES = 60
PAGE_W, PAGE_H = 612, 792          # US Letter, points
MARGIN_X, TOP_Y = 54, 750
FONT_SIZE, LEADING = 10, 12


class PDFPrinter:
    def __init__(self, out_dir, on_status=None):
        self.out_dir = pathlib.Path(out_dir)
        self.on_status = on_status or (lambda msg: None)
        self.buffer = bytearray()
        self.last_byte = None

    # ---- wire protocol ---------------------------------------------------
    def feed(self, byte):
        self.buffer.append(byte)
        self.last_byte = time.monotonic()

    def tick(self, wall):
        if self.buffer and self.last_byte is not None \
                and wall - self.last_byte > JOB_IDLE_SECONDS:
            self.flush()

    def flush(self):
        if not self.buffer:
            return None
        data = bytes(self.buffer)
        self.buffer.clear()
        self.last_byte = None
        pages = self._paginate(data)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        name = "print_%s.pdf" % time.strftime("%Y-%m-%d_%H%M%S")
        path = self.out_dir / name
        try:
            path.write_bytes(_render_pdf(pages))
        except OSError as e:
            self.on_status("printer: %s" % e)
            return None
        self.on_status("printed %d page%s -> %s"
                       % (len(pages), "s" if len(pages) != 1 else "", path))
        return path

    # ---- job -> pages of text lines ---------------------------------------
    @staticmethod
    def _paginate(data):
        pages = []
        lines = []
        col = 0
        cur = []

        def end_line():
            nonlocal col
            lines.append("".join(cur))
            cur.clear()
            col = 0
            if len(lines) >= LINES:
                end_page()

        def end_page():
            nonlocal lines
            pages.append(lines)
            lines = []

        prev = 0
        for b in data:
            if b == 0x0D:
                end_line()
            elif b == 0x0A:
                if prev != 0x0D:  # bare LF is a newline; CRLF already did
                    end_line()
            elif b == 0x0C:
                if cur:
                    end_line()
                if lines:
                    end_page()
            elif b == 0x09:
                spaces = 8 - (col % 8)
                cur.append(" " * spaces)
                col += spaces
            elif 0x20 <= b < 0x7F:
                cur.append(chr(b))
                col += 1
                if col >= COLS:
                    end_line()
            prev = b
        if cur:
            end_line()
        if lines:
            pages.append(lines)
        return pages or [[""]]


def _render_pdf(pages):
    """Minimal single-font text PDF: Catalog, Pages, Courier, then a
    page + content-stream object pair per page."""

    def esc(line):
        out = line.replace("\\", r"\\").replace("(", r"\(") \
                  .replace(")", r"\)")
        return out.encode("latin-1", "replace")

    n_pages = len(pages)
    page_ids = [4 + 2 * i for i in range(n_pages)]
    kids = " ".join("%d 0 R" % pid for pid in page_ids)

    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: ("<< /Type /Pages /Kids [%s] /Count %d >>"
            % (kids, n_pages)).encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    }
    for i, lines in enumerate(pages):
        content = bytearray()
        content += b"BT /F1 %d Tf %d TL %d %d Td\n" % (
            FONT_SIZE, LEADING, MARGIN_X, TOP_Y)
        for line in lines:
            content += b"(" + esc(line) + b") Tj T*\n"
        content += b"ET"
        pid, cid = page_ids[i], page_ids[i] + 1
        objs[pid] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                     "/Resources << /Font << /F1 3 0 R >> >> "
                     "/Contents %d 0 R >>"
                     % (PAGE_W, PAGE_H, cid)).encode()
        objs[cid] = (b"<< /Length %d >>\nstream\n" % len(content)
                     + bytes(content) + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num
        out += objs[num]
        out += b"\nendobj\n"
    xref_at = len(out)
    count = max(objs) + 1
    out += b"xref\n0 %d\n" % count
    out += b"0000000000 65535 f \n"
    for num in range(1, count):
        out += b"%010d 00000 n \n" % offsets[num]
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (count, xref_at))
    return bytes(out)
