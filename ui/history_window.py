"""
TRANSLATION HISTORY WINDOW

Shows core.history.TranslationHistory - the latest translations from the current
session (from the screen and from the text translation window). Non-modal - it can
stay open while you translate, and refreshes itself on each new translation.
"""

from utils.imports import QtWidgets, QtCore
from ui.components import AudioButton, CopyButton

PREVIEW_LEN = 70


def _preview(text, limit=PREVIEW_LEN):
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "…"


class HistoryWindow(QtWidgets.QDialog):
    """
    history:            core.history.TranslationHistory
    on_show:            callback(entry) - "Show" (shows the translation in the toolbar panel)
    get_audio_settings: callback() -> AudioOptions (engine, voice, speed, language)
    stats:              core.history.SessionStats - statistics row at the bottom
    """

    def __init__(self, parent, i18n, history, on_show, get_audio_settings, stats):
        super().__init__(parent, QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowCloseButtonHint)
        self.i18n = i18n
        self.history = history
        self.on_show = on_show
        self.stats = stats
        self._entries = []

        self.setMinimumSize(540, 360)  # also fits the statistics to the right of the button row
        layout = QtWidgets.QVBoxLayout(self)

        self.empty_label = QtWidgets.QLabel()
        self.empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label, stretch=1)  # empty history - the label takes the list's place

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setWordWrap(True)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._show_selected())
        self.list_widget.currentRowChanged.connect(lambda _row: self._update_buttons())
        layout.addWidget(self.list_widget, stretch=1)

        buttons = QtWidgets.QHBoxLayout()
        self.show_btn = QtWidgets.QPushButton()
        self.show_btn.clicked.connect(self._show_selected)
        self.copy_btn = CopyButton(i18n, self._selected_translation)
        self.audio_btn = AudioButton(i18n, self._selected_translation, get_audio_settings)
        buttons.addWidget(self.show_btn)
        buttons.addWidget(self.copy_btn)
        buttons.addWidget(self.audio_btn)
        buttons.addStretch()
        # The statistics sit to the right of the button row - as a separate row below
        # them they took up part of the window's free space.
        self.stats_label = QtWidgets.QLabel()
        self.stats_label.setObjectName("muted_label")
        self.stats_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.stats_label.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        buttons.addWidget(self.stats_label)
        layout.addLayout(buttons)

        self.update_texts()
        self.refresh()

    def update_texts(self):
        """UI texts (also called when the language changes)."""
        self.setWindowTitle(self.i18n.tr("history_title"))
        self.empty_label.setText(self.i18n.tr("history_empty"))
        self.show_btn.setText(self.i18n.tr("history_show"))
        self.show_btn.setToolTip(self.i18n.tr("history_show_tooltip"))
        self.copy_btn.update_text()
        self.audio_btn.update_text()
        self._update_stats()

    def _update_stats(self):
        self.stats_label.setText(self.i18n.tr("history_stats").format(
            translations=self.stats.translations, cache_hits=self.stats.cache_hits))
        self.stats_label.setToolTip(self.i18n.tr("history_stats_tooltip"))

    def refresh(self):
        """Reloads the list from the history, keeping the selected entry if it still exists."""
        selected = self._selected_entry()
        self._entries = self.history.items()

        self.list_widget.clear()
        for entry in self._entries:
            item = QtWidgets.QListWidgetItem(f"{_preview(entry.source)}\n→ {_preview(entry.translation)}")
            item.setToolTip(entry.translation)
            self.list_widget.addItem(item)

        has_entries = bool(self._entries)
        self.empty_label.setVisible(not has_entries)
        self.list_widget.setVisible(has_entries)
        if has_entries:
            row = self._entries.index(selected) if selected in self._entries else 0
            self.list_widget.setCurrentRow(row)
        self._update_buttons()
        self._update_stats()

    def _selected_entry(self):
        row = self.list_widget.currentRow()
        return self._entries[row] if 0 <= row < len(self._entries) else None

    def _selected_translation(self):
        entry = self._selected_entry()
        return entry.translation if entry else ""

    def _update_buttons(self):
        enabled = self._selected_entry() is not None
        for btn in (self.show_btn, self.copy_btn, self.audio_btn):
            btn.setEnabled(enabled)

    def _show_selected(self):
        entry = self._selected_entry()
        if entry:
            self.on_show(entry)

    def hideEvent(self, event):
        # hideEvent, not closeEvent - Escape closes the dialog without a closeEvent.
        self.audio_btn.stop()
        super().hideEvent(event)
