# Overlingo

Настолно приложение за Windows, Linux и macOS, което маркираш произволна
област от екрана и превежда текста в нея — с overlay върху оригинала,
кеширане, автоматично опресняване и глас за озвучаване на превода.

## Функционалности

- Маркиране и превод на текст от всяка част от екрана (OCR чрез Tesseract)
- Четири преводача: **Google Translate**, **DeepL**, **Microsoft Azure
  Translator** и **Ollama** (локално, офлайн, без ключ)
- Автоматичен fallback към Google, ако основната платена услуга откаже
  (с изключение на Ollama - тя нарочно не пада тихо към облак)
- Retry с exponential backoff при временни грешки (напр. 429 Too Many
  Requests) и бърза проверка за интернет връзка преди облачните API-та
- Избор и изтегляне на OCR езици направо от приложението (Settings →
  "Свали език", тегли от `tessdata_fast`)
- Избор на глас за озвучаване от пълния списък edge-tts гласове, с
  автоматично допълване при отваряне на Settings
- Прозрачен overlay за резултатите, позициониран върху оригиналния текст
- Кеширане на преводите (не се плаща повторна заявка за вече видян текст)
- Скорост на озвучаването (0.5x-2x, като YouTube)
- "Преведи отново" - нов превод на последно маркираната област без
  ново маркиране
- Прозорец за превод на написан/поставен текст (с бутон / Ctrl+Enter
  или автоматично секунда след последния клавиш - с отметка)
- История на преводите от текущата сесия (не се записва на диска)
- Два глобални hotkey-а - "Маркирай и преведи" и "Преведи отново"
  (Windows и Linux под X11; не под Wayland/macOS - виж
  `core/hotkey_manager.py` защо) и минимизиране в taskbar-а
- Отказ от маркирането с Esc или десен бутон
- Само едно копие на програмата - второ стартиране показва вече
  отвореното (`core/single_instance.py`)
- Настройки, организирани в табове (Интерфейс/Превод/Аудио/Hotkey), с
  "Възстанови по подразбиране"; тъмна тема
- Меню "?" с Помощ и За програмата
- Локализиран интерфейс (български, английски) - текстовете са само в
  `assets/locales/*.json`

## Инсталация

### 1. Python зависимости

```bash
pip install -r requirements.txt
```

### 2. Tesseract OCR (задължително, инсталира се системно на трите платформи)

- **Windows** — `winget install --id UB-Mannheim.TesseractOCR -e` (вградено
  в Windows 10/11, винаги тегли последната версия), или ръчно от
  https://github.com/UB-Mannheim/tesseract/wiki
- **macOS** — `brew install tesseract`
- **Linux** — `sudo apt install tesseract-ocr` (или `dnf`/`pacman` еквивалент)

Overlingo **не пакетира** Tesseract - разчита изцяло на системна
инсталация на трите платформи (виж коментара при `TESSERACT_PATHS` в
`utils/config.py` защо съзнателно отказахме от AppImage/bundled копия:
AppImage build-ът твърдо задава собствен tessdata път, който не може да
се разшири през бутона "Свали език"). Ако Tesseract липсва, Overlingo
показва диалог с точните инструкции при стартиране.

Допълнителни езици за OCR освен английски:
```bash
sudo apt install tesseract-ocr-bul   # или желания език
```
или ползвай бутона "Свали език" в Settings (пише директно в системната
tessdata папка, откривана автоматично).

### 3. Ollama (по избор, за локален/офлайн превод)

```bash
curl -fsSL https://ollama.com/install.sh | sh   # Linux
# или изтегли инсталатора от https://ollama.com/download за Windows/macOS

ollama pull llama3.2
```

Не е нужен, ако ще ползваш само Google/DeepL/Microsoft.

### 4. Стартиране

```bash
python3 main.py
```

### 5. Тестове

```bash
python3 -m unittest discover -s tests -t .
```

Тестват логиката без интерфейс (преводачи, кеш, retry, история,
настройки, hotkey формати, намиране на Tesseract) и текстовете: двата
езика трябва да имат едни и същи ключове и полета, всеки ключ, ползван в
кода, трябва да съществува, и обратно - да няма излишни. Ако някоя тежка
библиотека (PyQt5, pygame...) липсва, тестовете я подменят с празен
заместител (`tests/_stubs.py`), така че вървят и без нея.

## Структура на проекта

```
main.py                    Входна точка (+ защита от второ копие)
core/                       Логика без интерфейс (тестваема)
  translations.py           Преводачи (Google/DeepL/Microsoft/Ollama) + fallback, кеш, нишки
  translation_controller.py Оркестрация: screenshot → OCR → превод (+ timeout)
  history.py                История на преводите (само за сесията)
  capture.py                Screenshot + OpenCV preprocessing
  settings_manager.py       Зареждане/запис/валидация на настройки
  tesseract_setup.py        Намиране на системния Tesseract
  retry.py                  Retry с exponential backoff
  network.py                Проверка за интернет връзка
  audio_handler.py          Text-to-speech (edge-tts) чрез фонова нишка
  audio_playback.py         Споделена play/stop логика
  localization.py           Зареждане на текстовете от assets/locales
  ollama_pull.py            Изтегляне на Ollama модел от приложението
  tessdata_download.py      Изтегляне на Tesseract езикови данни
  hotkey_manager.py         Глобални hotkey-и (Windows, Linux/X11)
  single_instance.py        Само едно отворено копие
  fullscreen_detector.py    Показване над приложения на цял екран (Linux/X11)
  font_size_detector.py     Размер на шрифта на оригиналния текст
ui/                          PyQt5 интерфейс
  main_window.py             Главен прозорец и лента с бутони
  settings_dialog.py         Диалог с настройки
  history_window.py          Прозорец с историята
  text_translate_window.py   Прозорец за превод на текст
  dialogs.py                 Помощ, За програмата, липсващ Tesseract
  components.py              Overlay, маркиране, общи бутони
utils/
  version.py                 APP_VERSION - единственото място за версията
  config.py                  Пътища, настройки по подразбиране
  logging_setup.py           Логване (конзола + app.log)
assets/
  locales/                   bg.json, en.json - всички текстове на интерфейса
  theme.qss                  Тъмна тема
  images/, icons/            Икони
tests/                       Тестове (unittest)
install.sh                   Linux: стартер за двоен клик и меню с приложения
README_DIST_*.txt            README за потребителя, влиза в build-а
```

## Build (самостоятелен .exe/binary)

```
build.bat     Windows (PyInstaller, onedir)
build.sh      Linux (PyInstaller, onedir)
```

Изисква `pip install pyinstaller` предварително. Резултатът е в
`dist/overlingo/`, заедно с готов архив в `dist/`
(`Overlingo-<версия>-win64.zip` / `Overlingo-<версия>-linux-<архитектура>.tar.gz`).
Версията се сменя само в `utils/version.py` - About прозорецът и имената
на архивите я четат оттам.
`settings.json` нарочно НЕ се копира в build-а — приложението си генерира
чист файл при първо стартиране (виж `core/settings_manager.py`).

## Логове

Всички съобщения (INFO/WARNING/ERROR) отиват в конзолата и в `app.log`,
до `settings.json`, с ротация (макс. 1MB, до 3 архива).

## Лиценз

GPL-3.0 — виж `LICENSE`. Изисква се от лиценза на PyQt5 (GPL или платен
комерсиален от Riverbank Computing); този проект не ползва комерсиалния.

## Използвани библиотеки/услуги

PyQt5, Tesseract OCR, OpenCV, mss, pytesseract, edge-tts, pygame,
requests, Google Translate, DeepL API, Microsoft Azure Translator,
Ollama — всяка със собствен лиценз/условия за ползване.
