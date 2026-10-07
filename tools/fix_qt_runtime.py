"""
WINDOWS: СТАРИЯТ MSVCP140.DLL НА PyQt5 СРИВА ctranslate2 / sentencepiece

PyQt5 (пакетът PyQt5-Qt5 5.15.2, последният за Windows) носи в
PyQt5\\Qt5\\bin своя msvcp140.dll от 2020 г. Щом PyQt5 се зареди първи,
Windows ползва него за всички. ctranslate2 и sentencepiece са компилирани
с по-нов Visual Studio и с този стар файл падат при първото заключване на
mutex - процесът изчезва без грешка (код 3221225477 / 0xC0000005).

Така пада и PyInstaller при билд ("Isolated subprocess crashed while
importing package 'sentencepiece'"), защото той внася пакетите в един
процес, започвайки с PyQt5. Освен това би сложил стария файл в билда.

Решение: ако в Windows\\System32 има по-нова версия на същия файл,
старият в PyQt5 се преименува на *.old - тогава Qt ползва системния
(съвместим назад). Нищо не се трие; връщане: махни ".old" от името.

Пуска се автоматично от build.bat; може и ръчно: python tools\\fix_qt_runtime.py
"""

import ctypes
import importlib.util
import os
import sys
from pathlib import Path

# Конзолата на Windows (и логовете в GitHub Actions) често не е UTF-8 -
# без това българският текст гърми с UnicodeEncodeError.
if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

RUNTIME_DLLS = ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll",
                "msvcp140_codecvt_ids.dll", "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll")


def file_version(path):
    """(major, minor, build, private) от ресурса на DLL файла; None, ако няма."""
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
    spec = importlib.util.find_spec("PyQt5")  # без import - иначе DLL-ите се заключват
    if spec is None or not spec.submodule_search_locations:
        print("PyQt5 не е инсталиран - няма какво да се оправя.")
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
            print(f"Не успях да преименувам {qt_file}: {e}")
            print("Затвори всички Python програми (и Overlingo) и пусни отново.")
            return 1
        changed += 1
        print(f"{name}: PyQt5 {'.'.join(map(str, qt_version))} -> системен "
              f"{'.'.join(map(str, system_version))} (старият е запазен като {backup.name})")

    if not changed:
        print("C++ библиотеките на PyQt5 са наред.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
