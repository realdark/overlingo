import socket
import unittest
from unittest import mock

from core import network


class InternetCheckTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(network, "_uses_proxy", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_behind_a_proxy_the_real_request_decides(self):
        with mock.patch.object(network, "_uses_proxy", return_value=True), \
             mock.patch.object(network.socket, "create_connection", side_effect=OSError("blocked")) as connect:
            self.assertTrue(network.has_internet_connection())
        connect.assert_not_called()

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
