# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import pathlib
import secrets
import tempfile
import threading
import types

import pytest
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import ThreadedFTPServer


@pytest.fixture
def host():
    return "ftp.example.com"


@pytest.fixture
def port():
    return 21


@pytest.fixture
def username():
    return "user"


@pytest.fixture
def password():
    return secrets.token_urlsafe(128)


@pytest.fixture
def ftp_server(fs, username, password):
    homedir = tempfile.mkdtemp()

    authorizer = DummyAuthorizer()
    authorizer.add_anonymous(homedir, perm="el")
    authorizer.add_user(username, password, homedir, perm="delmrw")

    handler = FTPHandler
    handler.authorizer = authorizer

    server = ThreadedFTPServer(("127.0.0.1", 0), handler)
    host, port = server.address

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield types.SimpleNamespace(
        host=host,
        port=port,
        home=pathlib.Path(homedir),
        root=pathlib.Path("/"),
    )

    if server:
        server.close()

    if thread.is_alive():
        thread.join()
