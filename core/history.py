"""
TRANSLATION HISTORY

Keeps the last N translations only while the program is open (nothing is
written to disk - the text from the screen may be private). Does not depend on Qt -
the UI (ui/history_window.py) only reads items().
"""

from dataclasses import dataclass

DEFAULT_MAX_ITEMS = 20


@dataclass(frozen=True)
class HistoryEntry:
    source: str
    translation: str


class TranslationHistory:
    def __init__(self, max_items=DEFAULT_MAX_ITEMS):
        self.max_items = max_items
        self._entries = []  # newest first

    def add(self, source, translation):
        """
        Adds a translation at the top. If the same source text is already present
        (e.g. on auto-refresh or "Translate again" on unchanged
        text), the old entry is removed - otherwise the history fills up with duplicates.
        Empty text or translation is not recorded.
        """
        source = (source or "").strip()
        translation = (translation or "").strip()
        if not source or not translation:
            return
        key = _normalize(source)
        self._entries = [e for e in self._entries if _normalize(e.source) != key]
        self._entries.insert(0, HistoryEntry(source, translation))
        del self._entries[self.max_items:]

    def items(self):
        """A copy of the entries, newest first."""
        return list(self._entries)

    def clear(self):
        self._entries.clear()

    def __len__(self):
        return len(self._entries)


def _normalize(text):
    return " ".join(text.split()).lower()


class SessionStats:
    """
    How many translations were made in the current session and how many of them came from
    the cache (no request to the service - useful with a paid key). Counts both
    screen translations and the text translation window. Not stored on disk.
    """

    def __init__(self):
        self.translations = 0
        self.cache_hits = 0

    def record(self, from_cache):
        self.translations += 1
        if from_cache:
            self.cache_hits += 1
