import socket
import unittest
from unittest import mock

from core import network


class InternetCheckTest(unittest.TestCase):
    def test_does_not_change_global_socket_timeout(self):
        before = socket.getdefaulttimeout()
        with mock.patch.object(network.socket, "create_connection") as connect:
            self.assertTrue(network.has_internet_connection(timeout=1.5))
        connect.assert_called_once_with(("8.8.8.8", 53), timeout=1.5)
        self.assertEqual(socket.getdefaulttimeout(), before)

    def test_offline(self):
        with mock.patch.object(network.socket, "create_connection", side_effect=OSError("unreachable")):
            self.assertFalse(network.has_internet_connection())


if __name__ == "__main__":
    unittest.main()
