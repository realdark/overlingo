"""
САМО ЕДНО КОПИЕ НА ПРОГРАМАТА

Две едновременно отворени Overlingo си пречат (двата слушат един и същ
hotkey и пишат в един settings.json). Първото копие отваря локален
"канал" (QLocalServer - named pipe на Windows, socket файл на Linux/macOS).
Всяко следващо стартиране първо пробва да се свърже към него: ако успее,
моли отвореното копие да се покаже и само излиза.

Името на канала съдържа потребителя - двама души на един компютър си
имат по едно свое копие.
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
    # друго стартиране е поискало вече отвореното копие да се покаже
    activation_requested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._name = _server_name()
        self._server = None

    def notify_running_instance(self, timeout_ms=500):
        """True, ако вече има отворено копие (и то е помолено да се покаже)."""
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
        """Започва да приема молби от следващи стартирания. Вика се само
        след като notify_running_instance() е върнал False."""
        # На Linux/macOS канал от сринато предишно копие остава като файл и
        # пречи на listen() - махаме го. Вече знаем, че никой не слуша на него.
        QtNetwork.QLocalServer.removeServer(self._name)
        self._server = QtNetwork.QLocalServer(self)
        if not self._server.listen(self._name):
            logger.warning(f"Защитата от второ копие не можа да стартира: {self._server.errorString()}")
            return False
        self._server.newConnection.connect(self._on_new_connection)
        return True

    def _on_new_connection(self):
        connection = self._server.nextPendingConnection()
        if connection:
            connection.disconnectFromServer()
            connection.deleteLater()
        self.activation_requested.emit()
