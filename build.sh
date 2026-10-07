#!/bin/bash
echo "=== Build Overlingo (onedir, Linux) ==="

# Stop on error
set -e

# Run from the script's directory, regardless of where it was launched from.
cd "$(dirname "$(readlink -f "$0")")"

# The version is read from utils/version.py - the only place it is changed.
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' utils/version.py)"
if [ -z "$VERSION" ]; then
    echo "Cannot read APP_VERSION from utils/version.py"
    exit 1
fi
ARCH="$(uname -m)"

# Clean up old builds
rm -rf build
rm -rf dist
rm -f overlingo.spec

# The icon must be .png or .ico
ICON="assets/icons/app_icon.png"

# Run PyInstaller
pyinstaller --onedir --noconsole \
  --icon="$ICON" \
  --name "overlingo" \
  --hidden-import=mss \
  --hidden-import=mss.tools \
  --hidden-import=edge_tts \
  --hidden-import=pygame \
  --hidden-import=deepl \
  --hidden-import=pytesseract \
  --hidden-import=PyQt5.QtCore \
  --hidden-import=PyQt5.QtGui \
  --hidden-import=PyQt5.QtWidgets \
  --hidden-import=PyQt5.QtNetwork \
  --hidden-import=cv2 \
  --hidden-import=numpy \
  --hidden-import=pynput \
  --hidden-import=pynput.keyboard \
  --hidden-import=pynput.keyboard._xorg \
  --collect-all ctranslate2 \
  --exclude-module torch \
  --exclude-module transformers \
  --exclude-module tensorflow \
  --collect-all sentencepiece \
  main.py
  # ctranslate2/sentencepiece - offline translation (core/argos.py). They are
  # imported lazily (inside a function) and ship their own native
  # libraries - --collect-all grabs everything so no .so is missing from the build.
  # --exclude-module: ctranslate2 optionally uses torch - we don't bundle it.
  # pynput is imported by core/hotkey_manager.py - PyInstaller detects it
  # statically. The hotkey feature works on Linux only in an X11 session
  # (HOTKEY_SUPPORTED check - see core/hotkey_manager.py), not under
  # Wayland. "_xorg" is pynput's Linux backend (see pynput docs) -
  # NOT "_win32", that one is for build.bat.

# Copy assets
echo "Copying assets..."
cp -r assets dist/overlingo/

# End-user README (separate from the technical README.md in the repo) -
# explains the Tesseract requirement and first steps without having to
# read the code. English is the main README.txt, Bulgarian is
# README_bg.txt (English is the more universal choice for the README of
# the distributed archive).
cp README_DIST_en.txt dist/overlingo/README.txt
cp README_DIST_bg.txt dist/overlingo/README_bg.txt

# install.sh - one-time desktop integration script so Overlingo can be
# opened with a double click / from the application menu instead of only
# from a terminal (see the comments in install.sh itself).
cp install.sh dist/overlingo/install.sh
chmod +x dist/overlingo/install.sh

# Tesseract is NOT bundled - Overlingo relies entirely on a system
# installation (see README.md "Installation"); the user installs it
# (apt/dnf/pacman). See also the comment at TESSERACT_PATHS in
# utils/config.py for why we deliberately dropped AppImage bundling.

# settings.json is deliberately NOT copied - it contains personal settings/API
# keys; the app generates a clean file on first launch
# (see core/settings_manager.py - fallback to DEFAULT_SETTINGS).

# Archive from inside dist/ so the archive contains an "overlingo/"
# folder rather than the full dist/overlingo/... path (cleaner when the
# user extracts it).
echo "Archiving..."
ARCHIVE_NAME="Overlingo-${VERSION}-linux-${ARCH}.tar.gz"
(cd dist && tar -czf "$ARCHIVE_NAME" overlingo)

echo
echo "=== Ready! View dist/overlingo/overlingo ==="
echo "=== Archive: dist/${ARCHIVE_NAME} ==="
echo
