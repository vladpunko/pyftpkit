# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

__all__ = ["FTPError", "FTPPathError", "FTPPathNotAbsoluteError"]


class FTPError(Exception):
    """Base exception for all errors related to FTP operations."""


class FTPPathError(ValueError, TypeError):
    """The path is invalid in the given context."""


class FTPPathNotAbsoluteError(FTPPathError):
    """The path is not absolute."""
