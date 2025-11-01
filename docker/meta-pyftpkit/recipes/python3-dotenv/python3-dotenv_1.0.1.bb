# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

HOMEPAGE = "https://github.com/theskumar/python-dotenv"

LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=e914cdb773ae44a732b392532d88f072"

PYPI_PACKAGE = "python-dotenv"
SRC_URI[md5] = "68abb78e05460ce558ca255de550e1ea"
SRC_URI[sha256sum] = "e324ee90a023d808f1959c46bcbc04446a10ced277783dc6ee09987c37ec10ca"

inherit pypi setuptools3

BBCLASSEXTEND += "native nativesdk"
