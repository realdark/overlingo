"""
ПРОВЕРКА ЗА ИНТЕРНЕТ ВРЪЗКА

Споделена между core/audio_handler.py (edge-tts) и core/translations.py
(Google/DeepL/Microsoft) - всички те са онлайн услуги. Преводът без
интернет (Argos, core/argos.py) нарочно не я ползва - работи изцяло
на компютъра.
"""

from utils.imports import socket


def has_internet_connection(host="8.8.8.8", port=53, timeout=1.5):
    """
    Бърза проверка - опитва TCP връзка към Google DNS (порт 53), без да
    прави реална HTTP заявка. Не е 100% гаранция (възможно е DNS портът
    да е достъпен, а конкретната услуга - не), но е достатъчно бърз и
    надежден сигнал за "няма никаква връзка", за да не чакаме пълния
    retry цикъл напразно в такъв случай.
    """
    try:
        # Таймаутът е само за тази връзка. (По-рано тук се викаше
        # socket.setdefaulttimeout(), което сменяше таймаута на ВСИЧКИ
        # мрежови връзки в програмата.)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
