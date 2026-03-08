# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-28

import logging

import pydantic
import pytest

from pyftpkit.connection_parameters import ConnectionParameters


@pytest.mark.parametrize(
    "field, value",
    [
        ("max_connections", 0),
        ("max_queues_size", 0),
        ("max_workers", 0),
        ("port", -1),
        ("timeout", -1),
        ("transfer_pause_seconds", -0.1),
        ("transfer_retry_backoff", -0.1),
        ("transfer_retry_count", -1),
    ],
)
def test_connection_parameters_reject_invalid_values(
    host, port, username, password, field, value, caplog
):
    payload = {
        "host": host,
        "port": port,
        "credentials": {
            "username": username,
            "password": password,
        },
    }
    payload[field] = value

    with caplog.at_level(logging.ERROR):
        with pytest.raises(pydantic.ValidationError) as error:
            ConnectionParameters.model_validate(payload)

    assert caplog.text == ""
    assert field in str(error.value)


@pytest.mark.parametrize(
    "field, value",
    [
        ("timeout", 0),
        ("transfer_pause_seconds", 0),
        ("transfer_retry_backoff", 0),
        ("transfer_retry_count", 0),
    ],
)
def test_connection_parameters_allow_zero_values(
    host, port, username, password, field, value
):
    payload = {
        "host": host,
        "port": port,
        "credentials": {
            "username": username,
            "password": password,
        },
    }
    payload[field] = value

    ConnectionParameters.model_validate(payload)
