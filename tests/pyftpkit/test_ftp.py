# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-27

import socket
import struct
from unittest import mock

from pyftpkit._ftp import _BUFFER_SIZE, FTP


def test_connect_sets_socket_options(host, port):
    ftp_client = FTP()

    with mock.patch("pyftpkit._ftp.ftplib.FTP.connect", return_value="welcome"):
        socket_mock = mock.MagicMock()
        ftp_client.sock = socket_mock

        message = ftp_client.connect(host, port)
        assert message == "welcome"

        expected_calls = [
            mock.call(socket.SOL_SOCKET, socket.SO_RCVBUF, _BUFFER_SIZE),
            mock.call(socket.SOL_SOCKET, socket.SO_SNDBUF, _BUFFER_SIZE),
            mock.call(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
            mock.call(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
            mock.call(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)),
        ]
        socket_mock.setsockopt.assert_has_calls(expected_calls, any_order=False)


def test_connect_skips_socket_options_without_socket(host, port):
    ftp_client = FTP()

    with mock.patch("pyftpkit._ftp.ftplib.FTP.connect", return_value="welcome"):
        with mock.patch("pyftpkit._ftp._set_socket_options") as set_options_mock:
            ftp_client.sock = None

            message = ftp_client.connect(host, port)

    assert message == "welcome"
    set_options_mock.assert_not_called()
