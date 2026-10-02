#!/bin/bash
echo "=== Build Overlingo (onedir, Linux) ==="

# Спиране при грешка
set -e

# Версията се чете от utils/version.py - единственото място, където се сменя.
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' utils/version.py)"
if [ -z "$VERSION" ]; then
    echo "Не мога да прочета APP_VERSION от utils/version.py"
    exit 1
fi
ARCH="$(uname -m)"

# Изчистване на стари билдове
rm -rf build
rm -rf dist
rm -f overlingo.spec

# Иконата трябва да е .png или .ico
ICON="assets/icons/app_icon.png"

# Стартираме PyInstaller
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
  main.py
  # pynput се внася от core/hotkey_manager.py - PyInstaller го засича
  # статично. Hotkey функцията е активна на Linux само под X11 сесия
  # (HOTKEY_SUPPORTED проверка - виж core/hotkey_manager.py), не под
  # Wayland. "_xorg" е Linux backend-ът на pynput (виж pynput docs) -
  # НЕ "_win32", това е за build.bat.

# Копиране на assets
echo "Copying assets..."
cp -r assets dist/overlingo/

# README за крайния потребител (различен от техническия README.md в
# repo-то) - обяснява Tesseract изискването и първите стъпки, без да
# е нужно да чете кода. Английски е основният README.txt, българският
# е README_bg.txt (интерфейсът е по подразбиране на български, но
# английският е по-универсален за README на дистрибуирания архив).
cp README_DIST_en.txt dist/overlingo/README.txt
cp README_DIST_bg.txt dist/overlingo/README_bg.txt

# install.sh - еднократен desktop-интеграционен скрипт, за да може
# Overlingo да се отваря с двоен клик / от менюто с приложения, вместо
# само от терминал (виж коментарите в самия install.sh).
cp install.sh dist/overlingo/install.sh
chmod +x dist/overlingo/install.sh

# Tesseract НЕ се пакетира - Overlingo разчита изцяло на системна
# инсталация (виж README.md "Инсталация"), потребителят го слага сам
# (apt/dnf/pacman). Виж и коментара при TESSERACT_PATHS в
# utils/config.py защо съзнателно отказахме от AppImage bundling.

# НЕ копираме settings.json нарочно - съдържа лични настройки/API
# ключове; приложението си генерира чист файл при първо стартиране
# (виж core/settings_manager.py - fallback към DEFAULT_SETTINGS).

# Архивиране - от вътре в dist/, за да съдържа архивът папка
# "overlingo/", а не пълния път dist/overlingo/... (по-чисто при
# разархивиране от потребителя).
echo "Archiving..."
ARCHIVE_NAME="Overlingo-${VERSION}-linux-${ARCH}.tar.gz"
(cd dist && tar -czf "$ARCHIVE_NAME" overlingo)

echo
echo "=== Ready! View dist/overlingo/overlingo ==="
echo "=== Archive: dist/${ARCHIVE_NAME} ==="
echo
