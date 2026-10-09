"""
INFO DIALOGS: Help, About, missing Tesseract

Moved out of ui/main_window.py - they are self-contained and depend only
on the texts (i18n), not on the main window's state.
"""

import html

from utils.imports import QtWidgets, QtCore, QtGui
from utils.version import APP_VERSION
from core.tesseract_setup import configure_tesseract, install_hint, terminal_hint_key
from core.update_check import STATUS_NEWER, STATUS_ERROR

# Explicit keys (not f"about_feature{i}") - so they can be found by searching
# the code and the "every text in the JSON is used somewhere" test can see them.
ABOUT_FEATURE_KEYS = (
    "about_feature1", "about_feature2", "about_feature3", "about_feature4", "about_feature5",
    "about_feature6", "about_feature7", "about_feature8", "about_feature9", "about_feature10",
    "about_feature11",
)
ABOUT_TECH_KEYS = (
    "about_tech1", "about_tech2", "about_tech3", "about_tech4",
    "about_tech5", "about_tech6", "about_tech7", "about_tech8",
)
HELP_SECTION_KEYS = (  # (title, text)
    ("help_requirements_title", "help_requirements_body"),
    ("help_workflow_title", "help_workflow_body"),
    ("help_interface_title", "help_interface_body"),
    ("help_translation_title", "help_translation_body"),
    ("help_appearance_title", "help_appearance_body"),
    ("help_audio_title", "help_audio_body"),
    ("help_hotkey_title", "help_hotkey_body"),
    ("help_files_title", "help_files_body"),
)


# Qt's standard buttons (OK, Close...) take their text from Qt's own
# translations, which we don't load - they stayed in English with the
# Bulgarian UI. So every button is added with our own text.

def show_message(parent, i18n, title, text, kind="warning"):
    """A simple message with a translated OK button. kind: "info", "warning" or "error"."""
    icons = {
        "info": QtWidgets.QMessageBox.Information,
        "warning": QtWidgets.QMessageBox.Warning,
        "error": QtWidgets.QMessageBox.Critical,
    }
    msg = QtWidgets.QMessageBox(parent)
    msg.setIcon(icons.get(kind, QtWidgets.QMessageBox.Warning))
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setDefaultButton(msg.addButton(i18n.tr("ok_button"), QtWidgets.QMessageBox.AcceptRole))
    msg.exec_()


def _rich_message(parent, title, html, icon=QtWidgets.QMessageBox.Information):
    msg = QtWidgets.QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setTextFormat(QtCore.Qt.RichText)
    msg.setText(html)
    msg.setIcon(icon)
    return msg


def show_about(parent, i18n):
    """The "About" dialog."""
    t = i18n.tr
    features = "".join(f"<li>{t(key)}</li>" for key in ABOUT_FEATURE_KEYS)
    techs = "".join(f"<li>{t(key)}</li>" for key in ABOUT_TECH_KEYS)
    html = f"""
    <h3>{t('app_name')}</h3>
    <p>{t('about_version').format(version=APP_VERSION)}</p>
    <p>{t('about_description')}</p>
    <p><b>{t('about_features')}</b></p>
    <ul>{features}</ul>
    <p><b>{t('about_technologies')}</b></p>
    <ul>{techs}</ul>
    <p>{t('about_copyright')}</p>
    """
    msg = _rich_message(parent, t("about_title"), html)
    msg.addButton(t("close_button"), QtWidgets.QMessageBox.RejectRole)
    msg.exec_()


def help_section_html(title, body):
    """One help topic as HTML: a heading and the text's lines as bullet points."""
    items = "".join(f"<li style='margin-bottom:6px'>{html.escape(line)}</li>" for line in body.splitlines() if line.strip())
    return f"<h3>{html.escape(title)}</h3><ul>{items}</ul>"


class HelpDialog(QtWidgets.QDialog):
    """
    Help: the topics in a list on the left, the chosen one on the right -
    instead of one tall message box with all the text at once.
    """

    def __init__(self, parent, i18n):
        super().__init__(parent, QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowCloseButtonHint)
        t = i18n.tr
        self.setWindowTitle(t("help_title"))
        self.resize(760, 460)
        self.setMinimumSize(560, 340)

        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(t("help_intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        panes = QtWidgets.QHBoxLayout()
        panes.setSpacing(10)
        self.topics = QtWidgets.QListWidget()
        self.topics.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.topics.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.text = QtWidgets.QTextBrowser()
        self.text.setOpenExternalLinks(True)
        self.text.document().setIndentWidth(18)  # bullets close to the edge (Qt default: 40 px)
        self.text.document().setDocumentMargin(10)
        # Text colors follow the dark theme (assets/theme.qss); headings a bit brighter.
        self.text.document().setDefaultStyleSheet("h3 { color: #ffffff; } a { color: #60a5fa; }")
        self._pages = []
        for title_key, body_key in HELP_SECTION_KEYS:
            self.topics.addItem(t(title_key))
            self._pages.append(help_section_html(t(title_key), t(body_key)))
        # Fixed width from the longest title: the theme adds padding to the list
        # (4 px) and to each item (6 px) that sizeHint doesn't know about -
        # without the extra room a horizontal scrollbar appeared under the list.
        metrics = self.topics.fontMetrics()
        longest = max(metrics.horizontalAdvance(t(title_key)) for title_key, _ in HELP_SECTION_KEYS)
        self.topics.setFixedWidth(longest + 48)
        panes.addWidget(self.topics)
        panes.addWidget(self.text, stretch=1)
        layout.addLayout(panes, stretch=1)

        buttons = QtWidgets.QDialogButtonBox()
        close = buttons.addButton(t("close_button"), QtWidgets.QDialogButtonBox.RejectRole)
        close.setAutoDefault(False)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.topics.currentRowChanged.connect(self._show_topic)
        self.topics.setCurrentRow(0)
        self.topics.setFocus()

    def _show_topic(self, row):
        if 0 <= row < len(self._pages):
            self.text.setHtml(self._pages[row])


def show_help(parent, i18n):
    """The short user guide dialog."""
    HelpDialog(parent, i18n).exec_()


def show_tesseract_missing(parent, i18n):
    """
    Dialog with the Tesseract install command. "Check again" searches
    again without a restart, "Copy command" puts it on the clipboard - in both
    cases the dialog stays open until Tesseract is found or the
    user closes it. Returns True if Tesseract was found.
    """
    t = i18n.tr
    command, alt_url = install_hint()
    hint_html = f"<code>{command}</code><br><br><i>{t(terminal_hint_key())}</i>"
    if alt_url:
        hint_html += (
            f'<br><br>{t("tesseract_alt_link_intro")} '
            f'<a href="{alt_url}" style="color:#60a5fa;">{alt_url}</a>'
        )

    while True:
        msg = _rich_message(
            parent, t("tesseract_missing_title"),
            f"{t('tesseract_missing_intro')}<br><br>{hint_html}", QtWidgets.QMessageBox.Warning,
        )
        retry_btn = msg.addButton(t("tesseract_check_again"), QtWidgets.QMessageBox.ActionRole)
        copy_btn = msg.addButton(t("tesseract_copy_command"), QtWidgets.QMessageBox.ActionRole)
        msg.addButton(t("close_button"), QtWidgets.QMessageBox.RejectRole)
        msg.exec_()
        clicked = msg.clickedButton()

        if clicked == retry_btn:
            if configure_tesseract():
                show_message(parent, i18n, t("tesseract_missing_title"), t("tesseract_found_now"), "info")
                return True
        elif clicked == copy_btn:
            QtWidgets.QApplication.clipboard().setText(command)
            show_message(parent, i18n, t("tesseract_missing_title"), t("tesseract_command_copied"), "info")
        else:
            return False


def show_update_result(parent, i18n, result):
    """
    Result of "Check for updates" (core.update_check.UpdateResult):
    new version - "Download" (opens the release page) and OK;
    already up to date or error - OK only.
    """
    t = i18n.tr
    if result.status == STATUS_NEWER:
        text = t("update_available").format(latest=result.latest_version, current=result.current_version)
        icon = QtWidgets.QMessageBox.Information
    elif result.status == STATUS_ERROR:
        text = t("update_check_failed")
        icon = QtWidgets.QMessageBox.Warning
    else:
        text = t("update_up_to_date").format(current=result.current_version)
        icon = QtWidgets.QMessageBox.Information

    msg = _rich_message(parent, t("update_title"), text, icon)
    download_btn = None
    if result.status == STATUS_NEWER:
        download_btn = msg.addButton(t("update_download_button"), QtWidgets.QMessageBox.AcceptRole)
    msg.addButton(t("close_button"), QtWidgets.QMessageBox.RejectRole)
    msg.exec_()
    if download_btn is not None and msg.clickedButton() == download_btn:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(result.url))
