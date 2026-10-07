#!/bin/bash
# Overlingo - one-time desktop integration setup (Linux).
#
# What it does:
#   1. Makes the binary executable (in case the bit was lost on extraction).
#   2. Creates an "Overlingo.desktop" launcher IN THIS FOLDER - that is
#      what you double-click. Many file managers (Thunar, Nautilus)
#      detect the "overlingo" binary itself as a "shared library" and
#      will NOT run it on double click even if it is executable - hence
#      the launcher.
#   3. Creates the same launcher in ~/.local/share/applications and puts
#      the icon into the icon theme (~/.local/share/icons) so Overlingo
#      shows up in the application menu - with its icon.
#
# Both launchers point to the CURRENT location of this folder -
# if you move it, just run install.sh again from the new location.

set -e

# Absolute path of THIS folder (works regardless of where the script is run from).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Overlingo - desktop integration ==="
echo "Folder: $DIR"

# With sudo the launcher ends up in root's menu, not yours - and you won't see it.
if [ "$(id -u)" -eq 0 ]; then
    echo
    echo "Don't run install.sh with sudo / as root - the launcher would end up in"
    echo "root's menu. Run it as a regular user:  ./install.sh"
    exit 1
fi

chmod +x "$DIR/overlingo"

# Launcher contents. Path= sets the working directory - without it the
# menu starts the app from $HOME (the app no longer depends on this,
# but it is safer).
# $2 - the icon: full path (for the in-folder launcher) or theme name (for the menu).
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

# Marks the launcher as "trusted" so the file manager doesn't show an
# "Untrusted launcher" prompt on the first double click. Desktops store this
# differently - try both, without failing if it doesn't work.
trust_desktop_file() {
    command -v gio >/dev/null 2>&1 || return 0
    # GNOME (Nautilus) and derivatives
    gio set "$1" metadata::trusted true 2>/dev/null || true
    # XFCE (Thunar 4.18+) - stores a checksum of the file
    if command -v sha256sum >/dev/null 2>&1; then
        gio set -t string "$1" metadata::xfce-exe-checksum \
            "$(sha256sum "$1" | cut -d' ' -f1)" 2>/dev/null || true
    fi
}

# 1) Launcher in the folder itself (for double click)
LOCAL_LAUNCHER="$DIR/Overlingo.desktop"
write_desktop_file "$LOCAL_LAUNCHER" "$DIR/assets/icons/app_icon.png"
trust_desktop_file "$LOCAL_LAUNCHER"

# 2) The icon - into the user's icon theme. Menus (GNOME, KDE,
# Cinnamon, XFCE...) reliably find icons by theme name; some of them
# don't display a full path in Icon=.
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/128x128/apps"
mkdir -p "$ICON_DIR"
cp "$DIR/assets/icons/app_icon.png" "$ICON_DIR/overlingo.png"
# Without index.theme in ~/.local/share/icons/hicolor some desktops don't look there.
HICOLOR_DIR="$(dirname "$(dirname "$ICON_DIR")")"
if [ ! -f "$HICOLOR_DIR/index.theme" ] && [ -f /usr/share/icons/hicolor/index.theme ]; then
    cp /usr/share/icons/hicolor/index.theme "$HICOLOR_DIR/" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HICOLOR_DIR" >/dev/null 2>&1 || true
fi

# 3) Launcher in the application menu
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DESKTOP_DIR"
MENU_LAUNCHER="$DESKTOP_DIR/overlingo.desktop"
write_desktop_file "$MENU_LAUNCHER" "overlingo"

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$MENU_LAUNCHER" || echo "(the warnings above do not affect the launcher)"
fi

# Refresh the menu - every desktop has its own way; missing commands
# are not an error (the menu will refresh on next login).
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
echo "Done! Overlingo can now be opened:"
echo "  - by double-clicking the 'Overlingo' launcher (with the app icon)"
echo "    in this folder - NOT the 'overlingo' file without an icon;"
echo "  - from the application menu, by searching for 'Overlingo'"
echo "    ($MENU_LAUNCHER)."
echo
echo "If it's not in the menu yet or has no icon - log out and log back"
echo "in (some desktops only refresh the menu then)."
echo
echo "If the file manager asks on the first double click whether the launcher"
echo "is trusted, choose 'Launch'/'Mark as executable' - it only asks"
echo "once."
echo
