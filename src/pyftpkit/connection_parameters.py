# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import argparse
import collections
import typing

import pydantic
import pydantic_settings

__all__ = ["Credentials", "ConnectionParameters"]


class Credentials(pydantic.BaseModel):
    """Represents authentication credentials for an FTP connection."""

    username: str
    password: pydantic.SecretStr


class ConnectionParameters(pydantic_settings.BaseSettings):
    """Connection parameters for establishing and managing FTP connections."""

    model_config = pydantic_settings.SettingsConfigDict(
        env_file_encoding="utf-8",
        env_file=".env",
        env_nested_delimiter="__",
        env_prefix="PYFTPKIT_",
        extra="ignore",
    )

    host: str
    port: pydantic.NonNegativeInt = pydantic.Field(0, gt=0)  # no ports
    credentials: Credentials
    timeout: pydantic.NonNegativeInt = pydantic.Field(
        30, description="connection timeout in seconds"
    )
    max_connections: pydantic.NonNegativeInt = pydantic.Field(
        10, gt=0, description="maximum number of simultaneous connections"
    )
    max_workers: pydantic.NonNegativeInt = pydantic.Field(
        30, gt=0, description="maximum number of worker threads for parallel tasks"
    )
    extra_options: dict[int, str | int] = pydantic.Field(
        default_factory=dict,
        description="optional dictionary of additional cURL configuration options",
    )

    @classmethod
    def from_arguments(
        cls: type["ConnectionParameters"], arguments: argparse.Namespace
    ) -> "ConnectionParameters":
        settings = cls()

        overrides: typing.DefaultDict[str, typing.Any] = collections.defaultdict(dict)
        for key, value in vars(arguments).items():
            if value is None:
                continue

            match key:
                case "host" | "port" | "timeout" | "max_connections" | "max_workers":
                    overrides[key] = value

                case "username" | "password":
                    overrides["credentials"][key] = value

                case _:
                    continue

        return cls.model_validate(settings.model_dump() | overrides)
