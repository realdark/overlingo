"""
WINDOWS: PyQt5'S OLD MSVCP140.DLL CRASHES ctranslate2 / sentencepiece

PyQt5 (the PyQt5-Qt5 5.15.2 package, the last one for Windows) ships its own
msvcp140.dll from 2020 in PyQt5\\Qt5\\bin. Once PyQt5 is loaded first,
Windows uses that copy for everyone. ctranslate2 and sentencepiece are built
with a newer Visual Studio and crash with this old file on the first mutex
lock - the process vanishes without an error (code 3221225477 / 0xC0000005).

PyInstaller crashes the same way during the build ("Isolated subprocess
crashed while importing package 'sentencepiece'"), because it imports the
packages in one process, starting with PyQt5. It would also put the old
file into the build.

Fix: if Windows\\System32 has a newer version of the same file, the old
one in PyQt5 is renamed to *.old - Qt then uses the system one
(backward compatible). Nothing is deleted; to revert, remove ".old" from the name.

Run automatically by build.bat; can also be run by hand: python tools\\fix_qt_runtime.py
"""

import ctypes
import importlib.util
import os
import sys
from pathlib import Path

# The Windows console (and GitHub Actions logs) is often not UTF-8 -
# without this, non-ASCII text fails with UnicodeEncodeError.
if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

RUNTIME_DLLS = ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll",
                "msvcp140_codecvt_ids.dll", "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll")


def file_version(path):
    """(major, minor, build, private) from the DLL's version resource; None if absent."""
    version_dll = ctypes.WinDLL("version")
    size = version_dll.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version_dll.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    info = ctypes.c_void_p()
    length = ctypes.c_uint()
    if not version_dll.VerQueryValueW(buffer, "\\", ctypes.byref(info), ctypes.byref(length)):
        return None
    # VS_FIXEDFILEINFO: dwSignature, dwStrucVersion, dwFileVersionMS, dwFileVersionLS, ...
    fields = ctypes.cast(info, ctypes.POINTER(ctypes.c_uint32 * 4)).contents
    ms, ls = fields[2], fields[3]
    return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def main():
    if sys.platform != "win32":
        return 0
    spec = importlib.util.find_spec("PyQt5")  # no import - otherwise the DLLs get locked
    if spec is None or not spec.submodule_search_locations:
        print("PyQt5 is not installed - nothing to fix.")
        return 0
    qt_bin = Path(list(spec.submodule_search_locations)[0]) / "Qt5" / "bin"
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"

    changed = 0
    for name in RUNTIME_DLLS:
        qt_file, system_file = qt_bin / name, system32 / name
        if not qt_file.is_file() or not system_file.is_file():
            continue
        qt_version, system_version = file_version(qt_file), file_version(system_file)
        if not qt_version or not system_version or system_version <= qt_version:
            continue
        backup = qt_file.with_name(name + ".old")
        try:
            if backup.exists():
                backup.unlink()
            qt_file.rename(backup)
        except OSError as e:
            print(f"Could not rename {qt_file}: {e}")
            print("Close all Python programs (including Overlingo) and run again.")
            return 1
        changed += 1
        print(f"{name}: PyQt5 {'.'.join(map(str, qt_version))} -> system "
              f"{'.'.join(map(str, system_version))} (old one kept as {backup.name})")

    if not changed:
        print("PyQt5's C++ runtime libraries are fine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
