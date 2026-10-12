"""
ENVIRONMENT FOR PROGRAMS WE START (Linux build)

The PyInstaller build sets LD_LIBRARY_PATH to its own _internal folder while
it starts. Every program we run inherits it - the system's tesseract,
xprop, xdg-open... - and then loads the build's libraries instead of the
system's. The build is made on an older Ubuntu (GitHub Actions), so on a newer
system tesseract failed with "version `GLIBCXX_3.4.32' not found".

PyInstaller keeps the original value in LD_LIBRARY_PATH_ORIG. The program
itself doesn't need the variable after it has started (the dynamic loader
reads it only at startup), so we put the original back for the whole process.
See "Bundled libraries and external programs" in the PyInstaller docs.
"""

import os
import sys

_VARIABLES = ("LD_LIBRARY_PATH",)


def restore_library_path(environ=None, frozen=None, platform=None):
    """Puts back the library path the user had before the build changed it (only in the Linux build)."""
    environ = os.environ if environ is None else environ
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    platform = sys.platform if platform is None else platform
    if not frozen or not platform.startswith("linux"):
        return
    for name in _VARIABLES:
        original = environ.get(name + "_ORIG")
        if original is not None:
            environ[name] = original
        else:
            environ.pop(name, None)
