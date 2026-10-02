"""
Core модул - основна функционалност
"""
from .translations import (
    BaseTranslator,
    GoogleTranslator,
    DeepLTranslator,
    MicrosoftTranslator,
    OllamaTranslator,
    FallbackTranslator,
    TranslationCache,
    TranslationThread,
    create_translator,
)
from .translation_controller import TranslationController
from .settings_manager import SettingsManager, SettingsValidationError
from .capture import capture_region_as_gray, capture_full_screen_qimage, CaptureError, warm_up
from .network import has_internet_connection
from .hotkey_manager import HotkeyManager, HOTKEY_SUPPORTED
from .font_size_detector import FontSizeDetector
from .ollama_pull import OllamaPullThread
from .tessdata_download import TessdataDownloadThread
from .audio_handler import AudioThread, EdgeVoicesThread
from .localization import UiLocalizer
from .fullscreen_detector import FullscreenDetector

__all__ = [
    'BaseTranslator',
    'GoogleTranslator',
    'DeepLTranslator',
    'MicrosoftTranslator',
    'OllamaTranslator',
    'FallbackTranslator',
    'TranslationCache',
    'TranslationThread',
    'create_translator',
    'TranslationController',
    'SettingsManager',
    'SettingsValidationError',
    'capture_region_as_gray',
    'capture_full_screen_qimage',
    'CaptureError',
    'warm_up',
    'has_internet_connection',
    'HotkeyManager',
    'HOTKEY_SUPPORTED',
    'FontSizeDetector',
    'OllamaPullThread',
    'TessdataDownloadThread',
    'AudioThread',
    'EdgeVoicesThread',
    'UiLocalizer',
    'FullscreenDetector',
]
