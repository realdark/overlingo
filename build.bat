@echo off
REM UTF-8 в конзолата - иначе българските съобщения излизат като йероглифи
chcp 65001 >nul
echo === Build Overlingo (onedir, Windows) ===

REM Работи от папката на скрипта, независимо откъде е пуснат
REM (%~dp0 = папката на build.bat; /d сменя и диска, ако е различен).
cd /d "%~dp0"

REM Спиране при грешка
setlocal enabledelayedexpansion

REM Версията се чете от utils\version.py - единственото място, където се сменя.
REM Без Python (командата "python" не винаги е в PATH на Windows): редът е
REM APP_VERSION = "3.0" - взимаме частта след "=" и махаме интервали и кавички.
set VERSION=
for /f "tokens=2 delims==" %%v in ('findstr /b /c:"APP_VERSION" utils\version.py') do set VERSION=%%v
if defined VERSION set VERSION=%VERSION: =%
if defined VERSION set VERSION=%VERSION:"=%
if "%VERSION%"=="" (
    echo Не мога да прочета APP_VERSION от utils\version.py
    exit /b 1
)

REM Изчистване на стари билдове
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist overlingo.spec del /q overlingo.spec

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
  --hidden-import=cv2 ^
  --hidden-import=numpy ^
  --hidden-import=pynput ^
  --hidden-import=pynput.keyboard ^
  --hidden-import=pynput.keyboard._win32 ^
  main.py

if errorlevel 1 (
    echo.
    echo === BUILD FAILED ===
    exit /b 1
)

echo Copying assets...
xcopy /e /i /y assets dist\overlingo\assets

REM README за крайния потребител (различен от техническия README.md в
REM repo-то) - обяснява Tesseract изискването и първите стъпки, без да
REM е нужно да чете кода. Английски е основният README.txt, българският
REM е README_bg.txt.
copy /y README_DIST_en.txt dist\overlingo\README.txt
copy /y README_DIST_bg.txt dist\overlingo\README_bg.txt

REM Tesseract НЕ се пакетира - Overlingo разчита изцяло на системна
REM инсталация (виж README.md "Инсталация"), потребителят го слага сам
REM (UB Mannheim инсталатор). Виж и коментара при TESSERACT_PATHS в
REM utils/config.py защо съзнателно отказахме от bundling.

REM НЕ копираме settings.json нарочно - съдържа лични настройки/API
REM ключове; приложението си генерира чист файл при първо стартиране
REM (виж core/settings_manager.py - fallback към DEFAULT_SETTINGS).

REM Архивиране в zip - Compress-Archive е вграден в PowerShell (Windows
REM 10/11 без нужда от допълнителен инструмент). Пуска се от dist\, за
REM да съдържа архивът папка "overlingo\", а не целия път.
echo Archiving...
set ARCHIVE_NAME=Overlingo-%VERSION%-win64.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\overlingo' -DestinationPath 'dist\%ARCHIVE_NAME%' -Force"

echo.
echo === Ready! Виж dist\overlingo\overlingo.exe ===
echo === Archive: dist\%ARCHIVE_NAME% ===
echo.
