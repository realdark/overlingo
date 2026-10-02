#!/bin/bash
# Overlingo - еднократна инсталация за desktop интеграция (Linux).
#
# Прави следното:
#   1. Слага изпълними права на бинарника (ако липсват след разархивиране).
#   2. Създава стартер "Overlingo.desktop" В ТАЗИ ПАПКА - него се
#      кликва два пъти. Самият бинарник "overlingo" много файлови
#      мениджъри (Thunar, Nautilus) го разпознават като "shared library"
#      и НЕ го пускат с двоен клик, дори да е изпълним - затова е нужен
#      стартерът.
#   3. Създава същия стартер в ~/.local/share/applications, за да се
#      появи Overlingo в менюто с приложения.
#
# И двата стартера сочат към ТЕКУЩОТО местоположение на тази папка -
# ако я преместиш, просто пусни install.sh пак от новото място.

set -e

# Абсолютният път на ТАЗИ папка (работи независимо откъде е пуснат скриптът).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Overlingo - desktop интеграция ==="
echo "Папка: $DIR"

chmod +x "$DIR/overlingo"

# Съдържание на стартера. Path= задава работната папка - без него
# менюто стартира програмата от $HOME (програмата вече не зависи от
# това, но така е по-сигурно).
write_desktop_file() {
    cat > "$1" <<EOF
[Desktop Entry]
Type=Application
Name=Overlingo
Comment=Screen OCR + translation
Exec="$DIR/overlingo"
Path=$DIR
Icon=$DIR/assets/icons/app_icon.png
Terminal=false
Categories=Utility;Office;
StartupWMClass=overlingo
EOF
    chmod +x "$1"
}

# Маркира стартера като "доверен", за да не пита файловият мениджър
# "Недоверен стартер" при първия двоен клик. Различните среди пазят това
# по различен начин - пробваме и двата, без грешка ако не стане.
trust_desktop_file() {
    command -v gio >/dev/null 2>&1 || return 0
    # GNOME (Nautilus) и производни
    gio set "$1" metadata::trusted true 2>/dev/null || true
    # XFCE (Thunar 4.18+) - пази контролна сума на файла
    if command -v sha256sum >/dev/null 2>&1; then
        gio set -t string "$1" metadata::xfce-exe-checksum \
            "$(sha256sum "$1" | cut -d' ' -f1)" 2>/dev/null || true
    fi
}

# 1) Стартер в самата папка (за двоен клик)
LOCAL_LAUNCHER="$DIR/Overlingo.desktop"
write_desktop_file "$LOCAL_LAUNCHER"
trust_desktop_file "$LOCAL_LAUNCHER"

# 2) Стартер в менюто с приложения
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
write_desktop_file "$DESKTOP_DIR/overlingo.desktop"

# Не всички дистрибуции имат update-desktop-database - не е грешка, ако
# липсва (менюто само ще се опресни малко по-късно).
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo
echo "Готово! Overlingo вече може да се отваря:"
echo "  - с двоен клик върху стартера 'Overlingo' (с иконата на програмата)"
echo "    в тази папка - НЕ върху файла 'overlingo' без икона;"
echo "  - от менюто с приложения, като търсиш 'Overlingo'."
echo
echo "Ако файловият мениджър при първия двоен клик пита дали стартерът"
echo "е надежден, избери 'Стартирай'/'Маркирай като изпълним' - пита"
echo "само веднъж."
echo
