"""
ONLY ONE INSTANCE OF THE PROGRAM

Two Overlingo instances open at once interfere with each other (both
listen to the same hotkey and write to the same settings.json). The first
instance opens a local "channel" (QLocalServer - a named pipe on Windows,
a socket file on Linux/macOS). Every later launch first tries to connect
to it: if it succeeds, it asks the open instance to show itself and exits.

The channel name includes the user - two people on one computer each get
their own instance.
"""

import getpass

from PyQt5 import QtCore, QtNetwork

from utils.logging_setup import logger


def _server_name():
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"overlingo-{user}"


class SingleInstance(QtCore.QObject):
    # another launch asked the already open instance to show itself
    activation_requested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._name = _server_name()
        self._server = None

    def notify_running_instance(self, timeout_ms=500):
        """True if an instance is already open (and it has been asked to show itself)."""
        socket = QtNetwork.QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
        socket.disconnectFromServer()
        return True

    def listen(self):
        """Starts accepting requests from later launches. Call only
        after notify_running_instance() has returned False."""
        # On Linux/macOS a channel from a previously crashed instance remains as
        # a file and blocks listen() - remove it. We already know nobody listens on it.
        QtNetwork.QLocalServer.removeServer(self._name)
        self._server = QtNetwork.QLocalServer(self)
        if not self._server.listen(self._name):
            logger.warning(f"Second-instance protection could not start: {self._server.errorString()}")
            return False
        self._server.newConnection.connect(self._on_new_connection)
        return True

    def _on_new_connection(self):
        connection = self._server.nextPendingConnection()
        if connection:
            connection.disconnectFromServer()
            connection.deleteLater()
        self.activation_requested.emit()
