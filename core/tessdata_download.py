"""
ИЗТЕГЛЯНЕ НА TESSERACT ЕЗИКОВИ ДАННИ (.traineddata) ОТ ПРИЛОЖЕНИЕТО

Тегли директно от официалното GitHub хранилище на Google/tesseract-ocr
(tessdata_fast - баланс скорост/точност, това ползват и повечето Linux
дистрибуции по подразбиране), за да не се налага потребителят да търси
и сваля .traineddata файлове ръчно от браузъра.
"""

from utils.imports import QThread, pyqtSignal, requests, tempfile, shutil, Path, sys
from utils.logging_setup import logger

# Пробваме и двата branch-а на хранилището - не е сигурно кой е активният
# в момента, а провалът е евтин (един бърз 404) в сравнение с това целият
# бутон да спре да работи при преименуване на branch-а нагоре по веригата.
TESSDATA_FAST_BRANCHES = ("main", "master")
TESSDATA_FAST_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{branch}/{lang}.traineddata"
)


class TessdataDownloadThread(QThread):
    # bytes_downloaded, total_bytes (total е -1, ако сървърът не го подаде)
    progress = pyqtSignal(int, int)
    # success, message_key, params - при успех ключът е празен, а params
    # съдържа {"name": езиков код}; при провал UI-ят показва tr(ключ).format(**params)
    finished_download = pyqtSignal(bool, str, object)

    def __init__(self, lang_code, dest_path):
        super().__init__()
        self.lang_code = lang_code.strip().lower()
        self.dest_path = dest_path

    def run(self):
        if not self.lang_code:
            self.finished_download.emit(False, "tessdata_err_no_code", {})
            return

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

            # Сваляме първо във временна папка (винаги достъпна за писане),
            # НЕ директно в dest_path - системни папки като
            # "C:\Program Files\Tesseract-OCR\tessdata" изискват
            # администраторски права за запис на Windows; ако свалянето
            # директно там гръмне с PermissionError по средата, губим и
            # изтеглените вече байтове. Така свалянето винаги успява,
            # само последната стъпка (местенето) може да поиска права.
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
                # Файлът е свален успешно (в tmp_path) - само местенето до
                # системната папка е блокирано. Даваме ясна, конкретна,
                # platform-специфична инструкция вместо суровия Python
                # traceback, и не губим вече свалените байтове.
                key = "tessdata_err_permission_windows" if sys.platform == "win32" else "tessdata_err_permission_unix"
                self.finished_download.emit(
                    False, key, {"folder": str(self.dest_path.parent), "file": str(tmp_path)}
                )

        except requests.exceptions.RequestException as e:
            self.finished_download.emit(False, "network_error_detail", {"error": str(e)})
        except Exception as e:
            logger.error(f"Грешка при изтегляне на tessdata '{self.lang_code}': {e}", exc_info=True)
            self.finished_download.emit(False, "unexpected_error_detail", {"error": str(e)})
