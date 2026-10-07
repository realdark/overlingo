"""
DOWNLOADING OFFLINE TRANSLATION MODELS (ARGOS) FROM THE SETTINGS

Fetches the Argos index, decides which pairs are needed to translate "source
language -> target language" (directly or via English), downloads the missing ones
(~70 MB each) and extracts them into the argos-models folder next to the program.
"""

from utils.imports import QThread, pyqtSignal, requests, tempfile, os, Path
from utils.logging_setup import logger
from core import argos


class ArgosDownloadThread(QThread):
    # pair ("en → bg"), bytes downloaded, total bytes (-1 = unknown)
    progress = pyqtSignal(str, int, int)
    # success, message_key, params - on success params["name"] holds the downloaded pairs
    finished_download = pyqtSignal(bool, str, object)

    # Keep a reference to every started thread while it runs: if the settings
    # dialog is closed during a download, the thread must not be
    # destroyed by the garbage collector ("QThread: Destroyed while running").
    # Also lets a new dialog know that a download is already in progress.
    _active = []

    def __init__(self, source_lang, target_lang):
        """Languages are two-letter ISO codes ("en", "bg")."""
        super().__init__()
        self.source_lang = source_lang
        self.target_lang = target_lang

    @classmethod
    def is_busy(cls):
        """Is there a download still running (from this or a previous dialog)?"""
        cls._active[:] = [t for t in cls._active if t.isRunning()]
        return bool(cls._active)

    def start(self, *args):
        type(self)._active.append(self)
        super().start(*args)

    def run(self):
        try:
            headers = {"User-Agent": argos.USER_AGENT}
            response = requests.get(argos.INDEX_URL, headers=headers, timeout=30)
            response.raise_for_status()
            index = argos.parse_index(response.text)
            installed = argos.installed_pairs()
            needed = argos.pairs_to_download(self.source_lang, self.target_lang, index, installed)
            for pair in needed:
                self._download(pair, index[pair], headers)
            done = argos.find_route(self.source_lang, self.target_lang, argos.installed_pairs()) or []
            self.finished_download.emit(True, "", {"name": ", ".join(argos.pair_label(p) for p in done)})
        except argos.ArgosPackageUnavailableError as e:
            self.finished_download.emit(False, "argos_pair_unavailable", {"pair": str(e)})
        except requests.exceptions.RequestException as e:
            self.finished_download.emit(False, "network_error_detail", {"error": str(e)})
        except Exception as e:
            logger.error(f"Error downloading offline translation model: {e}", exc_info=True)
            self.finished_download.emit(False, "unexpected_error_detail", {"error": str(e)})

    def _download(self, pair, url, headers):
        label = argos.pair_label(pair)
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", -1))
        downloaded = 0
        # Unique name - two copies of the program don't interfere with each other.
        fd, name = tempfile.mkstemp(prefix=f"overlingo-argos-{pair[0]}_{pair[1]}-", suffix=".part")
        archive = Path(name)
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(label, downloaded, total)
            argos.install_package(archive, pair)
        finally:
            archive.unlink(missing_ok=True)
