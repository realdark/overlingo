"""
ИНФОРМАЦИОННИ ПРОЗОРЦИ: Помощ, За програмата, липсващ Tesseract

Изнесени от ui/main_window.py - самостоятелни са и не зависят от
състоянието на главния прозорец, само от текстовете (i18n).
"""

from utils.imports import QtWidgets, QtCore, QtGui
from utils.version import APP_VERSION
from core.tesseract_setup import configure_tesseract, install_hint, terminal_hint_key
from core.update_check import STATUS_NEWER, STATUS_ERROR

# Изрични ключове (не f"about_feature{i}") - за да се намират с търсене в
# кода и тестът "всеки текст в JSON се ползва някъде" да ги вижда.
ABOUT_FEATURE_KEYS = (
    "about_feature1", "about_feature2", "about_feature3", "about_feature4", "about_feature5",
    "about_feature6", "about_feature7", "about_feature8", "about_feature9", "about_feature10",
    "about_feature11",
)
ABOUT_TECH_KEYS = (
    "about_tech1", "about_tech2", "about_tech3", "about_tech4",
    "about_tech5", "about_tech6", "about_tech7", "about_tech8",
)
HELP_SECTION_KEYS = (  # (заглавие, текст)
    ("help_requirements_title", "help_requirements_body"),
    ("help_workflow_title", "help_workflow_body"),
    ("help_interface_title", "help_interface_body"),
    ("help_translation_title", "help_translation_body"),
    ("help_audio_title", "help_audio_body"),
    ("help_hotkey_title", "help_hotkey_body"),
)


def _rich_message(parent, title, html, icon=QtWidgets.QMessageBox.Information):
    msg = QtWidgets.QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setTextFormat(QtCore.Qt.RichText)
    msg.setText(html)
    msg.setIcon(icon)
    return msg


def show_about(parent, i18n):
    """Прозорецът "За програмата"."""
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
    msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
    msg.exec_()


def show_help(parent, i18n):
    """Прозорецът с кратко ръководство."""
    t = i18n.tr
    sections = "".join(f"<p><b>{t(title)}</b></p><p>{t(body)}</p>" for title, body in HELP_SECTION_KEYS)
    html = f"<h3>{t('help_title')}</h3><p>{t('help_intro')}</p>{sections}"
    msg = _rich_message(parent, t("help_title"), html)
    msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
    msg.exec_()


def show_tesseract_missing(parent, i18n):
    """
    Диалог с командата за инсталиране на Tesseract. "Провери отново" търси
    пак без рестарт, "Копирай командата" я слага в клипборда - и в двата
    случая диалогът остава, докато Tesseract не бъде намерен или
    потребителят не го затвори. Връща True, ако Tesseract е намерен.
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
        msg.addButton(QtWidgets.QMessageBox.Ok)
        msg.exec_()
        clicked = msg.clickedButton()

        if clicked == retry_btn:
            if configure_tesseract():
                QtWidgets.QMessageBox.information(parent, t("tesseract_missing_title"), t("tesseract_found_now"))
                return True
        elif clicked == copy_btn:
            QtWidgets.QApplication.clipboard().setText(command)
            QtWidgets.QMessageBox.information(parent, t("tesseract_missing_title"), t("tesseract_command_copied"))
        else:
            return False


def show_update_result(parent, i18n, result):
    """
    Резултат от "Провери за нова версия" (core.update_check.UpdateResult):
    нова версия - "Изтегли" (отваря страницата на release-а) и OK;
    последна версия или грешка - само OK.
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
    msg.addButton(QtWidgets.QMessageBox.Ok)
    msg.exec_()
    if download_btn is not None and msg.clickedButton() == download_btn:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(result.url))
