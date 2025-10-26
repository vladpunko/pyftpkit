# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import ftplib
import socket
import struct
import typing

__all__ = ["FTP"]

_BUFFER_SIZE: typing.Final[int] = 1_048_576  # 1 MB


def _set_socket_options(sock: socket.socket) -> None:
    """Optimizes socket options.

    Parameters
    ----------
    sock : socket.socket
        The socket to configure.
    """
    # Maximize data throughput on high-speed or high-latency networks.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _BUFFER_SIZE)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, _BUFFER_SIZE)

    # Lower latency for small commands.
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # Keep the connection alive while idle, ensuring that pooled sockets remain
    # open and ready for reuse without being closed by timeouts or network inactivity.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    # Instantly close and recreate sockets, avoiding delays and preventing
    # exhaustion of system resources.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))


class FTP(ftplib.FTP):
    """FTP subclass that applies custom socket settings after connecting."""

    def connect(
        self,
        host: str = "",
        port: int = 0,
        timeout: float = -999,
        source_address: tuple[str, int] | None = None,
    ) -> str:
        """Establishes a new connection and applies the socket configuration.

        Parameters
        ----------
        host : str
            Host name for a connection.

        port : int, default=0 (no port is used)
            Port number for a connection.

        timeout : float, default=-999
            Connection timeout in seconds.

        source_address : tuple[str, int], optional
            Source address for the socket to bind to before connecting.

        Returns
        -------
        str
            Server welcome message.
        """
        welcome = super().connect(host, port, timeout, source_address)

        if hasattr(self, "sock") and self.sock:
            _set_socket_options(self.sock)

        return welcome
