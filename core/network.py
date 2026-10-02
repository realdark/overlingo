"""
ПРОВЕРКА ЗА ИНТЕРНЕТ ВРЪЗКА

Споделена между core/audio_handler.py (edge-tts) и core/translations.py
(Google/DeepL/Microsoft) - всички те са онлайн услуги. Ollama е нарочно
изключена отвсякъде, където се ползва тази проверка - тя е локална,
работи офлайн по дизайн.
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
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
        return True
    except OSError:
        return False
