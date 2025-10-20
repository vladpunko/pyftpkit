# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import pydantic
import pydantic_settings

__all__ = ["Credentials", "ConnectionParameters"]


class Credentials(pydantic.BaseModel):
    """Represents authentication credentials for an FTP connection."""

    username: str
    password: pydantic.SecretStr


class ConnectionParameters(pydantic_settings.BaseSettings):
    """Connection parameters for establishing and managing FTP connections."""

    host: str
    port: int = 0  # no ports
    credentials: Credentials
    timeout: int = pydantic.Field(30, description="connection timeout in seconds")
    max_connections: int = pydantic.Field(
        10, description="maximum number of simultaneous connections"
    )
    max_workers: int = pydantic.Field(
        30, description="maximum number of worker threads for parallel tasks"
    )
