"""
Тестове за Overlingo.

Пускане (от папката на проекта):

    python -m unittest discover -s tests -t .

Ако някоя тежка библиотека (PyQt5, pygame, edge_tts, deepl, mss, pynput)
не е инсталирана, се подменя с празен заместител - виж _stubs.py. Тестовете
проверяват само логиката, която не зависи от тези библиотеки, така че
вървят еднакво и с, и без тях.
"""

import logging

from tests import _stubs

_stubs.install()

# Тестовете нарочно предизвикват грешки и повторни опити - без това
# изходът се пълни с очаквани предупреждения, а app.log - с шум.
logging.disable(logging.CRITICAL)
