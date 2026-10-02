import unittest

from core.hotkey_manager import format_combo


class FormatComboTest(unittest.TestCase):
    def test_modifiers_and_key(self):
        self.assertEqual(format_combo("<ctrl>+<alt>+t"), "Ctrl+Alt+T")

    def test_shift_and_named_key(self):
        self.assertEqual(format_combo("<shift>+<f5>"), "Shift+F5")

    def test_empty(self):
        self.assertEqual(format_combo(""), "")
        self.assertEqual(format_combo(None), "")


if __name__ == "__main__":
    unittest.main()
