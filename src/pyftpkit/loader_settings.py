# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-12

import collections
import typing

import pydantic
import pydantic_settings

from pyftpkit.connection_parameters import ConnectionParameters, Credentials

__all__ = ["LoaderSettings"]


class LoaderSettings(pydantic_settings.BaseSettings):
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
    raise_on_error: bool = pydantic.Field(
        True, description="whether to raise as soon as a transfer error occurs"
    )
    max_raises: pydantic.NonNegativeInt = pydantic.Field(
        100,
        gt=0,
        description="maximum number of errors allowed before aborting",
    )
    batch_pause_every: pydantic.NonNegativeInt = pydantic.Field(
        3500,
        ge=0,
        description="transfers between pause intervals",
    )
    batch_pause_seconds: pydantic.NonNegativeFloat = pydantic.Field(
        10.0,
        ge=0,
        description="pause duration in seconds",
    )

    @classmethod
    def from_arguments(
        cls: type["LoaderSettings"], arguments: dict[str, typing.Any]
    ) -> "LoaderSettings":
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

            if key in ConnectionParameters.model_fields:
                connection_parameters[key] = value

                continue

            if key in Credentials.model_fields:
                connection_parameters["credentials"][key] = value

                continue

            overrides[key] = value

        return cls(**overrides)
