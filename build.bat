@echo off
REM UTF-8 console - otherwise non-ASCII output is garbled
chcp 65001 >nul
echo === Build Overlingo (onedir, Windows) ===

REM Run from the script's directory, regardless of where it was launched from
REM (%~dp0 = build.bat's directory; /d also switches drive if different).
cd /d "%~dp0"

REM Stop on error
setlocal enabledelayedexpansion

REM The version is read from utils\version.py - the only place it is changed.
REM Without Python (the "python" command isn't always on PATH on Windows): the line is
REM APP_VERSION = "3.0" - take the part after "=" and strip spaces and quotes.
set VERSION=
for /f "tokens=2 delims==" %%v in ('findstr /b /c:"APP_VERSION" utils\version.py') do set VERSION=%%v
if defined VERSION set VERSION=%VERSION: =%
if defined VERSION set VERSION=%VERSION:"=%
if "%VERSION%"=="" (
    echo Cannot read APP_VERSION from utils\version.py
    exit /b 1
)

REM Clean up old builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist overlingo.spec del /q overlingo.spec

REM PyQt5 ships an old msvcp140.dll that crashes ctranslate2/sentencepiece
REM (and PyInstaller during the build) - tools\fix_qt_runtime.py replaces it with the system one.
REM Use the Python that owns pyinstaller (the "python" command may be just
REM a Microsoft Store shortcut): ...\Scripts\pyinstaller.exe ->
REM ...\Scripts\python.exe (venv) or ...\python.exe (regular install).
set PY=
for /f "delims=" %%p in ('where pyinstaller 2^>nul') do (
    if not defined PY if exist "%%~dpppython.exe" set "PY=%%~dpppython.exe"
    if not defined PY if exist "%%~dpp..\python.exe" set "PY=%%~dpp..\python.exe"
)
if not defined PY (
    where py >nul 2>nul && set PY=py
)
if defined PY (
    "%PY%" tools\fix_qt_runtime.py
    if errorlevel 1 (
        echo.
        echo === BUILD FAILED ===
        exit /b 1
    )
) else (
    echo Python not found - skipping tools\fix_qt_runtime.py
)

set ICON=assets\icons\app_icon.ico

pyinstaller --onedir --noconsole ^
  --icon="%ICON%" ^
  --name "overlingo" ^
  --hidden-import=mss ^
  --hidden-import=mss.tools ^
  --hidden-import=edge_tts ^
  --hidden-import=pygame ^
  --hidden-import=deepl ^
  --hidden-import=pytesseract ^
  --hidden-import=PyQt5.QtCore ^
  --hidden-import=PyQt5.QtGui ^
  --hidden-import=PyQt5.QtWidgets ^
  --hidden-import=PyQt5.QtNetwork ^
  --hidden-import=PyQt5.QtTextToSpeech ^
  --hidden-import=cv2 ^
  --hidden-import=numpy ^
  --hidden-import=pynput ^
  --hidden-import=pynput.keyboard ^
  --hidden-import=pynput.keyboard._win32 ^
  --collect-all ctranslate2 ^
  --exclude-module torch ^
  --exclude-module transformers ^
  --exclude-module tensorflow ^
  --collect-all sentencepiece ^
  main.py

if errorlevel 1 (
    echo.
    echo === BUILD FAILED ===
    exit /b 1
)

echo Copying assets...
xcopy /e /i /y assets dist\overlingo\assets

REM End-user README (separate from the technical README.md in the repo) -
REM explains the Tesseract requirement and first steps without having to
REM read the code. English is the main README.txt, Bulgarian is
REM README_bg.txt.
copy /y README_DIST_en.txt dist\overlingo\README.txt
copy /y README_DIST_bg.txt dist\overlingo\README_bg.txt

REM Tesseract is NOT bundled - Overlingo relies entirely on a system
REM installation (see README.md "Installation"); the user installs it
REM (UB Mannheim installer). See also the comment at TESSERACT_PATHS in
REM utils/config.py for why we deliberately dropped bundling.

REM settings.json is deliberately NOT copied - it contains personal settings/API
REM keys; the app generates a clean file on first launch
REM (see core/settings_manager.py - fallback to DEFAULT_SETTINGS).

REM Zip archive - Compress-Archive is built into PowerShell (Windows
REM 10/11, no extra tool needed). Runs from dist\ so the archive
REM contains an "overlingo\" folder rather than the full path.
echo Archiving...
set ARCHIVE_NAME=Overlingo-%VERSION%-win64.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\overlingo' -DestinationPath 'dist\%ARCHIVE_NAME%' -Force"

echo.
echo === Ready! See dist\overlingo\overlingo.exe ===
echo === Archive: dist\%ARCHIVE_NAME% ===
echo.
