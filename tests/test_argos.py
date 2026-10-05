import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from core import argos


class SplitSentencesTest(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(argos.split_sentences("One. Two! Three?"), ["One.", "Two!", "Three?"])

    def test_initials_are_not_sentence_ends(self):
        text = "Characters from A.A. Milne's timeless stories. Beloved by all."
        self.assertEqual(argos.split_sentences(text),
                         ["Characters from A.A. Milne's timeless stories.", "Beloved by all."])

    def test_abbreviations(self):
        self.assertEqual(argos.split_sentences("Start with the Case No. 1. Do not start a new one!"),
                         ["Start with the Case No. 1.", "Do not start a new one!"])
        self.assertEqual(argos.split_sentences("Use dice, e.g. the white ones. Then roll."),
                         ["Use dice, e.g. the white ones.", "Then roll."])
        self.assertEqual(argos.split_sentences("Mr. Smith arrived. He sat."), ["Mr. Smith arrived.", "He sat."])

    def test_quotes_and_brackets_after_end(self):
        self.assertEqual(argos.split_sentences('He said "Go." Then left.'), ['He said "Go."', "Then left."])

    def test_no_terminal_punctuation(self):
        self.assertEqual(argos.split_sentences("GAME OVERVIEW"), ["GAME OVERVIEW"])
        self.assertEqual(argos.split_sentences("   "), [])

    def test_cjk_sentence_ends(self):
        self.assertEqual(argos.split_sentences("你好。我很好！谢谢"), ["你好。", "我很好！", "谢谢"])

    def test_no_split_before_lowercase(self):
        self.assertEqual(argos.split_sentences("Costs 5 lv. per item. Next one."),
                         ["Costs 5 lv. per item.", "Next one."])

    def test_long_sentence_is_cut_into_pieces(self):
        text = ", ".join(["word number"] * 60) + "."
        pieces = argos.split_sentences(text)
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(p) <= 300 for p in pieces))
        self.assertEqual(" ".join(pieces).replace(" ", ""), text.replace(" ", ""))  # нищо не се губи


class HelpersTest(unittest.TestCase):
    def test_detokenize(self):
        self.assertEqual(argos.detokenize(["▁В", "▁това", "▁приключение", ","]), "В това приключение,")

    def test_source_language_from_ocr_setting(self):
        self.assertEqual(argos.source_language("eng"), "en")
        self.assertEqual(argos.source_language("deu+eng"), "de")
        self.assertEqual(argos.source_language("chi_sim"), "zh")
        self.assertEqual(argos.source_language(""), "en")

    def test_route_direct_pivot_or_none(self):
        available = {("en", "bg"), ("de", "en"), ("bg", "en")}
        self.assertEqual(argos.find_route("en", "bg", available), [("en", "bg")])
        self.assertEqual(argos.find_route("de", "bg", available), [("de", "en"), ("en", "bg")])
        self.assertIsNone(argos.find_route("fr", "bg", available))
        self.assertEqual(argos.find_route("bg", "bg", available), [])

    def test_parse_index_and_pairs_to_download(self):
        index = argos.parse_index(json.dumps([
            {"code": "translate-en_bg", "from_code": "en", "to_code": "bg", "links": ["https://x/en_bg"]},
            {"code": "translate-de_en", "from_code": "de", "to_code": "en", "links": ["https://x/de_en"]},
            {"code": "sbd", "from_code": "en", "to_code": "en", "type": "sbd", "links": ["https://x/sbd"]},
        ]))
        self.assertEqual(index, {("en", "bg"): "https://x/en_bg", ("de", "en"): "https://x/de_en"})
        self.assertEqual(argos.pairs_to_download("de", "bg", index), [("de", "en"), ("en", "bg")])
        self.assertEqual(argos.pairs_to_download("de", "bg", index, installed={("en", "bg")}), [("de", "en")])
        with self.assertRaises(argos.ArgosPackageUnavailableError):
            argos.pairs_to_download("fr", "bg", index)


def _fake_package(path, top_folder="translate-en_bg-1_9"):
    """Архив като истинския .argosmodel: папка с metadata.json, model/model.bin и sentencepiece.model."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{top_folder}/metadata.json", json.dumps({"from_code": "en", "to_code": "bg"}))
        archive.writestr(f"{top_folder}/model/model.bin", b"\0")
        archive.writestr(f"{top_folder}/sentencepiece.model", b"\0")


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.models = Path(self.tmp.name) / "models"

    def test_install_and_list(self):
        archive = Path(self.tmp.name) / "en_bg.argosmodel"
        _fake_package(archive)
        argos.install_package(archive, ("en", "bg"), self.models)
        self.assertEqual(argos.installed_pairs(self.models), {("en", "bg")})
        self.assertTrue((self.models / "en_bg" / "model" / "model.bin").is_file())

    def test_package_without_top_folder(self):
        archive = Path(self.tmp.name) / "flat.argosmodel"
        _fake_package(archive, top_folder=".")
        argos.install_package(archive, ("en", "bg"), self.models)
        self.assertEqual(argos.installed_pairs(self.models), {("en", "bg")})

    def test_unsupported_package_is_rejected(self):
        archive = Path(self.tmp.name) / "bad.argosmodel"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("pkg/metadata.json", "{}")
        with self.assertRaises(ValueError):
            argos.install_package(archive, ("en", "bg"), self.models)
        self.assertEqual(argos.installed_pairs(self.models), set())

    def test_installed_pairs_ignores_unfinished_folders(self):
        archive = Path(self.tmp.name) / "en_bg.argosmodel"
        _fake_package(archive)
        argos.install_package(archive, ("en", "bg"), self.models)
        (self.models / "en_de.tmp").mkdir()  # прекъснато инсталиране
        (self.models / "en_de.tmp" / "metadata.json").write_text("{}")
        (self.models / "en_fr").mkdir()  # само metadata.json, без модел
        (self.models / "en_fr" / "metadata.json").write_text("{}")
        self.assertEqual(argos.installed_pairs(self.models), {("en", "bg")})


class _FakeResult:
    def __init__(self, tokens):
        self.hypotheses = [tokens]


def _fake_libraries(log):
    """Фалшиви ctranslate2/sentencepiece: "превеждат" като добавят [двойка] към всяко изречение."""
    ct2 = types.ModuleType("ctranslate2")
    sp = types.ModuleType("sentencepiece")

    class Translator:
        def __init__(self, model_dir, **kwargs):
            self.pair = Path(model_dir).parent.name

        def translate_batch(self, batch, target_prefix=None, **kwargs):
            log.append((self.pair, len(batch)))
            prefixes = target_prefix or [[]] * len(batch)
            return [_FakeResult(prefix + [f"▁[{self.pair}]"] + tokens) for prefix, tokens in zip(prefixes, batch)]

    class SentencePieceProcessor:
        def __init__(self, model_file):
            pass

        def encode(self, text, out_type=str):
            return ["▁" + word for word in text.split()]

    ct2.Translator = Translator
    sp.SentencePieceProcessor = SentencePieceProcessor
    return mock.patch.dict(sys.modules, {"ctranslate2": ct2, "sentencepiece": sp})


class ArgosTranslatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.models = Path(self.tmp.name)
        argos.ArgosTranslator.unload()
        self.addCleanup(argos.ArgosTranslator.unload)

    def _install(self, *pairs, metadata=None):
        for source, target in pairs:
            folder = self.models / f"{source}_{target}"
            (folder / "model").mkdir(parents=True)
            (folder / "model" / "model.bin").write_bytes(b"\0")
            (folder / "sentencepiece.model").write_bytes(b"\0")
            (folder / "metadata.json").write_text(json.dumps(metadata or {}))

    def test_direct_translation_keeps_paragraphs(self):
        self._install(("en", "bg"))
        log = []
        with _fake_libraries(log):
            result = argos.ArgosTranslator("en", self.models).translate("Hello there.\nGood.\n\nBye.", "BG")
        self.assertEqual(result, "[en_bg] Hello there. [en_bg] Good.\n\n[en_bg] Bye.")
        self.assertEqual(log, [("en_bg", 2), ("en_bg", 1)])  # изреченията на абзац - в една заявка

    def test_pivot_through_english(self):
        self._install(("de", "en"), ("en", "bg"))
        log = []
        with _fake_libraries(log):
            result = argos.ArgosTranslator("de", self.models).translate("Hallo.", "bg")
        self.assertEqual(result, "[en_bg] [de_en] Hallo.")

    def test_target_prefix_is_passed_and_removed(self):
        self._install(("en", "zh"), metadata={"target_prefix": "__zh__"})
        log = []
        with _fake_libraries(log):
            result = argos.ArgosTranslator("en", self.models).translate("Hello.", "ZH")
        self.assertEqual(result, "[en_zh] Hello.")  # без "__zh__" в резултата

    def test_missing_model(self):
        with self.assertRaises(argos.ArgosModelMissingError) as ctx:
            argos.ArgosTranslator("en", self.models).translate("Hello.", "BG")
        self.assertEqual(str(ctx.exception), "en → bg")

    def test_same_language_returns_text(self):
        self.assertEqual(argos.ArgosTranslator("en", self.models).translate("Hello.", "EN"), "Hello.")

    def test_missing_libraries(self):
        self._install(("en", "bg"))
        with mock.patch.dict(sys.modules, {"ctranslate2": None}):
            with self.assertRaises(argos.ArgosNotInstalledError):
                argos.ArgosTranslator("en", self.models).translate("Hello.", "BG")


if __name__ == "__main__":
    unittest.main()
