#!/usr/bin/env python

# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import os
import shlex
import shutil
import subprocess
import sys

import pybind11
import pybind11.setup_helpers
import setuptools

__version__ = "1.0.0"

CMAKE = shutil.which("cmake3") or shutil.which("cmake")

DEBUG = os.getenv("DEBUG", "0") == "1"


class CMakeExtension(pybind11.setup_helpers.Pybind11Extension):
    def __init__(self, name: str) -> None:
        super().__init__(name, sources=[])

        self.sourcedir = os.fspath(os.getcwd())


class CMakeBuild(pybind11.setup_helpers.build_ext):
    def build_extension(self, ext: CMakeExtension) -> None:
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))

        if not extdir.endswith(os.sep):
            extdir += os.sep

        build_type = "RelWithDebInfo" if DEBUG else "Release"

        cmake_args = [
            f"-DCMAKE_BUILD_TYPE={build_type!s}",
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir!s}",
            f"-DPYTHON_EXECUTABLE={sys.executable!s}",
        ]
        cmake_args += os.environ.get("CMAKE_ARGS", "").split()

        try:
            import ninja

            ninja_executable_path = os.path.join(ninja.BIN_DIR, "ninja")
            cmake_args += [
                "-DCMAKE_GENERATOR=Ninja",
                f"-DCMAKE_MAKE_PROGRAM:FILEPATH={ninja_executable_path!s}",
            ]
        except ImportError:
            pass  # try to build in any case

        build_path = os.path.join(self.build_temp, ext.name)
        os.makedirs(build_path, exist_ok=True)

        subprocess.check_call(
            shlex.split(f"{CMAKE!s} -S {ext.sourcedir!s}") + cmake_args, cwd=build_path
        )
        subprocess.check_call(shlex.split(f"{CMAKE!s} --build ."), cwd=build_path)


setuptools.setup(
    name="pyftpkit",
    version=__version__,
    description="Asynchronous library for FTP-based file system operations",
    long_description="",
    long_description_content_type="text/markdown",
    author="Vladislav Punko",
    author_email="iam.vlad.punko@gmail.com",
    license="MIT",
    url="https://github.com/vladpunko/pyftpkit",
    project_urls={
        "Issue tracker": "https://github.com/vladpunko/pyftpkit/issues",
        "Source code": "https://github.com/vladpunko/pyftpkit",
    },
    python_requires=">=3.10",
    install_requires=[
        "pycurl>=7.45.2,<8",
        "pydantic>=2.7,<3",
        "pydantic_settings>=2.10,<3",
    ],
    extras_require={
        "dev": [
            "bandit>=1.8,<2.0",
            "black>=25.1,<26.0",
            "flake8>=7.1,<8.0",
            "isort>=6.0,<7.0",
            "mypy>=1.14,<2.0",
            "pre-commit>=4.1,<5.0",
            "ruff>=0.9,<1.0",
            "twine>=6.1,<7.0",
        ],
        "tests": [
            "coverage>=7.6,<8.0",
            "pyfakefs>=5.7,<6.0",
            "pyftpdlib>=2.0,<3",
            "pytest-asyncio>=1.1,<2",
            "pytest-cov>=6.0,<7.0",
            "pytest-html>=4.1,<5.0",
            "pytest-mock>=3.14,<4.0",
            "pytest>=8.3,<9.0",
            "tox>=4.24,<5.0",
        ],
    },
    platforms=["macOS", "POSIX"],
    package_dir={"": "src"},
    packages=[
        "pyftpkit",
    ],
    ext_modules=[
        CMakeExtension("pyftpkit._pathtrie"),
    ],
    cmdclass={
        "build_ext": CMakeBuild,
    },
    include_package_data=True,
    classifiers=[],
)
