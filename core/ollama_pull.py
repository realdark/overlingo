"""
ИЗТЕГЛЯНЕ НА OLLAMA МОДЕЛ ОТ ПРИЛОЖЕНИЕТО

Праща /api/pull към локалния Ollama сървър и следи прогреса (streaming
NDJSON отговор), за да не се налага потребителят да отваря терминал и
да пише `ollama pull <модел>` ръчно - единственото, което остава извън
приложението, е самата инсталация на Ollama (както е и с Tesseract).
"""

from utils.imports import QThread, pyqtSignal, requests, json
from utils.logging_setup import logger


class OllamaPullThread(QThread):
    # status text (напр. "pulling manifest", "downloading", "verifying sha256 digest"), percent (0-100, -1 = неизвестен)
    progress = pyqtSignal(str, int)
    # success, message_key, params - при успех ключът е празен, а params
    # съдържа {"name": модел}; при провал UI-ят показва tr(ключ).format(**params)
    finished_pull = pyqtSignal(bool, str, object)

    def __init__(self, model, base_url):
        super().__init__()
        self.model = model
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")

    def run(self):
        try:
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": self.model, "stream": True},
                stream=True,
                timeout=None,  # моделите са по няколко GB - няма разумен фиксиран timeout
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue

                if data.get("error"):
                    self.finished_pull.emit(False, "ollama_pull_error", {"error": data["error"]})
                    return

                status = data.get("status", "")
                completed = data.get("completed")
                total = data.get("total")

                percent = -1
                if completed and total:
                    percent = int(completed * 100 / total)

                self.progress.emit(status, percent)

            self.finished_pull.emit(True, "", {"name": self.model})

        except requests.exceptions.ConnectionError:
            self.finished_pull.emit(False, "ollama_unavailable_at", {"url": self.base_url})
        except Exception as e:
            logger.error(f"Грешка при изтегляне на Ollama модел: {e}", exc_info=True)
            self.finished_pull.emit(False, "unexpected_error_detail", {"error": str(e)})
