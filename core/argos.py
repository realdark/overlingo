"""
OFFLINE TRANSLATION - ARGOS TRANSLATE MODELS

We use the Argos Translate models themselves (free, OPUS/OpenNMT), but not
the argostranslate package - it pulls in heavy dependencies (spaCy, etc.). The model
is a CTranslate2 model + a SentencePiece vocabulary, so these two
small libraries are enough:

    pip install ctranslate2 sentencepiece

Models are per language pair (e.g. en -> bg, ~70 MB) and are downloaded once from
Settings into an "argos-models" folder next to the program. When there is no direct model
(e.g. de -> bg), we translate via English: de -> en -> bg.

No Qt here - the download thread is separate, in core/argos_download.py.
"""

import json
import re
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path

from utils.config import DATA_DIR
from utils.logging_setup import logger

MODELS_DIR = DATA_DIR / "argos-models"
INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
# The model server returns 403 to requests with Python's signature - so we pose as a browser.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
PIVOT = "en"

# Tesseract language (the "OCR language" setting) -> two-letter code as used by Argos.
TESS_TO_ISO = {
    "eng": "en", "bul": "bg", "deu": "de", "fra": "fr", "spa": "es", "ita": "it", "por": "pt",
    "nld": "nl", "pol": "pl", "ces": "cs", "slk": "sk", "slv": "sl", "hrv": "hr", "srp": "sr",
    "ron": "ro", "hun": "hu", "ell": "el", "tur": "tr", "rus": "ru", "ukr": "uk", "swe": "sv",
    "dan": "da", "nor": "nb", "fin": "fi", "est": "et", "lav": "lv", "lit": "lt", "ara": "ar",
    "heb": "he", "hin": "hi", "chi_sim": "zh", "chi_tra": "zt", "jpn": "ja", "kor": "ko",
    "ind": "id", "msa": "ms", "fas": "fa", "aze": "az", "cat": "ca", "eus": "eu", "glg": "gl",
    "gle": "ga", "epo": "eo", "kir": "ky", "swa": "sw", "urd": "ur", "tha": "th", "vie": "vi",
    "ben": "bn", "fil": "tl", "tgl": "tl", "sqi": "sq", "mkd": "mk", "bel": "be", "kat": "ka",
}


class ArgosNotInstalledError(Exception):
    """The ctranslate2/sentencepiece libraries are missing (when run from source without pip install)."""


class ArgosModelMissingError(Exception):
    """No downloaded model for the language pair; str(e) is "en → bg"."""


class ArgosPackageUnavailableError(Exception):
    """Argos has no model for this pair (not even via English); str(e) is "xx → yy"."""


def libraries_available():
    """Whether ctranslate2 and sentencepiece are available (without actually loading them - that is slow)."""
    import importlib.util
    return all(importlib.util.find_spec(name) is not None for name in ("ctranslate2", "sentencepiece"))


def source_language(ocr_lang):
    """'eng+deu' -> 'en': the first recognition language is the source language."""
    first = (ocr_lang or "eng").split("+")[0].strip().lower()
    for suffix in ("_vert", "_latn"):  # "jpn_vert" -> "jpn"
        first = first.removesuffix(suffix)
    return TESS_TO_ISO.get(first, first[:2])


def pair_label(pair):
    return f"{pair[0]} → {pair[1]}"


# ----------------------------------------------------------------------
# Which models are downloaded and which are needed
# ----------------------------------------------------------------------

def installed_pairs(models_dir=None):
    """The downloaded pairs as {("en", "bg"), ...} - from the "en_bg" folders with metadata.json."""
    root = Path(models_dir or MODELS_DIR)
    pairs = set()
    if not root.is_dir():
        return pairs
    for folder in root.iterdir():
        if (folder.is_dir() and "_" in folder.name and not folder.name.endswith(".tmp")
                and (folder / "metadata.json").is_file() and _model_files(folder)):
            source, target = folder.name.split("_", 1)
            pairs.add((source, target))
    return pairs


def find_route(source, target, available):
    """
    The translation path over the available pairs: [("de","bg")] directly, or
    [("de","en"), ("en","bg")] via English. None if there is no path.
    """
    if source == target:
        return []
    if (source, target) in available:
        return [(source, target)]
    if source != PIVOT and target != PIVOT and (source, PIVOT) in available and (PIVOT, target) in available:
        return [(source, PIVOT), (PIVOT, target)]
    return None


def parse_index(index_json):
    """The Argos index (JSON text) -> {("en","bg"): url, ...} (translation packages only)."""
    result = {}
    for package in json.loads(index_json):
        source, target, links = package.get("from_code"), package.get("to_code"), package.get("links") or []
        if source and target and links and package.get("type", "translate") == "translate":
            result[(source, target)] = links[0]
    return result


def pairs_to_download(source, target, index, installed=()):
    """
    Which models must be downloaded to translate source -> target (already
    downloaded ones are skipped). Raises ArgosPackageUnavailableError if
    Argos has no such translation, neither directly nor via English.
    """
    route = find_route(source, target, set(index))
    if route is None:
        raise ArgosPackageUnavailableError(pair_label((source, target)))
    return [pair for pair in route if pair not in installed]


def install_package(archive_path, pair, models_dir=None):
    """
    Extracts a downloaded .argosmodel into models_dir/<from>_<to>. The archive contains
    one folder with metadata.json, model/ (CTranslate2) and sentencepiece.model.
    """
    root = Path(models_dir or MODELS_DIR)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{pair[0]}_{pair[1]}"
    staging = root / f"{pair[0]}_{pair[1]}.tmp"
    with tempfile.TemporaryDirectory(dir=root, ignore_cleanup_errors=True) as tmp:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(tmp)
        metadata = next(Path(tmp).rglob("metadata.json"), None)
        if metadata is None or not _model_files(metadata.parent):
            raise ValueError(f"Unsupported Argos package format: {archive_path}")
        # First a full copy to .tmp, then a single rename - a half-copied
        # model (full disk, antivirus) never looks "downloaded".
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(metadata.parent, staging)
    ArgosTranslator.unload(pair)
    shutil.rmtree(destination, ignore_errors=True)
    staging.replace(destination)
    return destination


def _read_metadata(package_dir):
    try:
        return json.loads((Path(package_dir) / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _model_files(package_dir):
    """(CTranslate2 model folder, SentencePiece file) or None."""
    model_bin = next(Path(package_dir).rglob("model.bin"), None)
    tokenizer = next(Path(package_dir).rglob("sentencepiece.model"), None)
    if model_bin is None or tokenizer is None:
        return None
    return model_bin.parent, tokenizer


# ----------------------------------------------------------------------
# Sentence splitting
# ----------------------------------------------------------------------

# After these words the period does not end a sentence ("No. 1", "Mr. Smith", "e.g. this").
_ABBREVIATIONS = {
    "no", "nr", "mr", "mrs", "ms", "dr", "st", "vs", "etc", "e.g", "i.e", "fig", "p", "pp", "vol",
    "ch", "approx", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "т", "г", "гр", "ул", "бр", "стр", "др", "напр", "вкл", "проф", "д-р", "лв", "млн", "хил", "мин",
}
_SENTENCE_END = re.compile(r"[.!?…]+[\"'”’)\]]*\s+|[。！？]+[」』”’)）]*\s*")
# The model stops translating after ~256 tokens - longer chunks are split.
_MAX_CHUNK_CHARS = 300


def split_sentences(text):
    """
    Splits the text into sentences - the model translates sentence by sentence.
    Does not split after initials ("A.A. Milne") or abbreviations ("No. 1", "e.g.").
    """
    sentences, start = [], 0
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        before = text[start:match.start() + 1].rstrip(".!?…\"'”’)] ")
        last_word = re.split(r"\s+", before)[-1] if before else ""
        if match.group().startswith(".") and _is_abbreviation(last_word):
            continue
        following = text[end:end + 1]
        if following.isalpha() and following.islower():
            continue  # "Wait... what" - the sentence continues
        sentences.append(text[start:end].strip())
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return [chunk for s in sentences if s for chunk in _split_long(s)]


def _split_long(sentence, max_chars=_MAX_CHUNK_CHARS):
    """A very long "sentence" (OCR text without periods) - split into chunks at a comma or space."""
    chunks = []
    while len(sentence) > max_chars:
        cut = max(sentence.rfind(", ", 0, max_chars), sentence.rfind("; ", 0, max_chars))
        if cut <= 0:
            cut = sentence.rfind(" ", 0, max_chars)
        if cut <= 0:
            cut = max_chars - 1
        chunks.append(sentence[:cut + 1].strip())
        sentence = sentence[cut + 1:].strip()
    if sentence:
        chunks.append(sentence)
    return chunks


def _is_abbreviation(word):
    word = word.lstrip("(\"'“‘[")
    if not word:
        return False
    if len(word.replace(".", "")) == 1 and word.replace(".", "").isalpha():
        return True  # initial: "A." in "A.A. Milne", "J. Smith"
    if re.fullmatch(r"(?:[A-Za-zА-Яа-я]\.)+[A-Za-zА-Яа-я]?", word):
        return True  # "A.A", "e.g", "U.S"
    return word.lower() in _ABBREVIATIONS


def detokenize(tokens):
    """SentencePiece marks the start of a word with '▁' - we turn these into spaces."""
    return "".join(tokens).replace("▁", " ").strip()


# ----------------------------------------------------------------------
# Translation
# ----------------------------------------------------------------------

class ArgosTranslator:
    """
    Translates with the already downloaded models. Models are loaded on first use
    and kept in memory (loading takes ~0.1 s, but not on every translation).
    source_lang - two-letter code (see source_language()).
    """

    _cache = {}
    _lock = threading.Lock()

    def __init__(self, source_lang="en", models_dir=None):
        self.source_lang = source_lang
        self.models_dir = Path(models_dir or MODELS_DIR)

    def translate(self, text, target_lang):
        target = (target_lang or "").strip().lower()[:2]
        route = find_route(self.source_lang, target, installed_pairs(self.models_dir))
        if route is None:
            raise ArgosModelMissingError(pair_label((self.source_lang, target)))
        result = text
        for pair in route:
            result = self._translate_pair(result, pair)
        return result

    def _translate_pair(self, text, pair):
        translator, tokenizer, prefix = self._load(pair)
        # Paragraphs (blank line) are preserved; each paragraph is split into sentences.
        paragraphs = []
        for paragraph in re.split(r"\n\s*\n", text):
            lines = " ".join(paragraph.split())  # the lines of one paragraph - joined into one
            sentences = split_sentences(lines)
            if not sentences:
                paragraphs.append("")
                continue
            tokens = [tokenizer.encode(sentence, out_type=str) for sentence in sentences]
            options = {"beam_size": 4, "replace_unknowns": True, "max_decoding_length": 512}
            if prefix:
                options["target_prefix"] = [[prefix]] * len(tokens)
            results = translator.translate_batch(tokens, **options)
            hypotheses = [r.hypotheses[0] for r in results]
            if prefix:
                hypotheses = [h[1:] if h and h[0] == prefix else h for h in hypotheses]
            paragraphs.append(" ".join(detokenize(h) for h in hypotheses))
        return "\n\n".join(paragraphs)

    def _load(self, pair):
        key = (str(self.models_dir), pair)
        with self._lock:
            if key not in self._cache:
                try:
                    import ctranslate2
                    import sentencepiece
                except ImportError as e:
                    raise ArgosNotInstalledError(str(e)) from e
                files = _model_files(self.models_dir / f"{pair[0]}_{pair[1]}")
                if files is None:
                    raise ArgosModelMissingError(pair_label(pair))
                model_dir, tokenizer_file = files
                import os
                logger.info(f"Loading offline translation model {pair_label(pair)} (ctranslate2 {getattr(ctranslate2, '__version__', '?')})")
                translator = ctranslate2.Translator(
                    str(model_dir), device="cpu", inter_threads=1, intra_threads=min(4, os.cpu_count() or 1)
                )
                tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(tokenizer_file))
                # Some Argos packages require a language tag at the start of the translation.
                prefix = _read_metadata(self.models_dir / f"{pair[0]}_{pair[1]}").get("target_prefix") or ""
                self._cache[key] = (translator, tokenizer, prefix)
                logger.info(f"Model {pair_label(pair)} loaded")
            return self._cache[key]

    @classmethod
    def unload(cls, pair=None):
        """Releases the loaded models (e.g. before deleting a pair)."""
        with cls._lock:
            for key in [k for k in cls._cache if pair is None or k[1] == pair]:
                cls._cache.pop(key, None)
