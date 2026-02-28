# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-13

__all__ = ["FTPError", "FTPPathError", "FTPPathNotAbsoluteError"]


class FTPError(Exception):
    """Base exception for all errors related to FTP operations."""


class FTPPathError(ValueError, TypeError):
    """The path is invalid in the given context."""


class FTPPathNotAbsoluteError(FTPPathError):
    """The path is not absolute."""
