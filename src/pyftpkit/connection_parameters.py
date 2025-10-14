# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import pydantic
import pydantic_settings

__all__ = ["Credentials", "ConnectionParameters"]


class Credentials(pydantic.BaseModel):
    username: str
    password: pydantic.SecretStr


class ConnectionParameters(pydantic_settings.BaseSettings):
    host: str
    port: int = 21
    credentials: Credentials
