import unittest

from core.history import SessionStats, TranslationHistory


class TranslationHistoryTest(unittest.TestCase):
    def test_newest_first(self):
        history = TranslationHistory()
        history.add("one", "едно")
        history.add("two", "две")
        self.assertEqual([e.source for e in history.items()], ["two", "one"])

    def test_same_source_moves_to_top_without_duplicate(self):
        history = TranslationHistory()
        history.add("Hello world", "Здравей, свят")
        history.add("other", "друго")
        history.add("hello   WORLD", "Здравей, свят!")
        items = history.items()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].translation, "Здравей, свят!")

    def test_keeps_only_max_items(self):
        history = TranslationHistory(max_items=3)
        for i in range(5):
            history.add(f"text {i}", f"превод {i}")
        self.assertEqual([e.source for e in history.items()], ["text 4", "text 3", "text 2"])

    def test_empty_values_are_ignored(self):
        history = TranslationHistory()
        history.add("", "нещо")
        history.add("something", "  ")
        self.assertEqual(len(history), 0)

    def test_items_returns_copy(self):
        history = TranslationHistory()
        history.add("a", "б")
        history.items().clear()
        self.assertEqual(len(history), 1)

    def test_clear(self):
        history = TranslationHistory()
        history.add("a", "б")
        history.clear()
        self.assertEqual(history.items(), [])


class SessionStatsTest(unittest.TestCase):
    def test_counts_translations_and_cache_hits(self):
        stats = SessionStats()
        stats.record(from_cache=False)
        stats.record(from_cache=True)
        stats.record(from_cache=True)
        self.assertEqual((stats.translations, stats.cache_hits), (3, 2))


if __name__ == "__main__":
    unittest.main()
