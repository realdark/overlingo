"""
DOWNLOADING TESSERACT LANGUAGE DATA (.traineddata) FROM WITHIN THE APP

Downloads directly from the official Google/tesseract-ocr GitHub repository
(tessdata_fast - a speed/accuracy balance, which is also what most Linux
distributions use by default), so the user doesn't have to find and
download .traineddata files manually in a browser.
"""

from utils.imports import QThread, pyqtSignal, requests, tempfile, shutil, Path, sys
from utils.logging_setup import logger

# We try both branches of the repository - it's not certain which one is
# currently active, and a miss is cheap (one quick 404) compared to the whole
# button breaking if the branch gets renamed upstream.
TESSDATA_FAST_BRANCHES = ("main", "master")
TESSDATA_FAST_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{branch}/{lang}.traineddata"
)


class TessdataDownloadThread(QThread):
    # bytes_downloaded, total_bytes (total is -1 if the server doesn't send it)
    progress = pyqtSignal(int, int)
    # success, message_key, params - on success the key is empty and params
    # contains {"name": language code}; on failure the UI shows tr(key).format(**params)
    finished_download = pyqtSignal(bool, str, object)

    def __init__(self, lang_code, dest_path):
        """lang_code - already cleaned by the dialog (lowercase, no spaces, not empty)."""
        super().__init__()
        self.lang_code = lang_code
        self.dest_path = dest_path

    def run(self):
        response = None
        try:
            for branch in TESSDATA_FAST_BRANCHES:
                url = TESSDATA_FAST_URL_TEMPLATE.format(branch=branch, lang=self.lang_code)
                response = requests.get(url, stream=True, timeout=30)
                if response.status_code == 200:
                    break
                if response.status_code != 404:
                    response.raise_for_status()
            else:
                self.finished_download.emit(False, "tessdata_err_not_found", {"lang": self.lang_code})
                return

            total = int(response.headers.get("Content-Length", -1))
            downloaded = 0

            # Download to a temp folder first (always writable), NOT directly
            # to dest_path - system folders such as
            # "C:\Program Files\Tesseract-OCR\tessdata" require
            # administrator rights to write on Windows; if downloading
            # directly there failed with PermissionError midway, we would
            # also lose the bytes already downloaded. This way the download
            # always succeeds, and only the last step (the move) may need rights.
            tmp_path = Path(tempfile.gettempdir()) / f"{self.lang_code}.traineddata.part"

            with open(tmp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    self.progress.emit(downloaded, total)

            try:
                self.dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_path), str(self.dest_path))
                self.finished_download.emit(True, "", {"name": self.lang_code})
            except PermissionError:
                # The file was downloaded successfully (to tmp_path) - only
                # moving it into the system folder is blocked. Give a clear,
                # specific, platform-specific instruction instead of the raw
                # Python traceback, and keep the already downloaded bytes.
                key = "tessdata_err_permission_windows" if sys.platform == "win32" else "tessdata_err_permission_unix"
                self.finished_download.emit(
                    False, key, {"folder": str(self.dest_path.parent), "file": str(tmp_path)}
                )

        except requests.exceptions.RequestException as e:
            self.finished_download.emit(False, "network_error_detail", {"error": str(e)})
        except Exception as e:
            logger.error(f"Error downloading tessdata '{self.lang_code}': {e}", exc_info=True)
            self.finished_download.emit(False, "unexpected_error_detail", {"error": str(e)})
