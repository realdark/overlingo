[Български](README_bg.md)

# Overlingo

A desktop app for Windows, Linux and macOS: select any area of the screen
and it translates the text inside it — shown as an overlay on top of the
original, with caching, auto refresh and text-to-speech for the
translation.

## Features

- Select and translate text from any part of the screen (OCR via Tesseract)
- Translation services: **offline translation** on the computer itself -
  the default (the free Argos Translate models, run with CTranslate2 - no API
  key and no separate program needed; the first translation between two
  languages offers to download them, ~70 MB per language pair, and without a
  direct model the translation goes through English), **Google Translate**,
  **DeepL** and **Microsoft Translator**
- Automatic fallback to Google if the main paid service fails, and to
  offline translation if there is no connection and the models are
  downloaded
- Retry with exponential backoff on temporary errors (e.g. 429 Too Many
  Requests) and a quick internet connection check before calling the cloud
  APIs
- Choose and download OCR languages right from the app (Settings →
  "Download language", fetches from `tessdata_fast`)
- Reading translations aloud **offline with the computer's own voices** (the
  default - Qt TextToSpeech: SAPI on Windows, the system voices on macOS,
  speech-dispatcher on Linux) or online with the natural **Microsoft Edge**
  voices (edge-tts; picked automatically by the translation language, or from
  the full list). Without a system voice for the language, the online voice
  reads instead when there is internet
- Transparent overlay for the results, positioned over the original text,
  with the same font size (measured in a background thread - see
  `core/font_size_detector.py`)
- Translation caching (no paying again for text that has already been seen)
- Speech speed (0.5x-2x, like YouTube)
- "Translate again" - translate the last selected area again without
  selecting it anew
- A window for translating typed/pasted text (with a button / Ctrl+Enter,
  or automatically a second after the last keystroke - via a checkbox)
- Translation history for the current session (not saved to disk), with
  statistics on how many translations were made and how many came from the
  cache
- Two global hotkeys - "Select & Translate" and "Translate again"
  (Windows and Linux under X11; not under Wayland/macOS - see
  `core/hotkey_manager.py` for why) and minimizing to the taskbar
- Cancel a selection with Esc or the right mouse button
- Single instance only - launching it a second time brings up the already
  open window (`core/single_instance.py`)
- Settings organized in tabs (Interface/Translation/Audio/Hotkey), with
  "Restore defaults"; dark theme
- A "?" menu with Help, About and a manual check for updates (GitHub
  Releases - only on request, nothing is downloaded automatically)
- Localized interface (Bulgarian, English) - all texts live only in
  `assets/locales/*.json`

## Installation

### 1. Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Tesseract OCR (required, installed system-wide on all three platforms)

- **Windows** — `winget install --id UB-Mannheim.TesseractOCR -e` (built
  into Windows 10/11, always fetches the latest version), or manually from
  https://github.com/UB-Mannheim/tesseract/wiki
- **macOS** — `brew install tesseract`
- **Linux** — `sudo apt install tesseract-ocr` (or the `dnf`/`pacman` equivalent)

Overlingo **does not bundle** Tesseract - it relies entirely on a
system-wide installation on all three platforms (see the comment at
`TESSERACT_PATHS` in `utils/config.py` for why we deliberately dropped
AppImage/bundled copies: the AppImage build hard-codes its own tessdata
path, which cannot be extended through the "Download language" button).
If Tesseract is missing, Overlingo shows a dialog with exact instructions
on startup.

Additional OCR languages besides English:
```bash
sudo apt install tesseract-ocr-bul   # or the language you want
```
or use the "Download language" button in Settings (it writes directly to
the system tessdata folder, which is detected automatically).

### 3. Offline translation and voices

Offline translation is the default. The `ctranslate2` and `sentencepiece`
libraries come with `requirements.txt`. The models themselves (one per
language pair) are offered for download on the first translation between two
languages, or can be downloaded beforehand from Settings → "Translation" tab →
"Download offline languages"; they go into an `argos-models` folder next to
the program.

Reading aloud uses the voices installed in the operating system by default
(no extra package - Qt TextToSpeech is part of PyQt5). On Linux it needs
speech-dispatcher (e.g. `sudo apt install speech-dispatcher espeak-ng`).
Missing languages can be added in the system speech settings; otherwise the
online Microsoft Edge voice is used when there is internet. When moving to a new version, copy the
`argos-models` folder into the new one so you don't have to download the
models again.

### 4. Running

```bash
python3 main.py
```

### 5. Tests

```bash
python3 -m unittest discover -s tests -t .
```

They test the logic without the UI (translators, cache, retry, history,
settings, hotkey formats, finding Tesseract) and the texts: both languages
must have the same keys and fields, every key used in the code must exist,
and conversely - there must be no unused ones. If a heavy library (PyQt5,
pygame...) is missing, the tests replace it with an empty stub
(`tests/_stubs.py`), so they run without it as well.

## Project structure

```
main.py                    Entry point (+ protection against a second instance)
core/                       Logic without UI (testable)
  translations.py           Translators (Google/DeepL/Microsoft/offline) + fallback, cache, threads
  translation_controller.py Orchestration: screenshot → OCR → translation (+ timeout)
  history.py                Translation history (session only)
  capture.py                Screenshot + OpenCV preprocessing
  settings_manager.py       Loading/saving/validating settings
  tesseract_setup.py        Finding the system Tesseract
  retry.py                  Retry with exponential backoff
  network.py                Internet connection check
  audio_handler.py          Online text-to-speech (edge-tts) in a background thread
  system_tts.py             Offline text-to-speech with the computer's voices (Qt TextToSpeech)
  audio_playback.py         Play/stop for all play buttons, engine choice and online fallback
  localization.py           Loading the texts from assets/locales
  argos.py                  Offline translation (the Argos Translate models)
  argos_download.py         Downloading the offline translation models
  selftest.py               Automated build check (overlingo --self-test)
  tessdata_download.py      Downloading Tesseract language data
  hotkey_manager.py         Global hotkeys (Windows, Linux/X11)
  single_instance.py        Only one open instance
  update_check.py           Manual check for updates (GitHub Releases)
  fullscreen_detector.py    Showing above full-screen apps (Linux/X11)
  font_size_detector.py     Font size of the original text
ui/                          PyQt5 interface
  main_window.py             Main window and button bar
  settings_dialog.py         Settings dialog
  history_window.py          History window
  text_translate_window.py   Text translation window
  dialogs.py                 Help, About, missing Tesseract
  components.py              Overlay, area selection, shared buttons
utils/
  version.py                 APP_VERSION - the single place for the version
  config.py                  Paths, default settings
  logging_setup.py           Logging (console + app.log), crash recording (crash.log)
assets/
  locales/                   bg.json, en.json - all interface texts
  theme.qss                  Dark theme
  images/, icons/            Icons
tests/                       Tests (unittest)
tools/fix_qt_runtime.py      Windows: replaces PyQt5's old msvcp140.dll (run by build.bat)
tools/fetch_argos_model.py   Downloads an offline translation model (for the GitHub Actions check)
.github/workflows/build.yml  Automatic build + check for Windows/Linux/macOS
build_macos.sh               macOS build (Overlingo.app)
install.sh                   Linux: double-click launcher and applications menu entry
README_DIST_*.txt            End-user README, included in the build
```

## Build (standalone .exe/binary)

```
build.bat        Windows (PyInstaller, onedir)
build.sh         Linux (PyInstaller, onedir)
build_macos.sh   macOS (PyInstaller, Overlingo.app; run on a Mac)
```

Requires `pip install pyinstaller` beforehand and an activated virtual
environment (`venv`) with the dependencies installed. The scripts can be
run from any folder - they change into the project folder themselves. The
result is in `dist/overlingo/`, together with a ready archive in `dist/`
(`Overlingo-<version>-win64.zip` / `Overlingo-<version>-linux-<arch>.tar.gz`).
The version is changed only in `utils/version.py` - the About window and
the archive names read it from there.
`settings.json` is deliberately NOT copied into the build — the app
generates a clean file on first launch (see `core/settings_manager.py`).

On macOS, `assets` lives inside the `.app` bundle, while settings, logs and
models go to `~/Library/Application Support/Overlingo` (the bundle is never
modified). See `get_resource_dir()` / `get_data_dir()` in `utils/config.py`.

### Automatic builds (GitHub Actions)

`.github/workflows/build.yml` builds for Windows, Linux, macOS (Apple
Silicon) and macOS (Intel) on GitHub's machines - free for a public
repository. For each system: tests → build → download a small offline
translation model → `overlingo --self-test` on the finished build
(`core/selftest.py`: libraries, Qt, Tesseract, text recognition, offline
translation, the main window).

- Test build: GitHub → Actions → **Build** → **Run workflow**. The archives
  are under "Artifacts" on the run's page (kept for 14 days).
- Published release: the archives are attached to it automatically. The
  tag must be `v` + `APP_VERSION`, otherwise the build stops (the in-app
  update check relies on this).

The check can also be run manually on a build:
`overlingo --self-test [--argos-models FOLDER] [--require-argos]`.

## Releasing a new version

1. Change the number in `utils/version.py` (format `3.1`, `3.2`, `3.0.1` - no
   leading zeros; compared numerically).
2. Commit and push.
3. GitHub → Releases → new release with tag **`v` + the same number** (e.g.
   `v3.3`) → Publish. GitHub Actions builds for Windows, Linux and macOS by
   itself and attaches the archives to the release (about 15-20 minutes).
   Building manually with `build.bat` / `build.sh` is still possible.

"Check for updates" in the app reads the latest published release and
compares its tag with `utils/version.py` - if the two diverge, the check
will be wrong. Drafts and pre-releases are not offered to users.

## Git

`.gitignore` keeps `settings.json` (may contain an API key), `app.log`,
`crash.log`, `argos-models/`, `build/`, `dist/` and `venv/` out of the repository. `.gitattributes` enforces
line endings: `.sh` always with Linux (LF), `.bat` with Windows
(CRLF) - otherwise the scripts break if they pass through the other
system. When pushing from Windows, `build.sh` and `install.sh` lose the
"executable" flag: `git update-index --chmod=+x build.sh build_macos.sh install.sh` fixes it once.

## Logs

All messages (INFO/WARNING/ERROR) go to the console and to `app.log`,
next to `settings.json`, with rotation (max. 1MB, up to 3 archives).
Uncaught exceptions are recorded there too, instead of the program closing
without a trace.

If the program crashes inside a C/C++ library (ctranslate2, OpenCV...),
Python cannot record the error - in that case `crash.log` (next to the
program) shows where the crash happened (`faulthandler`).

On Windows, `main.py` loads `ctranslate2` before PyQt5: PyQt5 ships an older
`msvcp140.dll`, and if it gets loaded first, offline translation crashes
the program.
Before PyInstaller, `build.bat` runs `tools/fix_qt_runtime.py`: it renames
the old `msvcp140.dll` (and related files) in `PyQt5\Qt5\bin` to
`*.old` if `System32` has a newer one - otherwise PyInstaller fails with
"Isolated subprocess crashed while importing package 'sentencepiece'",
and the build would contain the old file. Manually: `python tools\fix_qt_runtime.py`;
to revert, remove `.old` from the file names.

## License

GPL-3.0 — see `LICENSE`. Required by the PyQt5 license (GPL, or a paid
commercial license from Riverbank Computing); this project does not use
the commercial one.

## Libraries/services used

PyQt5, Tesseract OCR, OpenCV, mss, pytesseract, edge-tts, pygame,
requests, Google Translate, DeepL API, Microsoft Azure Translator,
CTranslate2, SentencePiece, the Argos Translate models (OPUS/OpenNMT) —
each with its own license/terms of use.
