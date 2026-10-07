#!/bin/bash
# macOS build: Overlingo.app (onedir inside an .app bundle) + zip archive.
# Run on a Mac (or in GitHub Actions - see .github/workflows/build.yml).
# The architecture is that of the machine: arm64 (Apple Silicon) or x86_64 (Intel).
echo "=== Build Overlingo (macOS .app) ==="

set -e
cd "$(dirname "$0")"

VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' utils/version.py)"
if [ -z "$VERSION" ]; then
    echo "Cannot read APP_VERSION from utils/version.py"
    exit 1
fi
ARCH="$(uname -m)"

rm -rf build dist
rm -f Overlingo.spec

# assets goes INSIDE the .app bundle (--add-data) - utils/config.py finds it
# via sys._MEIPASS. Settings, logs and offline translation models live in
# ~/Library/Application Support/Overlingo (the bundle is never modified).
#
# pynput (global hotkeys) is excluded: hotkeys are not supported on macOS yet
# (they need Accessibility permission - see core/hotkey_manager.py),
# and on macOS pynput also pulls in the large pyobjc.
pyinstaller --onedir --windowed \
  --name "Overlingo" \
  --icon="assets/icons/app_icon.icns" \
  --osx-bundle-identifier "com.realdark.overlingo" \
  --add-data "assets:assets" \
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
  --exclude-module pynput \
  --collect-all ctranslate2 \
  --collect-all sentencepiece \
  --exclude-module torch \
  --exclude-module transformers \
  --exclude-module tensorflow \
  main.py

APP="dist/Overlingo.app"
PLIST="$APP/Contents/Info.plist"

# The version shown in Finder's "Get Info" (Cmd+I) and other plist keys.
# PyInstaller doesn't set them from the command line.
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace LSMinimumSystemVersion -string "11.0" "$PLIST"
plutil -replace NSHighResolutionCapable -bool true "$PLIST"

# Editing Info.plist breaks the signature PyInstaller applies - re-sign
# "ad-hoc" (no Apple Developer account). Without a signature Apple
# Silicon refuses to run the app at all.
codesign --force --deep --sign - "$APP"

# Archive: Overlingo.app + the READMEs, in a folder named after the version.
echo "Archiving..."
PACKAGE="Overlingo-${VERSION}-macos-${ARCH}"
mkdir -p "dist/$PACKAGE"
cp -R "$APP" "dist/$PACKAGE/"
cp README_DIST_en.txt "dist/$PACKAGE/README.txt"
cp README_DIST_bg.txt "dist/$PACKAGE/README_bg.txt"
# ditto preserves the .app bundle's symlinks and attributes (as does a Finder zip).
(cd dist && ditto -c -k --keepParent "$PACKAGE" "$PACKAGE.zip")

echo
echo "=== Ready! dist/Overlingo.app ==="
echo "=== Archive: dist/${PACKAGE}.zip ==="
echo
