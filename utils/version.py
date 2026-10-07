"""
APPLICATION VERSION - the only place where it is changed.

Read by the About window (ui/dialogs.py) and by build.sh / build.bat
(for the archive name). Deliberately a separate file with no imports - the
build scripts read it without loading PyQt5/pygame and the other libraries.
"""

APP_VERSION = "3.3"
