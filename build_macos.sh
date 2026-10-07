#!/bin/bash
# Билд за macOS: Overlingo.app (onedir в .app пакет) + zip архив.
# Пуска се на Mac (или в GitHub Actions - виж .github/workflows/build.yml).
# Архитектурата е тази на машината: arm64 (Apple Silicon) или x86_64 (Intel).
echo "=== Build Overlingo (macOS .app) ==="

set -e
cd "$(dirname "$0")"

VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' utils/version.py)"
if [ -z "$VERSION" ]; then
    echo "Не мога да прочета APP_VERSION от utils/version.py"
    exit 1
fi
ARCH="$(uname -m)"

rm -rf build dist
rm -f Overlingo.spec

# assets влиза ВЪТРЕ в .app пакета (--add-data) - utils/config.py го намира
# през sys._MEIPASS. Настройките, логовете и моделите за превод без интернет
# са в ~/Library/Application Support/Overlingo (пакетът не се променя).
#
# pynput (глобални hotkey-и) е изключен: на macOS hotkey-ите засега не се
# поддържат (иска Accessibility разрешение - виж core/hotkey_manager.py),
# а pynput там дърпа и голямата pyobjc.
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

# Версията в "За програмата" на Finder (Cmd+I) и текстът при въпроса за
# разрешение. PyInstaller не ги задава от командния ред.
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace LSMinimumSystemVersion -string "11.0" "$PLIST"
plutil -replace NSHighResolutionCapable -bool true "$PLIST"

# Промяната на Info.plist разваля подписа, който PyInstaller слага -
# подписваме отново "ad-hoc" (без Apple Developer акаунт). Без подпис
# Apple Silicon изобщо не пуска програмата.
codesign --force --deep --sign - "$APP"

# Архив: Overlingo.app + README-тата, в папка с името на версията.
echo "Archiving..."
PACKAGE="Overlingo-${VERSION}-macos-${ARCH}"
mkdir -p "dist/$PACKAGE"
cp -R "$APP" "dist/$PACKAGE/"
cp README_DIST_en.txt "dist/$PACKAGE/README.txt"
cp README_DIST_bg.txt "dist/$PACKAGE/README_bg.txt"
# ditto пази symlink-овете и атрибутите на .app пакета (zip от Finder също).
(cd dist && ditto -c -k --keepParent "$PACKAGE" "$PACKAGE.zip")

echo
echo "=== Ready! dist/Overlingo.app ==="
echo "=== Archive: dist/${PACKAGE}.zip ==="
echo
