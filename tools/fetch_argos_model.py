"""
Downloads one offline translation model into a given folder - for the automated
build check in GitHub Actions (overlingo --self-test --argos-models ...).
The model lives outside the app folder so it doesn't end up in the archive.

    python tools/fetch_argos_model.py DIR [from] [to]      (default: en de)
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# The Windows console (and GitHub Actions logs) is often not UTF-8 -
# without this, non-ASCII text fails with UnicodeEncodeError.
if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

import requests  # noqa: E402

from core import argos  # noqa: E402


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    models_dir = Path(sys.argv[1])
    source = sys.argv[2] if len(sys.argv) > 2 else "en"
    target = sys.argv[3] if len(sys.argv) > 3 else "de"
    headers = {"User-Agent": argos.USER_AGENT}

    response = requests.get(argos.INDEX_URL, headers=headers, timeout=60)
    response.raise_for_status()
    index = argos.parse_index(response.text)
    for pair in argos.pairs_to_download(source, target, index, argos.installed_pairs(models_dir)):
        print(f"Downloading {argos.pair_label(pair)}: {index[pair]}", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "model.argosmodel"
            with requests.get(index[pair], headers=headers, stream=True, timeout=120) as download:
                download.raise_for_status()
                with open(archive, "wb") as out:
                    for chunk in download.iter_content(chunk_size=1 << 20):
                        out.write(chunk)
            argos.install_package(archive, pair, models_dir)
    print("Installed:", ", ".join(argos.pair_label(p) for p in sorted(argos.installed_pairs(models_dir))))


if __name__ == "__main__":
    main()
