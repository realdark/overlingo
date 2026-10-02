"""
ИСТОРИЯ НА ПРЕВОДИТЕ

Пази последните N превода само докато програмата е отворена (нищо не се
записва на диска - текстът от екрана може да е личен). Не зависи от Qt -
UI-ят (ui/history_window.py) само чете items().
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
        self._entries = []  # най-новият е първи

    def add(self, source, translation):
        """
        Добавя превод най-отгоре. Ако същият изходен текст вече го има
        (напр. при авто-рефреш или "Преведи отново" върху непроменен
        текст), старият запис се маха - иначе историята се пълни с копия.
        Празен текст или превод не се записват.
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
        """Копие на записите, най-новият първи."""
        return list(self._entries)

    def clear(self):
        self._entries.clear()

    def __len__(self):
        return len(self._entries)


def _normalize(text):
    return " ".join(text.split()).lower()


class SessionStats:
    """
    Колко превода са направени в текущата сесия и колко от тях са дошли от
    кеша (без заявка към услугата - полезно при платен ключ). Брои и
    превода от екрана, и прозореца за превод на текст. Не се пази на диска.
    """

    def __init__(self):
        self.translations = 0
        self.cache_hits = 0

    def record(self, from_cache):
        self.translations += 1
        if from_cache:
            self.cache_hits += 1
