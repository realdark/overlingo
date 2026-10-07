"""
Tests for Overlingo.

Run (from the project folder):

    python -m unittest discover -s tests -t .

If a heavy library (PyQt5, pygame, edge_tts, deepl, mss, pynput) is not
installed, it is replaced with an empty stub - see _stubs.py. The tests
only check logic that doesn't depend on these libraries, so they run
the same with or without them.
"""

import logging

from tests import _stubs

_stubs.install()

# The tests deliberately trigger errors and retries - without this the
# output fills with expected warnings and app.log with noise.
logging.disable(logging.CRITICAL)
