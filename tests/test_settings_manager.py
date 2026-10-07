import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import settings_manager
from core.settings_manager import SettingsManager, SettingsValidationError
from utils.config import DEFAULT_SETTINGS


class SettingsManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "settings.json"
        patcher = mock.patch.object(settings_manager, "SETTINGS_FILE", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.manager = SettingsManager()

    def test_defaults_when_file_missing(self):
        self.assertEqual(self.manager.load(), DEFAULT_SETTINGS)

    def test_saved_values_override_defaults(self):
        self.path.write_text(json.dumps({"text_size": 20}), encoding="utf-8")
        settings = self.manager.load()
        self.assertEqual(settings["text_size"], 20)
        self.assertEqual(settings["ocr_lang"], DEFAULT_SETTINGS["ocr_lang"])

    def test_old_ollama_settings_are_migrated(self):
        self.path.write_text(json.dumps({
            "translation_api": "ollama", "ollama_model": "llama3.2", "ollama_url": "http://localhost:11434",
        }), encoding="utf-8")
        settings = self.manager.load()
        self.assertEqual(settings["translation_api"], "google")
        self.assertNotIn("ollama_model", settings)
        self.assertNotIn("ollama_url", settings)

    def test_offline_translation_needs_libraries_and_models(self):
        settings = dict(DEFAULT_SETTINGS, translation_api="argos", ocr_lang="eng", target_lang="BG")
        with mock.patch.object(settings_manager.argos, "libraries_available", return_value=False):
            with self.assertRaises(SettingsValidationError) as ctx:
                self.manager.validate(settings)
            self.assertEqual(ctx.exception.message_key, "argos_not_installed")
        with mock.patch.object(settings_manager.argos, "libraries_available", return_value=True), \
             mock.patch.object(settings_manager.argos, "installed_pairs", return_value=set()):
            with self.assertRaises(SettingsValidationError) as ctx:
                self.manager.validate(settings)
            self.assertEqual(ctx.exception.message_key, "argos_models_needed")
            self.assertEqual(ctx.exception.detail, "en → bg")
        with mock.patch.object(settings_manager.argos, "libraries_available", return_value=True), \
             mock.patch.object(settings_manager.argos, "installed_pairs", return_value={("en", "bg")}):
            self.manager.validate(settings)  # no error

    def test_missing_offline_models_block_only_when_switching_to_offline(self):
        settings = dict(DEFAULT_SETTINGS, translation_api="argos", ocr_lang="eng", target_lang="BG")
        with mock.patch.object(settings_manager.argos, "libraries_available", return_value=True), \
             mock.patch.object(settings_manager.argos, "installed_pairs", return_value=set()):
            # Already offline (the default) - e.g. a font change is saved; the models are offered later.
            self.manager.validate(settings, previous=dict(settings))
            with self.assertRaises(SettingsValidationError) as ctx:
                self.manager.validate(settings, previous=dict(settings, translation_api="google"))
            self.assertEqual(ctx.exception.message_key, "argos_models_needed")

    def test_defaults_are_offline(self):
        self.assertEqual(DEFAULT_SETTINGS["translation_api"], "argos")
        self.assertEqual(DEFAULT_SETTINGS["tts_engine"], "system")

    def test_corrupted_file_falls_back_to_defaults(self):
        self.path.write_text("{ not json", encoding="utf-8")
        self.assertEqual(self.manager.load(), DEFAULT_SETTINGS)

    def test_save_and_load_round_trip_keeps_unicode(self):
        settings = dict(DEFAULT_SETTINGS, audio_lang="bg-BG-KalinaNeural", target_lang="BG")
        self.manager.save(settings)
        self.assertIn("bg-BG-KalinaNeural", self.path.read_text(encoding="utf-8"))
        self.assertEqual(self.manager.load(), settings)

    def test_failed_save_keeps_previous_file(self):
        self.manager.save(dict(DEFAULT_SETTINGS, text_size=33))
        self.manager.save(dict(DEFAULT_SETTINGS, text_size=44, broken=object()))  # cannot be serialized
        self.assertEqual(self.manager.load()["text_size"], 33)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["settings.json"])

    def test_obsolete_settings_are_dropped(self):
        self.path.write_text(json.dumps({"mark_translate_enabled": False}), encoding="utf-8")
        self.assertNotIn("mark_translate_enabled", self.manager.load())

    def test_reset_keeps_api_key_and_window_positions(self):
        current = dict(DEFAULT_SETTINGS, translation_api_key="secret", window_pos=[5, 6],
                       interface_language="bg", text_size=40)
        reset = self.manager.defaults_for_reset(current)
        self.assertEqual(reset["translation_api_key"], "secret")
        self.assertEqual(reset["window_pos"], [5, 6])
        self.assertEqual(reset["interface_language"], DEFAULT_SETTINGS["interface_language"])
        self.assertEqual(reset["text_size"], DEFAULT_SETTINGS["text_size"])

    def test_load_does_not_change_defaults(self):
        self.path.write_text(json.dumps({"text_size": 99}), encoding="utf-8")
        self.manager.load()
        self.assertNotEqual(DEFAULT_SETTINGS["text_size"], 99)


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.manager = SettingsManager()

    def _settings(self, **overrides):
        return {**DEFAULT_SETTINGS, "translation_api": "google", "audio_lang": "", **overrides}

    def test_default_settings_are_valid(self):
        self.manager.validate(self._settings())

    def test_hiding_panel_requires_overlay(self):
        with self.assertRaises(SettingsValidationError) as ctx:
            self.manager.validate(self._settings(hide_overlay_enabled=True, overlay_translation_enabled=False))
        self.assertEqual(ctx.exception.message_key, "overlay_hide_warning")

    def test_same_combo_for_both_hotkeys_is_rejected(self):
        with mock.patch.object(settings_manager, "combo_error", return_value=None):
            with self.assertRaises(SettingsValidationError) as ctx:
                self.manager.validate(self._settings(
                    hotkey_enabled=True, hotkey_combo="<ctrl>+<alt>+t", hotkey_retranslate_combo="<CTRL>+<alt>+t"))
        self.assertEqual(ctx.exception.message_key, "hotkey_duplicate")

    def test_invalid_combo_is_rejected(self):
        with mock.patch.object(settings_manager, "combo_error", side_effect=lambda c: "bad" if c == "oops" else None):
            with self.assertRaises(SettingsValidationError) as ctx:
                self.manager.validate(self._settings(hotkey_enabled=True, hotkey_retranslate_combo="oops"))
        self.assertEqual(ctx.exception.message_key, "hotkey_invalid")

    def test_hotkeys_not_checked_when_disabled(self):
        self.manager.validate(self._settings(hotkey_enabled=False, hotkey_combo="", hotkey_retranslate_combo="x"))

    def test_bad_paid_key_is_reported(self):
        with mock.patch.object(settings_manager, "create_translator") as create:
            create.return_value.translate.side_effect = RuntimeError("403")
            with self.assertRaises(SettingsValidationError) as ctx:
                self.manager.validate(self._settings(translation_api="deepl", translation_api_key="bad"))
        self.assertEqual(ctx.exception.message_key, "invalid_deepl_key")
        # The check must not silently fall through to the Google fallback.
        self.assertFalse(create.call_args.kwargs["enable_fallback"])


if __name__ == "__main__":
    unittest.main()
