"""
ПРОВЕРКА ЗА НОВА ВЕРСИЯ (ръчна, от менюто "?")

Пита GitHub кой е последният публикуван release на хранилището и го
сравнява с APP_VERSION. Нищо не се сваля и не се инсталира - при нова
версия UI-ят само отваря страницата на release-а в браузъра.

Чернови и предварителни версии (pre-release) не се връщат от GitHub като
"последна", така че не се предлагат.

Версиите са числа, разделени с точки: 3.1, 3.2, 3.0.1 (tag-ът в GitHub е
"v3.1" или "3.1"). Сравняват се числово - 3.10 е по-нова от 3.9, а 3.0.1
от 3.0. Tag с нещо нечислово (напр. "v3.1-beta") не се смята за по-нова
версия.
"""

import re
from dataclasses import dataclass

from utils.imports import QThread, pyqtSignal, requests
from utils.logging_setup import logger
from utils.version import APP_VERSION

GITHUB_REPO = "realdark/overlingo"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
TIMEOUT_SECONDS = 10

STATUS_NEWER = "newer"    # има по-нова версия
STATUS_LATEST = "latest"  # имаш последната
STATUS_ERROR = "error"    # не може да се провери (няма интернет, GitHub не отговаря...)

_VERSION_RE = re.compile(r"^[vV]?(\d+(?:\.\d+)*)$")


def parse_version(text):
    """ "v3.1" / "3.0.1" -> (3, 1) / (3, 0, 1); нещо друго -> None."""
    match = _VERSION_RE.match((text or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest, current):
    """Дали версията latest е по-нова от current (и двете - текст като "3.1")."""
    new, old = parse_version(latest), parse_version(current)
    if new is None or old is None:
        return False
    length = max(len(new), len(old))  # 3.0 == 3.0.0
    return new + (0,) * (length - len(new)) > old + (0,) * (length - len(old))


@dataclass(frozen=True)
class UpdateResult:
    status: str
    current_version: str
    latest_version: str = ""
    url: str = RELEASES_PAGE


def check_for_update(current_version=APP_VERSION):
    """Пита GitHub и връща UpdateResult. Не хвърля грешки - при проблем STATUS_ERROR."""
    try:
        response = requests.get(
            LATEST_RELEASE_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"Overlingo/{current_version}",  # GitHub изисква User-Agent
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            # Хранилището още няма публикуван release - значи няма и по-нов.
            return UpdateResult(STATUS_LATEST, current_version)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning(f"Проверката за нова версия не успя: {e}")
        return UpdateResult(STATUS_ERROR, current_version)

    tag = data.get("tag_name") or ""
    url = data.get("html_url") or RELEASES_PAGE
    latest = tag.lstrip("vV")
    if is_newer(tag, current_version):
        return UpdateResult(STATUS_NEWER, current_version, latest, url)
    return UpdateResult(STATUS_LATEST, current_version, latest, url)


class UpdateCheckThread(QThread):
    """check_for_update() във фонова нишка - при бавна връзка интерфейсът не замръзва."""

    # UpdateResult
    result_ready = pyqtSignal(object)

    def run(self):
        self.result_ready.emit(check_for_update())
