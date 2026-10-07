"""
Stubs for libraries missing from the current environment.

They are substituted ONLY if the real library can't be imported -
if it is installed, the tests use it. With OVERLINGO_TEST_STUBS=1 they
are always substituted (GitHub Actions): the tests check logic, while
real Qt/pynput/audio/network can hang on a headless machine. A stub accepts
any attribute access and call and does nothing - enough to import the
project's modules (e.g. `class TranslationThread(QThread)`) without
running a real UI, audio or network.
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


# Package -> submodules the project imports.
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
