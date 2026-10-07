"""
NEW VERSION CHECK (manual, from the "?" menu)

Asks GitHub for the repository's latest published release and
compares it with APP_VERSION. Nothing is downloaded or installed - if there is a new
version, the UI just opens the release page in the browser.

Drafts and pre-releases are not returned by GitHub as
"latest", so they are not offered.

Versions are numbers separated by dots: 3.1, 3.2, 3.0.1 (the GitHub tag is
"v3.1" or "3.1"). They are compared numerically - 3.10 is newer than 3.9, and 3.0.1
newer than 3.0. A tag with something non-numeric (e.g. "v3.1-beta") is not considered a newer
version.
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

STATUS_NEWER = "newer"    # a newer version exists
STATUS_LATEST = "latest"  # you have the latest
STATUS_ERROR = "error"    # cannot be checked (no internet, GitHub not responding...)

_VERSION_RE = re.compile(r"^[vV]?(\d+(?:\.\d+)*)$")


def parse_version(text):
    """ "v3.1" / "3.0.1" -> (3, 1) / (3, 0, 1); anything else -> None."""
    match = _VERSION_RE.match((text or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest, current):
    """Whether version latest is newer than current (both as text like "3.1")."""
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
    """Asks GitHub and returns an UpdateResult. Never raises - on a problem, STATUS_ERROR."""
    try:
        response = requests.get(
            LATEST_RELEASE_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"Overlingo/{current_version}",  # GitHub requires a User-Agent
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            # The repository has no published release yet - so there is no newer one either.
            return UpdateResult(STATUS_LATEST, current_version)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning(f"New version check failed: {e}")
        return UpdateResult(STATUS_ERROR, current_version)

    tag = data.get("tag_name") or ""
    url = data.get("html_url") or RELEASES_PAGE
    latest = tag.lstrip("vV")
    if is_newer(tag, current_version):
        return UpdateResult(STATUS_NEWER, current_version, latest, url)
    return UpdateResult(STATUS_LATEST, current_version, latest, url)


class UpdateCheckThread(QThread):
    """check_for_update() in a background thread - the UI doesn't freeze on a slow connection."""

    # UpdateResult
    result_ready = pyqtSignal(object)

    def run(self):
        self.result_ready.emit(check_for_update())
