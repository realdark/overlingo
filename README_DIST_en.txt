==============================
 Overlingo - Getting Started
==============================

What is this?
--------------
Overlingo lets you mark any area of your screen, recognizes the text in
it (OCR), and translates it - either directly over the original text
(overlay) or in the app's toolbar. It can also read the translation
out loud.


IMPORTANT - before first launch
----------------------------------
Overlingo requires Tesseract OCR to be installed separately on your
computer (it is not bundled in this folder). Without it, the app will
not be able to recognize text.

  Windows:
    winget install --id UB-Mannheim.TesseractOCR -e
    (or manually from https://github.com/UB-Mannheim/tesseract/wiki)

  Linux:
    sudo apt install tesseract-ocr
    (Fedora: sudo dnf install tesseract   |   Arch: sudo pacman -S tesseract)

  macOS:
    brew install tesseract

If Tesseract is missing, Overlingo will show a dialog with the exact
steps and a "Check again" button - once installed, there is nothing
else to configure.

Additional recognition languages (besides English) - either via the
command above with a -all / -bul / -deu etc. suffix, or directly from
the app: Settings -> "Download language".


How to run it
---------------
  Windows:  double-click overlingo.exe

  Linux:    First (one time only), so you can later open it with a
            double-click and from the applications menu:

              ./install.sh

            After that, Overlingo shows up in the applications menu,
            and an "Overlingo" launcher with the app icon appears in
            this folder - double-click that one, just like on
            Windows. (Not the plain "overlingo" file without an icon -
            most Linux file managers won't run it on double-click.)
            If the file manager asks whether the launcher is trusted
            the first time, choose "Launch" - it only asks once.

            If you move this folder, run ./install.sh again.

            Running it straight from a terminal, without install.sh,
            still works too:

              ./overlingo

  macOS:    Drag Overlingo.app to Applications. The first time, open it
            with right-click -> Open -> Open (the app is not signed with
            a paid Apple developer certificate, so a plain double-click
            only shows a warning). After that it opens normally.

            The first time you translate from the screen, macOS asks for
            "Screen Recording" permission: System Settings -> Privacy &
            Security -> Screen Recording -> turn on Overlingo, then
            restart the app. Without it the captured area is empty.

            Settings, logs and offline models are kept in
            ~/Library/Application Support/Overlingo (not in the app).
            Global hotkeys are not available on macOS yet.

The first launch creates its own settings file next to the executable
(on macOS: in ~/Library/Application Support/Overlingo) - nothing else
needs to be configured beforehand.


First steps in the app
-------------------------
1. Click "Select & Translate" and drag with the mouse over the area
   you want to translate (Esc or right-click cancels).
2. The translation appears over the original text (overlay) or in the
   app's toolbar - depending on your settings.
3. The circular arrow next to it translates the same area again -
   handy for subtitles and text that changes.
4. "Aa" opens a window for translating typed or pasted text, and the
   clock shows the translation history of the current session.
5. "?" contains the full guide (Help), information about the app and
   "Check for updates".
6. The gear icon opens Settings - choose your translation provider
   (Google/DeepL/Microsoft/offline), target language, voice, hotkeys,
   etc.

No API key is needed by default - the built-in Google translation
works right away. DeepL/Microsoft require your own key (paid services
with a free tier). "On this computer (offline)" translates without
internet: in Settings -> "Translation" press "Download offline
languages" once (about 70 MB per language pair). Downloaded languages
are also used automatically when the internet is down. They are kept
in the "argos-models" folder next to the program - copy it over when
you move to a new version so you don't download them again.


Having trouble?
-----------------
- "Tesseract not found" -> see above, install it and click "Check
  again" in the dialog.
- The overlay/toolbar isn't visible -> check the "Hide overlay panel" /
  "Translate directly over text" settings.
- The program closes by itself -> the cause is in app.log and crash.log
  in the program folder (macOS: ~/Library/Application Support/Overlingo);
  attach them when reporting the problem.
- macOS: the translated area is empty/black -> allow "Screen Recording"
  for Overlingo (see "How to run it") and restart the app.
- Anything else -> the in-app help section ("?") covers every feature
  in detail.
