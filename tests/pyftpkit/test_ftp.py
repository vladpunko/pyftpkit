# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import socket
import struct
from unittest import mock

from pyftpkit._ftp import _BUFFER_SIZE, FTP


def test_connect_sets_socket_options(host, port):
    ftp = FTP()

    with mock.patch("pyftpkit._ftp.ftplib.FTP.connect", return_value="welcome"):
        socket_mock = mock.MagicMock()
        ftp.sock = socket_mock

        message = ftp.connect(host, port)
        assert message == "welcome"

        expected_calls = [
            mock.call(socket.SOL_SOCKET, socket.SO_RCVBUF, _BUFFER_SIZE),
            mock.call(socket.SOL_SOCKET, socket.SO_SNDBUF, _BUFFER_SIZE),
            mock.call(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
            mock.call(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
            mock.call(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)),
        ]
        socket_mock.setsockopt.assert_has_calls(expected_calls, any_order=False)
