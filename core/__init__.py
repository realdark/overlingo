"""
UI-independent logic: translation, OCR, settings, history, hotkeys, etc.

Modules are imported individually (from core.translations import ...). There
is deliberately no list of "convenience" imports here - it went unused, went stale
with every new module, and made every "import core.something" load everything.
"""
