"""System ROM acquisition and option ROM loading.

The Model 100 needs its 32K Tandy/Microsoft system ROM to boot.  The ROM is
preserved by the Model 100 community; on first run we fetch it from the
Internet Archive's Model 100 software item and cache it locally.  The user
can replace it with their own image at any time.
"""

import hashlib
import io
import urllib.request
import zipfile

from .config import ROM_CACHE, STATE_DIR

ROM_SIZE = 32768
ROM_SHA256 = "0accd7e877ad6aad6ced81424f69e876093041f633e4900ea9d5b855830d0236"

# The archive.org item holds the MAME ROM set; the system ROM lives inside a
# nested zip as m100rom.m12.
ARCHIVE_URL = "https://archive.org/download/trs-80-model-100/TRS80Model100.zip"
INNER_ZIP = "roms/trsm100.zip"
INNER_ROM = "m100rom.m12"


class RomError(Exception):
    pass


def _looks_like_m100_rom(data):
    return len(data) == ROM_SIZE and b"(C)Microsoft" in data


def load_cached_rom():
    """Return the cached ROM bytes, or None if not cached/invalid."""
    if ROM_CACHE.exists():
        data = ROM_CACHE.read_bytes()
        if _looks_like_m100_rom(data):
            return data
    return None


def download_rom(progress=None):
    """Download, verify and cache the system ROM.  Returns ROM bytes."""
    if progress:
        progress("Downloading Model 100 ROM from archive.org...")
    req = urllib.request.Request(ARCHIVE_URL, headers={"User-Agent": "M100e"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        outer = resp.read()
    with zipfile.ZipFile(io.BytesIO(outer)) as zf:
        inner = zf.read(INNER_ZIP)
    with zipfile.ZipFile(io.BytesIO(inner)) as zf:
        data = zf.read(INNER_ROM)
    if hashlib.sha256(data).hexdigest() != ROM_SHA256:
        raise RomError("downloaded ROM failed checksum verification")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ROM_CACHE.write_bytes(data)
    if progress:
        progress("ROM cached at %s" % ROM_CACHE)
    return data


def get_system_rom(config, progress=None):
    """Resolve the system ROM: user-configured file, cache, or download."""
    user_path = config["system_rom"]
    if user_path:
        try:
            data = open(user_path, "rb").read()
            if len(data) == ROM_SIZE:
                return data
        except OSError:
            pass
        # fall through to the standard ROM if the user file vanished
    data = load_cached_rom()
    if data is not None:
        return data
    return download_rom(progress)


def load_rom_file(path):
    """Load a user-supplied 32K ROM image (system or option ROM)."""
    data = open(path, "rb").read()
    if len(data) > ROM_SIZE:
        raise RomError("%s is %d bytes; a Model 100 ROM is at most 32768"
                       % (path, len(data)))
    if len(data) < ROM_SIZE:
        data = data + b"\xFF" * (ROM_SIZE - len(data))
    return data
