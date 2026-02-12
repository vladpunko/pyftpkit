# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import collections
import typing

import pydantic
import pydantic_settings

from pyftpkit.connection_parameters import ConnectionParameters

__all__ = ["Config"]


class Config(pydantic_settings.BaseSettings):
    """Settings required to initialize the asynchronous FTP loader."""

    model_config = pydantic_settings.SettingsConfigDict(
        env_nested_delimiter="__",
        env_prefix="PYFTPKIT_",
        extra="ignore",
    )

    connection_parameters: ConnectionParameters
    logger_interval: pydantic.NonNegativeInt = pydantic.Field(
        10, gt=0, description="number of completed tasks between progress messages"
    )

    @classmethod
    def from_arguments(
        cls: type["Config"], arguments: dict[str, typing.Any]
    ) -> "Config":
        """Creates a new instance from CLI arguments.

        Only explicitly provided arguments override environment-based
        configuration values.
        """
        overrides: dict[str, typing.Any] = {}

        connection_parameters: typing.DefaultDict[str, typing.Any] = (
            overrides.setdefault("connection_parameters", collections.defaultdict(dict))
        )
        for key, value in arguments.items():
            if value is None:
                continue

            match key:
                case "host" | "port" | "timeout" | "max_connections" | "max_workers":
                    connection_parameters[key] = value

                case "username" | "password":
                    connection_parameters["credentials"][key] = value

                case _:
                    overrides[key] = value

        return cls(**overrides)
