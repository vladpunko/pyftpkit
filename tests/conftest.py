# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import secrets

import pytest

from pyftpkit.connection_parameters import ConnectionParameters


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
def connection_parameters(
    host,
    port,
    username,
    password,
):
    return ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
        }
    )
