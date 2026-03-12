# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-26

import secrets
import shutil
import tempfile
import threading
import types

import pytest
from pyfakefs import fake_filesystem_unittest
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import ThreadedFTPServer


@pytest.fixture
def filesystem_without_root():
    with fake_filesystem_unittest.Patcher(allow_root_user=False) as patcher:
        yield patcher.fs


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
def filenames_with_symbols():
    return [
        "   spaces.txt",
        " space-start.txt",
        ".hidden.txt",
        "backtick`mark.txt",
        "ampersand&and.txt",
        "at@home.txt",
        "braces{0}.txt",
        "brackets[0].txt",
        "caret^caret.txt",
        "café.txt",
        "colon:semicolon.txt",
        "comma,comma.txt",
        "dash--dash.txt",
        "dollar$bill.txt",
        "double  space.txt",
        "double-space-end.txt  ",
        'double"quote.txt',
        "dot...dot.txt",
        "noextension",
        "noextension.with.dots",
        "many.dots.in.name....",
        "archive.with.many.dots.tar.gz",
        "equals=.txt",
        "equals==.txt",
        "exclaim!.txt",
        "façade.txt",
        "greekΩmega.txt",
        "hash#tag.txt",
        "honeycomb-蜂.txt",
        "less<greater>.txt",
        "mañana.txt",
        "مرحبا.txt",
        "नमस्ते.txt",
        "привет.txt",
        "paren(0).txt",
        "percent%value.txt",
        "pipe|pipe.txt",
        "plus+plus.txt",
        "question?mark.txt",
        "quote'.txt",
        "résumé.txt",
        "ruble₽.txt",
        "semi;colon.txt",
        "simple.txt",
        "space-end.txt ",
        "star*star.txt",
        "underscore_name.txt",
        "tilde~tilde.txt",
        "über.txt",
        "with space.txt",
        "αβγ.txt",
        "中文.txt",
        "שלום.txt",
        "日本語.txt",
    ]


@pytest.fixture
def ftp_server(username, password):
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
        home=homedir,
        root="/",
    )

    server.close()

    thread.join(timeout=10)

    if thread.is_alive():
        raise RuntimeError("FTP test server thread did not terminate cleanly.")

    shutil.rmtree(homedir, ignore_errors=True)
