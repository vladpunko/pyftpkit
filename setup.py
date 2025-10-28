#!/usr/bin/env python

# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import os
import pathlib
import platform
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


_os_name = platform.system().lower()
# Make sure this python package is compatible with the current operating system.
if _os_name == "windows" or _os_name.startswith("cygwin"):
    raise RuntimeError("The pyftpkit library doesn't support windows at this moment.")


setuptools.setup(
    name="pyftpkit",
    version=__version__,
    description="Asynchronous library for FTP-based file system operations",
    long_description=pathlib.Path("README.md").read_text(),
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
    install_requires=pathlib.Path("requirements.txt").read_text().splitlines(),
    extras_require={
        "dev": pathlib.Path("requirements-dev.txt").read_text().splitlines(),
        "tests": pathlib.Path("requirements-tests.txt").read_text().splitlines(),
    },
    platforms=["macOS", "POSIX"],
    package_dir={"": "src"},
    packages=[
        "pyftpkit",
    ],
    entry_points={
        "console_scripts": [
            "pyftpkit = pyftpkit.__main__:main",
        ],
    },
    ext_modules=[
        CMakeExtension("pyftpkit._pathtrie"),
    ],
    cmdclass={
        "build_ext": CMakeBuild,
    },
    include_package_data=True,
    classifiers=[
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development",
        "Topic :: Utilities",
        "Typing :: Typed",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    ],
)
