# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-28

import pydantic
import pytest

from pyftpkit.connection_parameters import ConnectionParameters


@pytest.mark.parametrize(
    "field, value",
    [
        ("max_connections", 0),
        ("max_queue_size", 0),
        ("max_workers", 0),
        ("port", -1),
        ("timeout", -1),
    ],
)
def test_connection_parameters_invalid_values(
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

    with pytest.raises(pydantic.ValidationError):
        ConnectionParameters.model_validate(payload)
