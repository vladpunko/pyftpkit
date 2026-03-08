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
        20, gt=0, description="maximum number of worker threads for parallel tasks"
    )
    transfer_pause_seconds: pydantic.NonNegativeFloat = pydantic.Field(
        0.0,
        # to reduce `TIME_WAIT` port exhaustion
        description="fixed per-transfer delay (seconds) before the next transfer",
    )
    transfer_retry_count: pydantic.NonNegativeInt = pydantic.Field(
        5,
        description="number of retry attempts for transient FTP connect errors",
    )
    transfer_retry_backoff: pydantic.NonNegativeFloat = pydantic.Field(
        2.0,
        description=(
            "base delay in seconds for connect retries with exponential backoff"
        ),
    )
    extra_options: dict[int, str | int] = pydantic.Field(
        default_factory=dict,
        description="optional dictionary of additional cURL configuration options",
    )
