# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-03-01

import logging
import os
import pathlib

import pytest

from pyftpkit._paths_resolver.expander import (
    LocalTreeExpander,
    RemoteFTPExpander,
)
from pyftpkit._paths_resolver.resolver import (
    DownloadResolver,
    UploadResolver,
)
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import (
    FTPPathError,
    FTPPathNotAbsoluteError,
)


async def _drain_async_iterator(generator):
    items = []
    async for item in generator:
        items.append(item)

    return items


@pytest.fixture
def local_expander():
    return LocalTreeExpander()


@pytest.fixture
def upload_resolver(local_expander):
    return UploadResolver(expander=local_expander)


@pytest.fixture
def connection_parameters(ftp_server, username, password):
    return ConnectionParameters.model_validate(
        {
            "host": ftp_server.host,
            "port": ftp_server.port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 1,
            "max_workers": 2,
        }
    )


@pytest.fixture
def remote_expander(connection_parameters):
    return RemoteFTPExpander(connection_parameters=connection_parameters)


@pytest.fixture
def download_resolver(remote_expander):
    return DownloadResolver(expander=remote_expander)


@pytest.mark.asyncio
async def test_upload_file_renamed_to_destination(
    filesystem_without_root, upload_resolver
):
    source_path = pathlib.Path("/data")
    source_path.mkdir()
    source_path /= "a.txt"
    source_path.write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(str(source_path), "/output/b.txt")
    )

    assert resolved_pairs == [(str(source_path), "/output/b.txt")]


@pytest.mark.asyncio
async def test_upload_file_placed_in_destination_directory(
    filesystem_without_root, upload_resolver
):
    source_path = pathlib.Path("/data")
    source_path.mkdir()
    source_path /= "a.txt"
    source_path.write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(str(source_path), "/output/")
    )

    assert resolved_pairs == [(str(source_path), "/output/a.txt")]


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", ["/output/", "/output"])
async def test_upload_directory_preserves_name_in_destination(
    filesystem_without_root, upload_resolver, destination
):
    directory_path = pathlib.Path("/data")
    directory_path.mkdir()
    first_file_path = directory_path / "1.txt"
    first_file_path.write_text("", encoding="utf-8")
    second_file_path = directory_path / "2.txt"
    second_file_path.write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(str(directory_path), destination)
    )

    assert set(resolved_pairs) == {
        ("/data/1.txt", "/output/data/1.txt"),
        ("/data/2.txt", "/output/data/2.txt"),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["/data/", "/data/*"])
@pytest.mark.parametrize("destination", ["/output/", "/output"])
async def test_upload_directory_expands_contents_only(
    filesystem_without_root, upload_resolver, source, destination
):
    directory_path = pathlib.Path("/data")
    directory_path.mkdir()
    first_file_path = directory_path / "1.txt"
    first_file_path.write_text("", encoding="utf-8")
    second_file_path = directory_path / "2.txt"
    second_file_path.write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(source, destination)
    )

    assert set(resolved_pairs) == {
        ("/data/1.txt", "/output/1.txt"),
        ("/data/2.txt", "/output/2.txt"),
    }


@pytest.mark.asyncio
async def test_upload_directory_recurses_into_subdirectories(
    filesystem_without_root, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    (root_directory / "a.txt").write_text("", encoding="utf-8")
    subdirectory_path = root_directory / "subdir"
    subdirectory_path.mkdir()
    (subdirectory_path / "nested.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve("/data/", "/output")
    )

    assert set(resolved_pairs) == {
        ("/data/a.txt", "/output/a.txt"),
        ("/data/subdir/nested.txt", "/output/subdir/nested.txt"),
    }


@pytest.mark.asyncio
async def test_upload_supports_pathlike_source_and_destination(
    filesystem_without_root, upload_resolver
):
    source_path = pathlib.Path("/data/file.txt")
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    destination_path = pathlib.Path("/output")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(source_path, destination_path)
    )

    assert resolved_pairs == [(str(source_path), "/output")]


@pytest.mark.asyncio
async def test_upload_pathlike_wildcard_expands_contents_only(
    filesystem_without_root, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    (root_directory / "1.txt").write_text("", encoding="utf-8")
    (root_directory / "2.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(pathlib.Path("/data/*"), pathlib.Path("/output"))
    )

    assert set(resolved_pairs) == {
        ("/data/1.txt", "/output/1.txt"),
        ("/data/2.txt", "/output/2.txt"),
    }


@pytest.mark.asyncio
async def test_upload_supports_many_pathlike_sources(
    filesystem_without_root, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    (root_directory / "1.txt").write_text("", encoding="utf-8")
    (root_directory / "2.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(
            [root_directory / "1.txt", root_directory / "2.txt"],
            "/output",
        )
    )

    assert set(resolved_pairs) == {
        ("/data/1.txt", "/output/1.txt"),
        ("/data/2.txt", "/output/2.txt"),
    }


@pytest.mark.asyncio
async def test_upload_supports_many_to_many_pathlike(
    filesystem_without_root, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    (root_directory / "1.txt").write_text("", encoding="utf-8")
    (root_directory / "2.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(
            [root_directory / "1.txt", root_directory / "2.txt"],
            [pathlib.Path("/output/one.txt"), pathlib.Path("/output/two.txt")],
        )
    )

    assert resolved_pairs == [
        ("/data/1.txt", "/output/one.txt"),
        ("/data/2.txt", "/output/two.txt"),
    ]


@pytest.mark.asyncio
async def test_upload_raises_for_empty_source_path(
    filesystem_without_root, caplog, upload_resolver
):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(upload_resolver.resolve("", "/output/"))

    message = "The path must not be blank or empty."
    assert message in caplog.text

    message = "The path must contain non-whitespace characters: {0!r}".format("")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_whitespace_source_path(
    filesystem_without_root, caplog, upload_resolver
):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(upload_resolver.resolve("   ", "/output/"))

    message = "The path must not be blank or empty."
    assert message in caplog.text

    message = "The path must contain non-whitespace characters: {0!r}".format("   ")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_empty_destination_path(
    filesystem_without_root, caplog, upload_resolver
):
    source_path = pathlib.Path("/data/file.txt")
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(upload_resolver.resolve(str(source_path), ""))

    message = "The path must not be blank or empty."
    assert message in caplog.text

    message = "The path must contain non-whitespace characters: {0!r}".format("")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_whitespace_destination_path(
    filesystem_without_root, caplog, upload_resolver
):
    source_path = pathlib.Path("/data/file.txt")
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(upload_resolver.resolve(str(source_path), "  "))

    message = "The path must not be blank or empty."
    assert message in caplog.text

    message = "The path must contain non-whitespace characters: {0!r}".format("  ")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_parent_reference_source_path(
    filesystem_without_root, caplog, upload_resolver
):
    invalid_source = "../data/file.txt"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(invalid_source, "/output/")
            )

    message = "Parent directory references are not supported in paths."
    assert message in caplog.text

    message = "Parent directory segments are not permitted in paths: {0!r}".format(
        invalid_source
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_parent_reference_destination_path(
    filesystem_without_root, caplog, upload_resolver
):
    source_path = pathlib.Path("/data/file.txt")
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    invalid_destination = "/output/../escape"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(str(source_path), invalid_destination)
            )

    message = "Parent directory references are not supported in paths."
    assert message in caplog.text

    message = "Parent directory segments are not permitted in paths: {0!r}".format(
        invalid_destination
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_backslash_source_path(
    filesystem_without_root, caplog, upload_resolver
):
    invalid_source = "data\\file.txt"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(invalid_source, "/output/")
            )

    message = "Paths containing backslashes are not supported."
    assert message in caplog.text

    message = "The path contains unsupported backslash characters: {0!r}".format(
        invalid_source
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_backslash_destination_path(
    filesystem_without_root, caplog, upload_resolver
):
    source_path = pathlib.Path("/data/file.txt")
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    invalid_destination = "\\\\output\\file.txt"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(str(source_path), invalid_destination)
            )

    message = "Paths containing backslashes are not supported."
    assert message in caplog.text

    message = "The path contains unsupported backslash characters: {0!r}".format(
        invalid_destination
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_relative_destination_path(
    filesystem_without_root, caplog, upload_resolver
):
    source_path = pathlib.Path("/data/file.txt")
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathNotAbsoluteError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(str(source_path), "output")
            )

    message = "The path is not absolute and does not start from the root directory."
    assert message in caplog.text

    message = "Ambiguous path: {0!r}".format("output")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_skips_symlink_inside_directory(
    filesystem_without_root, upload_resolver
):
    source_directory = pathlib.Path("/data")
    source_directory.mkdir()
    target_file_path = source_directory / "real.txt"
    target_file_path.write_text("", encoding="utf-8")
    symlink_path = source_directory / "link.txt"
    symlink_path.symlink_to(target_file_path)

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve("/data/", "/output/")
    )

    assert resolved_pairs == [(str(target_file_path), "/output/real.txt")]


@pytest.mark.asyncio
async def test_upload_raises_for_missing_source(
    filesystem_without_root, caplog, upload_resolver
):
    missing_source_path = "/nonexistent/a.txt"
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(missing_source_path, "/output/")
            )

    message = "Source does not exist."
    assert message in caplog.text

    message = "Source path is invalid or missing: {0!r}".format(missing_source_path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_symlink_source(
    filesystem_without_root, caplog, upload_resolver
):
    target_file_path = pathlib.Path("/data/real.txt")
    target_file_path.parent.mkdir()
    target_file_path.write_text("", encoding="utf-8")

    source_link_path = pathlib.Path("/data/link.txt")
    source_link_path.symlink_to(target_file_path)

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(str(source_link_path), "/output/")
            )

    message = "Unsupported source type."
    assert message in caplog.text

    message = "Source points to a symlink and cannot be processed: {0!r}".format(
        str(source_link_path)
    )
    assert message in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["/data/a.txt/", "/data/a.txt/*"])
async def test_upload_raises_for_trailing_suffix_on_file_source(
    filesystem_without_root, caplog, upload_resolver, source
):
    source_file_path = pathlib.Path("/data/a.txt")
    source_file_path.parent.mkdir()
    source_file_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(upload_resolver.resolve(source, "/output/"))

    message = "File source has an unsupported suffix."
    assert message in caplog.text

    message = "Trailing slash or wildcard applies to directories only: {0!r}".format(
        str(source_file_path)
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_destination_wildcard(
    filesystem_without_root, caplog, upload_resolver
):
    source_path = pathlib.Path("/data/a.txt")
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(str(source_path), "/output/*")
            )

    message = "Destination must not include a wildcard."
    assert message in caplog.text

    message = "Destination must not include a wildcard: {0!r}".format("/output")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_relative_destination_path_in_many_sources(
    filesystem_without_root, caplog, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    source_path = root_directory / "1.txt"
    source_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathNotAbsoluteError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve([str(source_path)], "output")
            )

    message = "The path does not start at the root directory and is not absolute."
    assert message in caplog.text

    message = "Ambiguous path: {0!r}".format("output")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_destination_wildcard(download_resolver, caplog):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                download_resolver.resolve("/file.txt", "/output/*")
            )

    message = "The destination must not contain a wildcard."
    assert message in caplog.text

    message = "Wildcards are not allowed in the destination: {0!r}".format("/output")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_empty_source_path(download_resolver, caplog):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(download_resolver.resolve("", "/output/"))

    message = "The path must not be blank or empty."
    assert message in caplog.text

    message = "The path must contain non-whitespace characters: {0!r}".format("")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_empty_destination_path(download_resolver, caplog):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(download_resolver.resolve("/file.txt", ""))

    message = "The path must not be blank or empty."
    assert message in caplog.text

    message = "The path must contain non-whitespace characters: {0!r}".format("")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_backslash_source_path(download_resolver, caplog):
    invalid_source = "folder\\file.txt"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(
                download_resolver.resolve(invalid_source, "/output/")
            )

    message = "Paths containing backslashes are not supported."
    assert message in caplog.text

    message = "The path contains unsupported backslash characters: {0!r}".format(
        invalid_source
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_backslash_destination_path(
    download_resolver, caplog
):
    invalid_destination = "\\\\output\\file.txt"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(
                download_resolver.resolve("/file.txt", invalid_destination)
            )

    message = "Paths containing backslashes are not supported."
    assert message in caplog.text

    message = "The path contains unsupported backslash characters: {0!r}".format(
        invalid_destination
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_parent_reference_source_path(
    download_resolver, caplog
):
    invalid_source = "../file.txt"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(
                download_resolver.resolve(invalid_source, "/output/")
            )

    message = "Parent directory references are not supported in paths."
    assert message in caplog.text

    message = "Parent directory segments are not permitted in paths: {0!r}".format(
        invalid_source
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_parent_reference_destination_path(
    download_resolver, caplog
):
    invalid_destination = "/output/../escape"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(
                download_resolver.resolve("/file.txt", invalid_destination)
            )

    message = "Parent directory references are not supported in paths."
    assert message in caplog.text

    message = "Parent directory segments are not permitted in paths: {0!r}".format(
        invalid_destination
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_relative_source_path(download_resolver, caplog):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathNotAbsoluteError) as error:
            await _drain_async_iterator(
                download_resolver.resolve("file.txt", "/output/")
            )

    message = "The path is not rooted at the root directory and is not absolute."
    assert message in caplog.text

    message = "Ambiguous path: {0!r}".format("file.txt")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_directory_preserves_name_when_destination_is_plain(
    ftp_server, download_resolver
):
    home_path = pathlib.Path(ftp_server.home)
    directory_path = home_path / "folder"
    directory_path.mkdir()
    (directory_path / "file.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        download_resolver.resolve("/folder", "/output")
    )

    assert resolved_pairs == [("/folder/file.txt", "/output/folder/file.txt")]


@pytest.mark.asyncio
async def test_download_pathlike_wildcard_expands_contents_only(
    ftp_server, download_resolver
):
    home_path = pathlib.Path(ftp_server.home)
    directory_path = home_path / "folder"
    directory_path.mkdir()
    (directory_path / "file.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        download_resolver.resolve(
            pathlib.Path("/folder/*"),
            pathlib.Path("/output"),
        )
    )

    assert resolved_pairs == [("/folder/file.txt", "/output/file.txt")]


@pytest.mark.asyncio
async def test_download_directory_preserves_name_when_destination_has_trailing_slash(
    ftp_server, download_resolver
):
    home_path = pathlib.Path(ftp_server.home)
    directory_path = home_path / "folder"
    directory_path.mkdir()
    (directory_path / "file.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        download_resolver.resolve("/folder", "/output/")
    )

    assert resolved_pairs == [("/folder/file.txt", "/output/folder/file.txt")]


@pytest.mark.asyncio
async def test_download_file_renamed_to_destination(ftp_server, download_resolver):
    home_path = pathlib.Path(ftp_server.home)
    (home_path / "file.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        download_resolver.resolve("/file.txt", "/output.txt")
    )

    assert resolved_pairs == [("/file.txt", "/output.txt")]


@pytest.mark.asyncio
async def test_download_file_existing_destination_yields_pair(
    ftp_server, download_resolver, tmp_path
):
    home_path = pathlib.Path(ftp_server.home)
    (home_path / "file.txt").write_text("", encoding="utf-8")
    destination_path = tmp_path / "output.txt"
    destination_path.write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        download_resolver.resolve("/file.txt", str(destination_path))
    )

    assert resolved_pairs == [("/file.txt", str(destination_path))]


@pytest.mark.asyncio
async def test_download_empty_directory_with_existing_file_destination_raises(
    ftp_server, download_resolver, tmp_path, caplog
):
    home_path = pathlib.Path(ftp_server.home)
    (home_path / "empty").mkdir()
    destination_path = tmp_path / "output.txt"
    destination_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                download_resolver.resolve("/empty", str(destination_path))
            )

    message = "Existing destination is not a directory entry."
    assert message in caplog.text

    message = "A directory is required at destination: {0!r}".format(
        str(destination_path)
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_trailing_suffix_on_file(
    ftp_server, connection_parameters, download_resolver, caplog
):
    home_path = pathlib.Path(ftp_server.home)
    root_path = pathlib.Path(ftp_server.root)
    (home_path / "file.txt").write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                download_resolver.resolve("/file.txt/", "/output/")
            )

    message = "The source path uses an unsupported suffix."
    assert message in caplog.text

    message = "Trailing slash or wildcard is directory-only: {0!r}".format(
        str(root_path / "file.txt")
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_for_missing_source(download_resolver, caplog):
    missing_source_path = "/missing"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                download_resolver.resolve(missing_source_path, "/output/")
            )

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text

    message = "Walk worker error."
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_many_sources_to_single_destination_directory(
    ftp_server, download_resolver
):
    home_path = pathlib.Path(ftp_server.home)
    (home_path / "one.txt").write_text("", encoding="utf-8")
    (home_path / "two.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        download_resolver.resolve(["/one.txt", "/two.txt"], "/output")
    )

    assert set(resolved_pairs) == {
        ("/one.txt", "/output/one.txt"),
        ("/two.txt", "/output/two.txt"),
    }


@pytest.mark.asyncio
async def test_download_many_sources_to_single_destination_with_trailing_slash(
    ftp_server, download_resolver
):
    home_path = pathlib.Path(ftp_server.home)
    (home_path / "one.txt").write_text("", encoding="utf-8")
    (home_path / "two.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        download_resolver.resolve(["/one.txt", "/two.txt"], "/output/")
    )

    assert set(resolved_pairs) == {
        ("/one.txt", "/output/one.txt"),
        ("/two.txt", "/output/two.txt"),
    }


@pytest.mark.asyncio
async def test_download_raises_when_destination_with_trailing_slash_is_file(
    download_resolver, tmp_path, caplog
):
    destination_path = tmp_path / "output"
    destination_path.write_text("", encoding="utf-8")
    destination_with_slash = "{0}/".format(destination_path)

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                download_resolver.resolve("/file.txt", destination_with_slash)
            )

    message = "Existing destination is not a directory path."
    assert message in caplog.text

    message = "A directory is required at destination: {0!r}".format(
        str(destination_path)
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_when_directory_destination_is_file(
    ftp_server, download_resolver, tmp_path, caplog
):
    home_path = pathlib.Path(ftp_server.home)
    directory_path = home_path / "folder"
    directory_path.mkdir()
    (directory_path / "file.txt").write_text("", encoding="utf-8")
    destination_path = tmp_path / "output"
    destination_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                download_resolver.resolve("/folder", str(destination_path))
            )

    message = "Existing destination is not a directory entry."
    assert message in caplog.text

    message = "A directory is required at destination: {0!r}".format(
        str(destination_path)
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_when_many_sources_destination_is_file(
    download_resolver, tmp_path, caplog
):
    destination_path = tmp_path / "output"
    destination_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                download_resolver.resolve(["/one.txt"], str(destination_path))
            )

    message = "Destination exists and is not a directory."
    assert message in caplog.text

    message = "Destination must be a directory: {0!r}".format(str(destination_path))
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_download_raises_when_directory_destination_is_file_with_trailing_slash(
    ftp_server, download_resolver, tmp_path, caplog
):
    home_path = pathlib.Path(ftp_server.home)
    directory_path = home_path / "folder"
    directory_path.mkdir()
    (directory_path / "file.txt").write_text("", encoding="utf-8")
    destination_path = tmp_path / "output"
    destination_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                download_resolver.resolve("/folder/", str(destination_path))
            )

    message = "Existing destination is not a directory path."
    assert message in caplog.text

    message = "Expected a directory at destination: {0!r}".format(str(destination_path))
    assert message in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", ["/output/", "/output"])
async def test_upload_many_sources_to_single_destination(
    filesystem_without_root, upload_resolver, destination
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    (root_directory / "1.txt").write_text("", encoding="utf-8")
    (root_directory / "2.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(
            [str(root_directory / "1.txt"), str(root_directory / "2.txt")],
            destination,
        )
    )

    assert set(resolved_pairs) == {
        ("/data/1.txt", "/output/1.txt"),
        ("/data/2.txt", "/output/2.txt"),
    }


@pytest.mark.asyncio
async def test_upload_many_sources_to_many_destinations(
    filesystem_without_root, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    (root_directory / "1.txt").write_text("", encoding="utf-8")
    (root_directory / "2.txt").write_text("", encoding="utf-8")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(
            [str(root_directory / "1.txt"), str(root_directory / "2.txt")],
            ["/output/a.txt", "/output/b.txt"],
        )
    )

    assert resolved_pairs == [
        ("/data/1.txt", "/output/a.txt"),
        ("/data/2.txt", "/output/b.txt"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_count, destination_count",
    [
        (2, 1),
        (1, 2),
    ],
)
async def test_upload_raises_for_length_mismatch_between_sources_and_destinations(
    filesystem_without_root,
    caplog,
    upload_resolver,
    source_count,
    destination_count,
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    source_paths = [
        root_directory / "{0}.txt".format(index) for index in range(1, source_count + 1)
    ]
    for source_path in source_paths:
        source_path.write_text("", encoding="utf-8")
    destination_paths = [
        "/output/{0}.txt".format(index) for index in range(1, destination_count + 1)
    ]

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(
                    [str(source_path) for source_path in source_paths],
                    destination_paths,
                )
            )

    message = "Source and destination iterable length mismatch."
    assert message in caplog.text

    message = "Source and destination iterables must have equal length."
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_non_string_destination_in_many_to_many(
    filesystem_without_root, caplog, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    source_path = root_directory / "1.txt"
    source_path.write_text("", encoding="utf-8")
    source_value = str(source_path)
    destination_value = 42

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(ValueError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve([source_value], [destination_value])
            )

    message = "Both source and destination must be strings."
    assert message in caplog.text

    message = (
        "It is not possible to process non-string paths."
        "\nSource {0!r} has type: {1!s}".format(
            source_value, type(source_value).__name__
        )
        + "\nDestination {0!r} has type: {1!s}".format(
            destination_value, type(destination_value).__name__
        )
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_non_string_source_in_many_to_many(
    filesystem_without_root, caplog, upload_resolver
):
    destination_value = "/output/1.txt"
    invalid_source_value = 42

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(ValueError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve([invalid_source_value], [destination_value])
            )

    message = "Both source and destination must be strings."
    assert message in caplog.text

    message = (
        "It is not possible to process non-string paths."
        "\nSource {0!r} has type: {1!s}".format(
            invalid_source_value, type(invalid_source_value).__name__
        )
        + "\nDestination {0!r} has type: {1!s}".format(
            destination_value, type(destination_value).__name__
        )
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_many_sources_to_single_destination_with_empty_source_list(
    upload_resolver,
):
    result = await _drain_async_iterator(upload_resolver.resolve([], "/output/"))
    assert result == []


@pytest.mark.asyncio
async def test_upload_empty_directory_yields_nothing(
    filesystem_without_root, upload_resolver
):
    source_directory = pathlib.Path("/data")
    source_directory.mkdir()
    result = await _drain_async_iterator(upload_resolver.resolve("/data/", "/output"))
    assert result == []


@pytest.mark.asyncio
async def test_upload_raises_for_non_string_source_in_many_sources(
    filesystem_without_root, caplog, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    source_path = root_directory / "1.txt"
    source_path.write_text("", encoding="utf-8")
    invalid_source_value = 42
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(ValueError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(
                    [str(source_path), invalid_source_value],
                    "/output/",
                )
            )

    message = "Each source must be a string."
    assert message in caplog.text

    message = "Provided source is not a string: {0!r}".format(invalid_source_value)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_raises_for_invalid_argument_types(
    filesystem_without_root, caplog, upload_resolver
):
    source_path = pathlib.Path("/data/file.txt")
    source_path.parent.mkdir()
    source_path.write_text("", encoding="utf-8")
    destination_paths = ["/output/"]
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(TypeError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(str(source_path), destination_paths)
            )

    message = "Unsupported argument combination."
    assert message in caplog.text

    message = "Invalid argument types passed to resolve: {0!s} and {1!s}.".format(
        type(str(source_path)).__name__, type(destination_paths).__name__
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_upload_resolver_raises_for_pathlike_bytes_source(
    caplog, upload_resolver
):
    class BytesPathLike(os.PathLike):
        def __fspath__(self):
            return b"/data/file.txt"

    pathlike_value = BytesPathLike()

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(
                upload_resolver._one_to_one(pathlike_value, "/output/")
            )

    message = "Paths must be provided as text strings."
    assert message in caplog.text

    message = "Paths must be given as text strings rather than bytes: {0!r}".format(
        b"/data/file.txt"
    )
    assert message in str(error.value)
