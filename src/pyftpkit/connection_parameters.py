# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-14

import pydantic

__all__ = ["Credentials", "ConnectionParameters"]


class Credentials(pydantic.BaseModel):
    """Represents authentication credentials for an FTP connection."""

    username: str
    password: pydantic.SecretStr


class ConnectionParameters(pydantic.BaseModel):
    """Connection parameters for establishing and managing FTP connections."""

    host: str
    port: pydantic.NonNegativeInt = 0  # no ports
    credentials: Credentials
    timeout: pydantic.NonNegativeInt = pydantic.Field(
        30, description="connection timeout in seconds"
    )
    max_connections: pydantic.NonNegativeInt = pydantic.Field(
        10, gt=0, description="maximum number of simultaneous connections"
    )
    max_queues_size: pydantic.NonNegativeInt = pydantic.Field(
        100_000,
        gt=0,
        description=(
            "bound queues so a slow consumer cannot cause unbounded memory usage"
        ),
    )
    max_workers: pydantic.NonNegativeInt = pydantic.Field(
        30, gt=0, description="maximum number of worker threads for parallel tasks"
    )
    extra_options: dict[int, str | int] = pydantic.Field(
        default_factory=dict,
        description="optional dictionary of additional cURL configuration options",
    )
