"""Persisted emulator settings and state paths."""

import json
import pathlib

STATE_DIR = pathlib.Path.home() / ".m100e"
ROM_CACHE = STATE_DIR / "m100rom.bin"
RAM_IMAGE = STATE_DIR / "ram.bin"
CONFIG_FILE = STATE_DIR / "config.json"

DEFAULTS = {
    # 8, 16, 24 or 32 KB of battery-backed RAM
    "ram_size": 32768,
    # host:port the RS-232 port connects to when the software raises DTR/TX
    "serial_host": "telehack.com:23",
    # phone "numbers" the modem can pulse-dial, mapped to internet hosts
    "dial_directory": {
        "1": "telehack.com:23",
        "2": "bbs.fozztexx.com:23",
        "3": "1984.ws:23",
    },
    # "authentic" paces serial at the programmed baud rate, "fast" is snappy
    "baud_pacing": "authentic",
    # LCD contrast wheel position, 0.0-1.0 (Ctrl+Up / Ctrl+Down)
    "contrast": 0.55,
    "fullscreen": True,
    # path of a user-supplied system ROM (None = auto-downloaded cache)
    "system_rom": None,
    # path of an option ROM image loaded in the socket (None = empty)
    "option_rom": None,
    # print jobs are rendered to PDFs in this folder
    "printer_dir": str(pathlib.Path(__file__).resolve().parents[1]
                       / "printer"),
}


class Config:
    def __init__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.data = dict(DEFAULTS)
        if CONFIG_FILE.exists():
            try:
                stored = json.loads(CONFIG_FILE.read_text())
                for k in DEFAULTS:
                    if k in stored:
                        self.data[k] = stored[k]
            except (ValueError, OSError):
                pass

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def save(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self.data, indent=2))
