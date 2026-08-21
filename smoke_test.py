from __future__ import annotations

import importlib.util
import sys

MODULES = [
    'fastapi',
    'uvicorn',
    'numpy',
    'faster_whisper',
    'sounddevice',
    'pynput',
    'multipart',
]


def main() -> int:
    ok = True
    for name in MODULES:
        present = importlib.util.find_spec(name) is not None
        print(f'{name}: {"OK" if present else "MISSING"}')
        ok = ok and present

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        print(f'microphone_devices_found: {len(devices)}')
        default = sd.default.device
        print(f'default_device: {default}')
    except Exception as exc:
        ok = False
        print(f'sounddevice_check_failed: {exc}')

    if not ok:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
