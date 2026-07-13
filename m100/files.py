"""Import/export host files into the Model 100 RAM file system.

The ROM keeps a 24-entry directory at 0xF962 (11 bytes each: flag byte,
file address, 8-char name).  Flags: 0x80 = .BA, 0xA0 = .CO, 0xC0 = .DO.
File data lives in one contiguous arena ordered [BA files][DO files]
[CO files][variables...]; inserting or deleting a file shifts everything
above it and fixes up the directory, the BASIC line-link pointers and the
system pointers that delimit the arena regions.

BASIC keywords are tokenized using the keyword table read straight out of
the system ROM (tokens 0x80.., last character of each keyword has bit 7
set), so a custom ROM brings its own dialect along.
"""

# System RAM locations (standard US Model 100 ROM)
FILE_PTR_BA = 0xF99A    # head of the unsaved BASIC program
FILE_PTR_DO = 0xF9A5    # where the next .DO file starts
BEGIN_DO = 0xFBAE
BEGIN_CO = 0xFBB0
BEGIN_VAR = 0xFBB2
BEGIN_ARRAY = 0xFBB4
UNUSED_MEM = 0xFBB6
BASIC_STRINGS = 0xF678
BASIC_SIZE = 0xFAD8
DIRECTORY = 0xF962
DIR_COUNT = 24
FIRST_USER_ENTRY = 8

TYPE_BA = 0x80
TYPE_CO = 0xA0
TYPE_DO = 0xC0

KEYWORD_TABLE_ADDR = 0x0080
KEYWORD_TABLE_END = 0x0262

TOK_REM = 14
TOK_ELSE = 17
TOK_PRINT = 35


class FileError(Exception):
    pass


def rom_keywords(rom):
    """Decode the BASIC keyword table from the ROM image.  Bit 7 marks the
    first character of each keyword; token = 0x80 + index."""
    words = []
    cur = []
    for a in range(KEYWORD_TABLE_ADDR, KEYWORD_TABLE_END):
        b = rom[a]
        if b & 0x80 and cur:
            words.append("".join(cur))
            cur = []
        cur.append(chr(b & 0x7F))
    if cur:
        words.append("".join(cur))
    return words


class RamFiles:
    def __init__(self, machine):
        self.m = machine
        self.keywords = rom_keywords(machine.rom)

    # ---- little helpers ------------------------------------------------
    def rd8(self, a):
        return self.m.read(a)

    def rd16(self, a):
        return self.m.read(a) | (self.m.read((a + 1) & 0xFFFF) << 8)

    def wr8(self, a, v):
        self.m.write(a, v & 0xFF)

    def wr16(self, a, v):
        self.m.write(a, v & 0xFF)
        self.m.write((a + 1) & 0xFFFF, (v >> 8) & 0xFF)

    # ---- directory -------------------------------------------------------
    def list_files(self):
        """[(name, ext, size_bytes)] for user directory entries."""
        out = []
        for i in range(FIRST_USER_ENTRY, DIR_COUNT):
            da = DIRECTORY + 11 * i
            flag = self.rd8(da)
            if flag == 0 or not flag & 0x80:
                continue
            name = "".join(chr(self.rd8(da + 3 + x)) for x in range(8))
            base, ext = name[:6].rstrip(), name[6:]
            try:
                size = self._file_length(self.rd16(da + 1), ext)
            except FileError:
                size = 0
            out.append((base, ext, size))
        return out

    def _find_entry(self, mt_name):
        for i in range(DIR_COUNT):
            da = DIRECTORY + 11 * i
            if self.rd8(da) == 0:
                continue
            name = "".join(chr(self.rd8(da + 3 + x)) for x in range(8))
            if name == mt_name:
                return da
        return 0

    def _free_entry(self):
        for i in range(FIRST_USER_ENTRY, DIR_COUNT):
            da = DIRECTORY + 11 * i
            if self.rd8(da) == 0:
                return da
        raise FileError("Model 100 directory is full (16 files)")

    @staticmethod
    def mt_name(host_name, ext):
        base = "".join(c for c in host_name.upper()
                       if c.isalnum())[:6].ljust(6)
        return base + ext

    def _file_length(self, addr, ext):
        if ext == "DO":
            end = addr
            while self.rd8(end) != 0x1A:
                end += 1
                if end - addr > 0x8000:
                    raise FileError("unterminated .DO file")
            return end - addr + 1
        if ext[0] == "C":
            return self.rd16(addr + 2) + 6
        # BASIC: follow the line links to the 0x0000 terminator
        end = addr
        while self.rd16(end) != 0:
            nxt = self.rd16(end)
            if nxt <= end or nxt > 0xFFFF:
                raise FileError("corrupt BASIC line links")
            end = nxt
        return end - addr + 2

    # ---- delete ---------------------------------------------------------
    def delete(self, mt_name):
        da = self._find_entry(mt_name)
        if not da:
            return False
        addr = self.rd16(da + 1)
        ext = mt_name[6:]
        length = self._file_length(addr, ext)
        ftype = self.rd8(da)

        self.wr8(da, 0)
        # slide everything above the file down
        move_len = self.rd16(UNUSED_MEM) - (addr + length)
        for x in range(move_len):
            self.wr8(addr + x, self.rd8(addr + length + x))
        self._fix_offsets(addr, -length)
        self._fix_basic_links(addr, -length)
        self._fix_system_pointers(ftype, addr, -length)
        return True

    # ---- import -----------------------------------------------------------
    def import_file(self, path):
        """Load a host .DO/.BA/.CO file into RAM.  Returns the M100 name."""
        raw = open(path, "rb").read()
        lower = str(path).lower()
        stem = str(path).replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if lower.endswith(".ba"):
            ftype, ext = TYPE_BA, "BA"
        elif lower.endswith(".co"):
            ftype, ext = TYPE_CO, "CO"
        else:
            ftype, ext = TYPE_DO, "DO"
        name = self.mt_name(stem, ext)

        if ftype == TYPE_DO:
            data = self._prepare_do(raw)
        elif ftype == TYPE_CO:
            data = raw
            if len(data) < 6:
                raise FileError("not a valid .CO file (no header)")
            if (data[2] | (data[3] << 8)) > len(data) - 6:
                raise FileError(".CO header length exceeds file size")
        else:
            data = raw  # relocated below once the address is known

        if self._find_entry(name):
            self.delete(name)

        addr = self._insert_addr(ftype)
        if ftype == TYPE_BA:
            data = self._prepare_ba(raw, addr)
        length = len(data)
        if length == 0:
            raise FileError("file is empty")

        room = self.rd16(BASIC_STRINGS) - self.rd16(BEGIN_VAR)
        if room < length:
            raise FileError("not enough free RAM (%d needed, %d free)"
                            % (length, max(0, room)))

        da = self._free_entry()
        # make space
        move_len = self.rd16(UNUSED_MEM) - addr
        for x in range(move_len - 1, -1, -1):
            self.wr8(addr + length + x, self.rd8(addr + x))
        self._fix_offsets(addr, length)

        self.wr8(da, ftype)
        self.wr16(da + 1, addr)
        for x, ch in enumerate(name):
            self.wr8(da + 3 + x, ord(ch))

        self._fix_basic_links(addr, length, exclude=da)
        self._fix_system_pointers(ftype, addr, length)

        for x, b in enumerate(data):
            self.wr8(addr + x, b)
        return name

    def _insert_addr(self, ftype):
        if ftype == TYPE_BA:
            return self.rd16(FILE_PTR_BA)
        if ftype == TYPE_CO:
            return self.rd16(BEGIN_VAR)
        return self.rd16(FILE_PTR_DO)

    # ---- pointer fixups --------------------------------------------------
    def _fix_offsets(self, start, delta):
        for i in range(DIR_COUNT):
            da = DIRECTORY + 11 * i
            if self.rd8(da) == 0:
                continue
            fa = self.rd16(da + 1)
            if fa >= start:
                self.wr16(da + 1, fa + delta)

    def _fix_basic_links(self, start, delta, exclude=None):
        """Rewrite line-link chains of saved .BA files above the move point,
        plus the unsaved program."""
        for i in range(DIR_COUNT):
            da = DIRECTORY + 11 * i
            if da == exclude or self.rd8(da) != TYPE_BA:
                continue
            fa = self.rd16(da + 1)
            if fa >= start:
                self._relink(fa, delta)
        self._relink(self.rd16(FILE_PTR_BA), delta, only_if_above=start)

    def _relink(self, addr, delta, only_if_above=None):
        guard = 0
        while self.rd16(addr) != 0:
            nxt = self.rd16(addr)
            if only_if_above is not None and nxt < only_if_above:
                break
            self.wr16(addr, nxt + delta)
            addr = nxt + delta
            guard += 1
            if guard > 4000:
                break

    def _fix_system_pointers(self, ftype, start, delta):
        for ptr in (BEGIN_ARRAY, BEGIN_VAR, UNUSED_MEM):
            v = self.rd16(ptr)
            if v >= start:
                self.wr16(ptr, v + delta)
        if ftype != TYPE_CO:
            v = self.rd16(BEGIN_CO)
            if v > start:
                self.wr16(BEGIN_CO, v + delta)
        if ftype == TYPE_BA:
            v = self.rd16(BEGIN_DO)
            if v > start:
                self.wr16(BEGIN_DO, v + delta)
            self.wr16(BASIC_SIZE, self.rd16(BASIC_SIZE) + delta
                      - (2 if delta > 0 else -2))

    # ---- content preparation ----------------------------------------------
    @staticmethod
    def _prepare_do(raw):
        out = bytearray()
        prev = 0
        for b in raw:
            if b == 0x0A and prev != 0x0D:
                out.append(0x0D)
            out.append(b)
            prev = b
        if not out or out[-1] != 0x1A:
            out.append(0x1A)
        if len(out) > 0x7000:
            raise FileError("text file too large for the Model 100")
        return bytes(out)

    def _prepare_ba(self, raw, addr):
        """ASCII source is tokenized; an already-tokenized image is
        relocated to its new address."""
        is_ascii = all(b in (0x0D, 0x0A, 0x09, 0x1A) or 0x20 <= b < 0x80
                       for b in raw[:16])
        if is_ascii:
            return self._tokenize(raw.decode("ascii", "replace"), addr)
        return self._relocate(raw, addr)

    @staticmethod
    def _relocate(raw, addr):
        out = bytearray()
        pos = 0
        while pos + 2 <= len(raw):
            link = raw[pos] | (raw[pos + 1] << 8)
            if link == 0:
                break
            end = raw.index(b"\x00", pos + 4)  # line terminator
            line = raw[pos + 2:end + 1]
            out += b"\x00\x00" + line  # link patched below
            new_link = addr + len(out)
            out[-len(line) - 2] = new_link & 0xFF
            out[-len(line) - 1] = new_link >> 8
            pos = end + 1
        out += b"\x00\x00"
        # links must point at each following line, recompute cleanly
        return RamFiles._relink_image(bytes(out), addr)

    @staticmethod
    def _relink_image(img, addr):
        out = bytearray(img)
        pos = 0
        while pos + 2 <= len(out):
            if out[pos] == 0 and out[pos + 1] == 0:
                break
            end = out.index(b"\x00", pos + 4)
            nxt = addr + end + 1
            out[pos] = nxt & 0xFF
            out[pos + 1] = nxt >> 8
            pos = end + 1
        return bytes(out)

    def _tokenize(self, text, addr):
        keywords = self.keywords
        lines = []
        for src in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            src = src.strip()
            if not src:
                continue
            i = 0
            num = 0
            ndig = 0
            while i < len(src) and src[i].isdigit():
                num = num * 10 + int(src[i])
                i += 1
                ndig += 1
            if ndig == 0:
                raise FileError("BASIC line without a line number: %r"
                                % src[:30])
            if i < len(src) and src[i] == " ":
                i += 1
            lines.append((num, self._tokenize_line(src[i:], keywords)))
        lines.sort(key=lambda t: t[0])

        out = bytearray()
        for num, body in lines:
            line = bytes((num & 0xFF, num >> 8)) + body + b"\x00"
            link = addr + len(out) + 2 + len(line)
            out += bytes((link & 0xFF, link >> 8)) + line
        out += b"\x00\x00"
        return bytes(out)

    def _tokenize_line(self, src, keywords):
        out = bytearray()
        i = 0
        n = len(src)
        while i < n:
            ch = src[i]
            if ch == "?":
                out.append(0x80 + TOK_PRINT)
                i += 1
            elif ch == "'":
                out += bytes((ord(":"), 0x80 + TOK_REM, 0xFF))
                out += src[i + 1:].encode("ascii", "replace")
                break
            elif ch == '"':
                out.append(ord(ch))
                i += 1
                while i < n and src[i] != '"':
                    out.append(ord(src[i]))
                    i += 1
                if i < n:
                    out.append(ord('"'))
                    i += 1
            elif "0" <= ch <= ";":
                out.append(ord(ch))
                i += 1
            else:
                tok = None
                for t, kw in enumerate(keywords):
                    if kw and src.startswith(kw, i):
                        tok = t
                        break
                if tok is None:
                    out.append(ord(ch) & 0x7F)
                    i += 1
                    continue
                if tok == TOK_ELSE and (not out or out[-1] != ord(":")):
                    out.append(ord(":"))
                out.append(0x80 + tok)
                i += len(keywords[tok])
                if tok == TOK_REM:
                    out += src[i:].encode("ascii", "replace")
                    break
                if tok == 3:  # DATA: literal until ':' or EOL
                    while i < n and src[i] != ":":
                        out.append(ord(src[i]))
                        i += 1
        return bytes(out)

    # ---- export ------------------------------------------------------------
    def export_file(self, base, ext, path):
        name = base.ljust(6) + ext
        da = self._find_entry(name)
        if not da:
            raise FileError("no such file: %s" % name)
        addr = self.rd16(da + 1)
        length = self._file_length(addr, ext)
        data = bytes(self.rd8(addr + x) for x in range(length))
        if ext == "BA":
            data = self._detokenize(data, addr).encode("ascii", "replace")
        elif ext == "DO":
            data = data[:-1].replace(b"\r\n", b"\n")  # drop EOF mark, CRLF
        open(path, "wb").write(data)
        return length

    def _detokenize(self, img, addr):
        kw = self.keywords
        out = []
        pos = 0
        while pos + 2 <= len(img):
            if img[pos] | (img[pos + 1] << 8) == 0:
                break
            num = img[pos + 2] | (img[pos + 3] << 8)
            out.append("%d " % num)
            i = pos + 4
            in_quote = False
            while i < len(img) and img[i] != 0:
                b = img[i]
                if b == ord('"'):
                    in_quote = not in_quote
                    out.append('"')
                elif b >= 0x80 and not in_quote:
                    idx = b - 0x80
                    if idx == TOK_REM and i + 1 < len(img) \
                            and img[i + 1] == 0xFF:
                        # REM tick: strip a preceding ':' we emitted
                        if out and out[-1] == ":":
                            out.pop()
                        out.append("'")
                        i += 1
                    else:
                        out.append(kw[idx] if idx < len(kw) else "?")
                else:
                    out.append(chr(b))
                i += 1
            out.append("\n")
            pos = i + 1
        return "".join(out)
