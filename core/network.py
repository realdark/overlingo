"""
INTERNET CONNECTION CHECK

Shared by core/audio_handler.py (edge-tts) and core/translations.py
(Google/DeepL/Microsoft) - all of them are online services. Offline
translation (Argos, core/argos.py) deliberately does not use it - it runs
entirely on the computer.
"""

import urllib.request

from utils.imports import socket


def _uses_proxy():
    """An HTTP(S) proxy is set (environment / system settings) - see has_internet_connection."""
    try:
        proxies = urllib.request.getproxies()
    except Exception:
        return False
    return bool(proxies.get("https") or proxies.get("http"))


def has_internet_connection(host="8.8.8.8", port=53, timeout=1.5):
    """
    Quick check - tries a TCP connection to Google DNS (port 53) without
    making a real HTTP request. Not a 100% guarantee (the DNS port may be
    reachable while the specific service is not), but it is a fast and
    reliable enough signal for "no connection at all", so we don't wait
    through the full retry cycle for nothing in that case.

    Behind a proxy (company networks) direct connections are often blocked
    while the web works through the proxy - then the check is skipped and the
    real request decides; otherwise online translation never worked there.
    """
    if _uses_proxy():
        return True
    try:
        # The timeout applies only to this connection. (This used to call
        # socket.setdefaulttimeout(), which changed the timeout of ALL
        # network connections in the program.)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
