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
#   3. Създава същия стартер в ~/.local/share/applications и слага
#      иконата в темата с икони (~/.local/share/icons), за да се появи
#      Overlingo в менюто с приложения - с иконата.
#
# И двата стартера сочат към ТЕКУЩОТО местоположение на тази папка -
# ако я преместиш, просто пусни install.sh пак от новото място.

set -e

# Абсолютният път на ТАЗИ папка (работи независимо откъде е пуснат скриптът).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Overlingo - desktop интеграция ==="
echo "Папка: $DIR"

# Със sudo стартерът отива в менюто на root, не в твоето - и не се вижда.
if [ "$(id -u)" -eq 0 ]; then
    echo
    echo "Не пускай install.sh със sudo / като root - стартерът ще отиде в"
    echo "менюто на root. Пусни го като обикновен потребител:  ./install.sh"
    exit 1
fi

chmod +x "$DIR/overlingo"

# Съдържание на стартера. Path= задава работната папка - без него
# менюто стартира програмата от $HOME (програмата вече не зависи от
# това, но така е по-сигурно).
# $2 - иконата: пълен път (за стартера в папката) или име от темата (за менюто).
write_desktop_file() {
    cat > "$1" <<EOF
[Desktop Entry]
Type=Application
Name=Overlingo
Comment=Screen OCR + translation
Exec="$DIR/overlingo"
Path=$DIR
Icon=$2
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
write_desktop_file "$LOCAL_LAUNCHER" "$DIR/assets/icons/app_icon.png"
trust_desktop_file "$LOCAL_LAUNCHER"

# 2) Иконата - в темата с икони на потребителя. Менютата (GNOME, KDE,
# Cinnamon, XFCE...) намират надеждно иконите по име от темата; пълен път
# в Icon= някои от тях не показват.
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/128x128/apps"
mkdir -p "$ICON_DIR"
cp "$DIR/assets/icons/app_icon.png" "$ICON_DIR/overlingo.png"
# Без index.theme в ~/.local/share/icons/hicolor някои среди не търсят там.
HICOLOR_DIR="$(dirname "$(dirname "$ICON_DIR")")"
if [ ! -f "$HICOLOR_DIR/index.theme" ] && [ -f /usr/share/icons/hicolor/index.theme ]; then
    cp /usr/share/icons/hicolor/index.theme "$HICOLOR_DIR/" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HICOLOR_DIR" >/dev/null 2>&1 || true
fi

# 3) Стартер в менюто с приложения
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DESKTOP_DIR"
MENU_LAUNCHER="$DESKTOP_DIR/overlingo.desktop"
write_desktop_file "$MENU_LAUNCHER" "overlingo"

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$MENU_LAUNCHER" || echo "(предупрежденията по-горе не пречат на стартера)"
fi

# Опресняване на менюто - всяка среда си има свой начин; липсващите
# команди не са грешка (менюто ще се опресни при следващо влизане).
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi
if command -v xdg-desktop-menu >/dev/null 2>&1; then
    xdg-desktop-menu forceupdate 2>/dev/null || true
fi
for sycoca in kbuildsycoca6 kbuildsycoca5; do  # KDE Plasma
    if command -v "$sycoca" >/dev/null 2>&1; then
        "$sycoca" >/dev/null 2>&1 || true
        break
    fi
done

echo
echo "Готово! Overlingo вече може да се отваря:"
echo "  - с двоен клик върху стартера 'Overlingo' (с иконата на програмата)"
echo "    в тази папка - НЕ върху файла 'overlingo' без икона;"
echo "  - от менюто с приложения, като търсиш 'Overlingo'"
echo "    ($MENU_LAUNCHER)."
echo
echo "Ако в менюто още я няма или е без икона - излез от системата и влез"
echo "пак (някои среди опресняват менюто само тогава)."
echo
echo "Ако файловият мениджър при първия двоен клик пита дали стартерът"
echo "е надежден, избери 'Стартирай'/'Маркирай като изпълним' - пита"
echo "само веднъж."
echo
