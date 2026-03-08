# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-25

import argparse
import logging

import pydantic
import pytest

from pyftpkit.loader_settings import LoaderSettings


def test_from_arguments_builds_settings_from_namespace(host, port, username, password):
    namespace = argparse.Namespace(
        host=host,
        port=port,
        username=username,
        password=password,
        timeout=15,
        max_connections=5,
        max_workers=12,
        logger_interval=3,
    )

    settings = LoaderSettings.from_arguments(vars(namespace))

    assert settings.logger_interval == 3
    assert settings.connection_parameters.host == host
    assert settings.connection_parameters.port == port
    assert settings.connection_parameters.timeout == 15
    assert settings.connection_parameters.max_connections == 5
    assert settings.connection_parameters.max_workers == 12
    assert settings.connection_parameters.credentials.username == username
    assert (
        settings.connection_parameters.credentials.password.get_secret_value()
        == password
    )


def test_from_arguments_ignores_none_and_uses_defaults(host, port, username, password):
    namespace = argparse.Namespace(
        host=host,
        port=port,
        username=username,
        password=password,
        max_connections=None,
        timeout=None,
        logger_interval=None,
    )

    settings = LoaderSettings.from_arguments(vars(namespace))

    assert settings.connection_parameters.max_connections == 10
    assert settings.connection_parameters.max_workers == 20
    assert settings.connection_parameters.timeout == 30
    assert settings.logger_interval == 10


@pytest.mark.parametrize("logger_interval", [0, -1])
def test_from_arguments_rejects_invalid_logger_interval(
    host, port, username, password, logger_interval, caplog
):
    namespace = argparse.Namespace(
        host=host,
        port=port,
        username=username,
        password=password,
        logger_interval=logger_interval,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(pydantic.ValidationError) as error:
            LoaderSettings.from_arguments(vars(namespace))

    assert caplog.text == ""
    assert "logger_interval" in str(error.value)


def test_from_arguments_ignores_unknown_arguments(host, port, username, password):
    namespace = argparse.Namespace(
        host=host,
        port=port,
        username=username,
        password=password,
        extra_option="ignored",
    )

    settings = LoaderSettings.from_arguments(vars(namespace))

    assert settings.connection_parameters.host == host
    assert not hasattr(settings, "extra_option")
