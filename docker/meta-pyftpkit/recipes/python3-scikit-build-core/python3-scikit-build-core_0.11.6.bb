# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

HOMEPAGE = "https://github.com/scikit-build/scikit-build-core"

LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=3b4e748e5f102e31c9390dcd6fa66f09"

PYPI_PACKAGE = "scikit_build_core"
SRC_URI += "\
    file://0001-fix-the-issue-with-classifiers.patch \
    file://0002-use-PYTHON_INCLUDE_DIR-to-find-an-interpreter-and-its-headers.patch \
"
SRC_URI[md5sum] = "9b29970958cdff8120e65fa14a007d99"
SRC_URI[sha256sum] = "5982ccd839735be99cfd3b92a8847c6c196692f476c215da84b79d2ad12f9f1b"

DEPENDS = "python3-hatch-vcs-native"

inherit pypi python_hatchling

BBCLASSEXTEND = "native nativesdk"
