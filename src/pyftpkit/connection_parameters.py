# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import pydantic
import pydantic_settings

__all__ = ["Credentials", "ConnectionParameters"]


class Credentials(pydantic.BaseModel):
    """Represents authentication credentials for an FTP connection.

    Attributes
    ----------
    username : str
        The username used to authenticate with the FTP server.

    password : pydantic.SecretStr
        The password used for secure authentication.
    """

    username: str
    password: pydantic.SecretStr


class ConnectionParameters(pydantic_settings.BaseSettings):
    """Defines connection parameters required to establish an FTP session.

    Attributes
    ----------
    host : str
        The hostname or IP address of the FTP server.

    port : int, default=0 (no port is used)
        The port number for the FTP service.
        Use 0 when connecting via a domain name without specifying an explicit port.

    credentials : Credentials
        The authentication credentials for the connection.
    """

    host: str
    port: int = 0
    credentials: Credentials
