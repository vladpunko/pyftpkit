# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

HOMEPAGE = "https://github.com/vladpunko/pyftpkit"

LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=f2b48c6b5565659a3aed6766c79e9a76"

SRC_URI = "git://github.com/vladpunko/pyftpkit.git;branch=master;protocol=https"
SRCREV="722e5b2dd81db78f253bf93ccd999428d89cb780"
S = "${WORKDIR}/git"

DEPENDS = "\
    python3-cmake-native \
    python3-ninja-native \
    python3-pybind11-native \
    python3-scikit-build-core-native \
"

RDEPENDS:${PN} = "\
   python3-pycurl \
   python3-pydantic \
   python3-pydantic-settings \
"

inherit cmake python_setuptools_build_meta

# Avoid fetching or compiling CMake by using the one from the Yocto build tools.
export CMAKE_EXECUTABLE = "${STAGING_BINDIR_NATIVE}/cmake"
export SKBUILD_CMAKE_EXECUTABLE = "${STAGING_BINDIR_NATIVE}/cmake"

# Keep debug symbols intact so Yocto can perform its own stripping later.
export SKBUILD_CMAKE_BUILD_TYPE="Debug"

BBCLASSEXTEND += "native nativesdk"
