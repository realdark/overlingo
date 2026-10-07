"""
Заместители за библиотеки, които липсват в текущата среда.

Подменят се САМО ако истинската библиотека не може да се импортира -
ако е инсталирана, тестовете ползват нея. С OVERLINGO_TEST_STUBS=1 се
подменят винаги (GitHub Actions): тестовете проверяват логиката, а
истинските Qt/pynput/звук/мрежа на машина без екран могат да увиснат. Заместителят приема всякакви
атрибути и извиквания и не прави нищо - достатъчно, за да се импортират
модулите на проекта (напр. `class TranslationThread(QThread)`), без да
се изпълнява реален интерфейс, звук или мрежа.
"""

import importlib
import os
import sys
import types


class _AnythingMeta(type):
    def __getattr__(cls, name):
        return _Anything


class _Anything(metaclass=_AnythingMeta):
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return _Anything()

    def __getattr__(self, name):
        return _Anything()


def _stub_module(name):
    module = types.ModuleType(name)
    module.__getattr__ = lambda attr: _Anything
    return module


# Пакет -> подмодули, които проектът импортира.
_OPTIONAL = {
    "PyQt5": ["PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets", "PyQt5.QtNetwork"],
    "pygame": [],
    "edge_tts": [],
    "deepl": [],
    "mss": ["mss.tools"],
    "pynput": ["pynput.keyboard"],
}


def install():
    force = os.environ.get("OVERLINGO_TEST_STUBS") == "1"
    for package, submodules in _OPTIONAL.items():
        try:
            if force:
                raise ImportError("OVERLINGO_TEST_STUBS=1")
            importlib.import_module(package)
            for sub in submodules:
                importlib.import_module(sub)
        except Exception:
            parent = _stub_module(package)
            sys.modules[package] = parent
            for sub in submodules:
                child = _stub_module(sub)
                sys.modules[sub] = child
                setattr(parent, sub.rsplit(".", 1)[1], child)
