[English](README.md)

# Overlingo

Настолно приложение за Windows, Linux и macOS, което маркираш произволна
област от екрана и превежда текста в нея — с overlay върху оригинала,
кеширане, автоматично опресняване и глас за озвучаване на превода.

## Функционалности

- Маркиране и превод на текст от всяка част от екрана (OCR чрез Tesseract)
- Преводачи: **превод без интернет** на самия компютър - по подразбиране
  (свободните модели на Argos Translate, пускани с CTranslate2 - без ключ и
  без отделна програма; при първия превод между два езика програмата
  предлага да ги свали, ~70 MB на двойка езици, а без директен модел
  преводът минава през английски), **Google Translate**, **DeepL** и
  **Microsoft Translator**
- Автоматичен fallback към Google, ако основната платена услуга откаже,
  и към превод без интернет, ако няма връзка, а моделите са свалени
- Retry с exponential backoff при временни грешки (напр. 429 Too Many
  Requests) и бърза проверка за интернет връзка преди облачните API-та
- Избор и изтегляне на OCR езици направо от приложението (Settings →
  "Свали език", тегли от `tessdata_fast`)
- Четене на превода на глас **без интернет с гласовете на компютъра** (по
  подразбиране - SAPI на Windows, включително гласовете, добавени от
  Settings → Speech / Narrator; системните гласове на macOS и
  speech-dispatcher на Linux чрез Qt TextToSpeech) или онлайн с естествените гласове на
  **Microsoft Edge** (edge-tts; избират се автоматично според езика на
  превода или от пълния списък). Ако на компютъра няма глас за езика, чете
  онлайн гласът, когато има интернет
- Прозрачен overlay за резултатите, позициониран върху оригиналния текст,
  със същия размер на шрифта (мери се във фоновата нишка - виж
  `core/font_size_detector.py`)
- Кеширане на преводите (не се плаща повторна заявка за вече видян текст)
- Скорост на озвучаването (0.5x-2x, като YouTube)
- "Преведи отново" - нов превод на последно маркираната област без
  ново маркиране
- Прозорец за превод на написан/поставен текст (с бутон / Ctrl+Enter
  или автоматично секунда след последния клавиш - с отметка)
- История на преводите от текущата сесия (не се записва на диска), със
  статистика колко превода са направени и колко са взети от кеша
- Два глобални hotkey-а - "Маркирай и преведи" и "Преведи отново"
  (Windows и Linux под X11; не под Wayland/macOS - виж
  `core/hotkey_manager.py` защо) и минимизиране в taskbar-а
- Отказ от маркирането с Esc или десен бутон
- Само едно копие на програмата - второ стартиране показва вече
  отвореното (`core/single_instance.py`)
- Настройки, организирани в табове (Интерфейс/Превод/Аудио/Hotkey), с
  "Възстанови по подразбиране"; тъмна тема
- Меню "?" с Помощ, За програмата и ръчна проверка за нова версия (GitHub
  Releases - само при поискване, нищо не се сваля автоматично)
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

### 3. Превод и глас без интернет

Преводът без интернет е по подразбиране. Библиотеките `ctranslate2` и
`sentencepiece` идват с `requirements.txt`. Самите модели (по двойка езици)
програмата предлага да свали при първия превод между два езика, а могат да
се свалят и предварително от Настройки → таб „Превод“ → „Свали езиците за
превод без интернет“; отиват в папка `argos-models` до програмата.

Четенето на глас по подразбиране ползва гласовете, инсталирани в
операционната система (на Windows чрез SAPI с pywin32, който вижда и
гласовете, добавени от Settings → Time & language → Speech / Language →
"Text-to-speech"; на macOS и Linux чрез Qt TextToSpeech, част от PyQt5). На Linux е нужен speech-dispatcher (напр.
`sudo apt install speech-dispatcher espeak-ng`). Липсващи езици се добавят
от системните настройки за реч; иначе чете онлайн гласът на Microsoft
Edge, когато има интернет.

При преминаване към нова версия копирай папката `argos-models` в новата,
за да не сваляш моделите отново.

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
  translations.py           Преводачи (Google/DeepL/Microsoft/без интернет) + fallback, кеш, нишки
  translation_controller.py Оркестрация: screenshot → OCR → превод (+ timeout)
  history.py                История на преводите (само за сесията)
  capture.py                Screenshot + OpenCV preprocessing
  settings_manager.py       Зареждане/запис/валидация на настройки
  tesseract_setup.py        Намиране на системния Tesseract
  retry.py                  Retry с exponential backoff
  network.py                Проверка за интернет връзка
  audio_handler.py          Онлайн text-to-speech (edge-tts) чрез фонова нишка
  system_tts.py             Четене без интернет с гласовете на компютъра (SAPI / Qt TextToSpeech)
  audio_playback.py         Play/stop за всички бутони, избор на глас и онлайн резерва
  localization.py           Зареждане на текстовете от assets/locales
  argos.py                  Превод без интернет (моделите на Argos Translate)
  argos_download.py         Сваляне на моделите за превод без интернет
  selftest.py               Автоматична проверка на билда (overlingo --self-test)
  tessdata_download.py      Изтегляне на Tesseract езикови данни
  hotkey_manager.py         Глобални hotkey-и (Windows, Linux/X11)
  single_instance.py        Само едно отворено копие
  update_check.py           Ръчна проверка за нова версия (GitHub Releases)
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
  logging_setup.py           Логване (конзола + app.log), записване на сривове (crash.log)
assets/
  locales/                   bg.json, en.json - всички текстове на интерфейса
  theme.qss                  Тъмна тема
  images/, icons/            Икони
tests/                       Тестове (unittest)
tools/fix_qt_runtime.py      Windows: сменя стария msvcp140.dll на PyQt5 (пуска се от build.bat)
tools/fetch_argos_model.py   Сваля модел за превод без интернет (за проверката в GitHub Actions)
.github/workflows/build.yml  Автоматичен билд + проверка за Windows/Linux/macOS
build_macos.sh               Билд за macOS (Overlingo.app)
install.sh                   Linux: стартер за двоен клик и меню с приложения
README_DIST_*.txt            README за потребителя, влиза в build-а
```

## Build (самостоятелен .exe/binary)

```
build.bat        Windows (PyInstaller, onedir)
build.sh         Linux (PyInstaller, onedir)
build_macos.sh   macOS (PyInstaller, Overlingo.app; пуска се на Mac)
```

Изисква `pip install pyinstaller` предварително и активирана виртуална
среда (`venv`), в която са инсталирани зависимостите. Скриптовете могат да
се пускат от всяка папка - сами влизат в папката на проекта. Резултатът е в
`dist/overlingo/`, заедно с готов архив в `dist/`
(`Overlingo-<версия>-win64.zip` / `Overlingo-<версия>-linux-<архитектура>.tar.gz`).
Версията се сменя само в `utils/version.py` - About прозорецът и имената
на архивите я четат оттам.
`settings.json` нарочно НЕ се копира в build-а — приложението си генерира
чист файл при първо стартиране (виж `core/settings_manager.py`).

На macOS `assets` е вътре в `.app` пакета, а настройките, логовете и
моделите - в `~/Library/Application Support/Overlingo` (пакетът не се
променя). Виж `get_resource_dir()` / `get_data_dir()` в `utils/config.py`.

### Автоматичен билд (GitHub Actions)

`.github/workflows/build.yml` билдва за Windows, Linux, macOS (Apple
Silicon) и macOS (Intel) на машините на GitHub - безплатно за публично
хранилище. За всяка система: тестове → билд → сваляне на малък модел за
превод без интернет → `overlingo --self-test` върху готовия билд
(`core/selftest.py`: библиотеки, Qt, Tesseract, разпознаване на текст,
превод без интернет, главният прозорец).

- Пробен билд: GitHub → Actions → **Build** → **Run workflow**. Архивите са
  в "Artifacts" на страницата на изпълнението (пазят се 14 дни).
- Публикуван release: архивите се прикачват към него автоматично. Тагът
  трябва да е `v` + `APP_VERSION`, иначе билдът спира (проверката за нова
  версия в програмата разчита на това).

Проверката може да се пусне и ръчно върху билд:
`overlingo --self-test [--argos-models ПАПКА] [--require-argos]`.

## Пускане на нова версия

1. Смени номера в `utils/version.py` (формат `3.1`, `3.2`, `3.0.1` - без
   водещи нули; сравнява се числово).
2. Commit и push.
3. GitHub → Releases → нов release с tag **`v` + същия номер** (напр.
   `v3.3`) → Publish. GitHub Actions сам билдва за Windows, Linux и macOS
   и прикача архивите към release-а (около 15-20 минути). Ръчният билд
   с `build.bat` / `build.sh` остава възможен.

"Провери за нова версия" в програмата чете последния публикуван release
и сравнява tag-а му с `utils/version.py` - ако двата се разминават,
проверката ще греши. Чернови и pre-release не се предлагат на
потребителите.

## Git

`.gitignore` пази `settings.json` (може да съдържа API ключ), `app.log`,
`crash.log`, `argos-models/`, `build/`, `dist/` и `venv/` извън хранилището. `.gitattributes` пази
краищата на редовете: `.sh` винаги с Linux (LF), `.bat` с Windows
(CRLF) - иначе скриптовете гърмят, ако минат през другата система. При
качване от Windows `build.sh` и `install.sh` губят флага "изпълним":
`git update-index --chmod=+x build.sh build_macos.sh install.sh` веднъж го оправя.

## Логове

Всички съобщения (INFO/WARNING/ERROR) отиват в конзолата и в `app.log`,
до `settings.json`, с ротация (макс. 1MB, до 3 архива). Неприхванати
грешки също се записват там, вместо програмата да се затвори без следа.

Ако програмата падне в C/C++ библиотека (ctranslate2, OpenCV...), Python
не успява да запише грешка - тогава `crash.log` (до програмата) показва
къде е станал сривът (`faulthandler`).

На Windows `main.py` зарежда `ctranslate2` преди PyQt5: PyQt5 носи по-стара
`msvcp140.dll` и ако тя се зареди първа, преводът без интернет срива
програмата.
`build.bat` пуска преди PyInstaller `tools/fix_qt_runtime.py`: той
преименува стария `msvcp140.dll` (и сродните) в `PyQt5\Qt5\bin` на
`*.old`, ако в `System32` има по-нов - иначе PyInstaller пада при
"Isolated subprocess crashed while importing package 'sentencepiece'",
а билдът би съдържал стария файл. Ръчно: `python tools\fix_qt_runtime.py`;
връщане - махни `.old` от имената.

## Лиценз

GPL-3.0 — виж `LICENSE`. Изисква се от лиценза на PyQt5 (GPL или платен
комерсиален от Riverbank Computing); този проект не ползва комерсиалния.

## Използвани библиотеки/услуги

PyQt5, Tesseract OCR, OpenCV, mss, pytesseract, edge-tts, pygame,
requests, Google Translate, DeepL API, Microsoft Azure Translator,
CTranslate2, SentencePiece, моделите на Argos Translate (OPUS/OpenNMT) —
всяка със собствен лиценз/условия за ползване.
