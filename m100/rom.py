"""System ROM location and option ROM loading.

M100e neither ships nor downloads ROM images.  You must provide your own
32K Model 100 system ROM dump.  The emulator finds it in one of three
ways, in this order:

  1. the "system_rom" path in ~/.m100e/config.json (set via the menu's
     "Load system ROM..." or the first-run file dialog),
  2. a file placed at ~/.m100e/m100rom.bin,
  3. a file dialog on startup when neither of the above exists - the
     chosen image is installed to ~/.m100e/m100rom.bin for next time.
"""

import shutil

from .config import ROM_CACHE, STATE_DIR

ROM_SIZE = 32768


class RomError(Exception):
    pass


def looks_like_m100_rom(data):
    """Heuristic for the standard Tandy image (a custom or non-US ROM can
    legitimately fail this - it's used for warnings, not rejection)."""
    return len(data) == ROM_SIZE and b"(C)Microsoft" in data


def get_system_rom(config, progress=None):
    """Resolve the user-provided system ROM.  Raises RomError when no ROM
    has been installed yet."""
    user_path = config["system_rom"]
    if user_path:
        try:
            data = open(user_path, "rb").read()
            if len(data) == ROM_SIZE:
                return data
        except OSError:
            pass  # configured file vanished; fall through to the cache
    if ROM_CACHE.exists():
        data = ROM_CACHE.read_bytes()
        if len(data) == ROM_SIZE:
            return data
    raise RomError(
        "No system ROM installed.  Provide your own 32K Model 100 ROM "
        "dump: copy it to %s, or start the emulator and pick it in the "
        "file dialog." % ROM_CACHE)


def install_system_rom(path):
    """Validate a user-chosen ROM file and install it as the default.
    Returns the ROM bytes."""
    data = open(path, "rb").read()
    if len(data) != ROM_SIZE:
        raise RomError("%s is %d bytes; a Model 100 system ROM is exactly "
                       "32768 bytes" % (path, len(data)))
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(path, ROM_CACHE)
    except OSError:
        pass  # not fatal: we can still run from the original location
    return data


def load_rom_file(path):
    """Load a user-supplied 32K ROM image (system or option ROM)."""
    data = open(path, "rb").read()
    if len(data) > ROM_SIZE:
        raise RomError("%s is %d bytes; a Model 100 ROM is at most 32768"
                       % (path, len(data)))
    if len(data) < ROM_SIZE:
        data = data + b"\xFF" * (ROM_SIZE - len(data))
    return data
