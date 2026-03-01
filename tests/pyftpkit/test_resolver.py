# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-03-01

import logging
import pathlib

import pytest

from pyftpkit._paths_resolver.expander import LocalTreeExpander
from pyftpkit._paths_resolver.resolver import UploadResolver


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


@pytest.mark.asyncio
async def test_file_renamed_to_destination(fs_without_root, upload_resolver):
    source_path = pathlib.Path("/data")
    source_path.mkdir()
    source_path /= "a.txt"
    source_path.write_text("")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(str(source_path), "output/b.txt")
    )

    assert resolved_pairs == [(str(source_path), "output/b.txt")]


@pytest.mark.asyncio
async def test_file_placed_in_destination_directory(fs_without_root, upload_resolver):
    source_path = pathlib.Path("/data")
    source_path.mkdir()
    source_path /= "a.txt"
    source_path.write_text("")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(str(source_path), "output/")
    )

    assert resolved_pairs == [(str(source_path), "output/a.txt")]


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", ["output/", "output"])
async def test_directory_preserves_name_in_destination(
    fs_without_root, upload_resolver, destination
):
    directory_path = pathlib.Path("/data")
    directory_path.mkdir()
    first_file_path = directory_path / "1.txt"
    first_file_path.write_text("")
    second_file_path = directory_path / "2.txt"
    second_file_path.write_text("")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(str(directory_path), destination)
    )

    assert set(resolved_pairs) == {
        ("/data/1.txt", "output/data/1.txt"),
        ("/data/2.txt", "output/data/2.txt"),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["/data/", "/data/*"])
@pytest.mark.parametrize("destination", ["output/", "output"])
async def test_directory_contents_only(
    fs_without_root, upload_resolver, source, destination
):
    directory_path = pathlib.Path("/data")
    directory_path.mkdir()
    first_file_path = directory_path / "1.txt"
    first_file_path.write_text("")
    second_file_path = directory_path / "2.txt"
    second_file_path.write_text("")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(source, destination)
    )

    assert set(resolved_pairs) == {
        ("/data/1.txt", "output/1.txt"),
        ("/data/2.txt", "output/2.txt"),
    }


@pytest.mark.asyncio
async def test_directory_recursion(fs_without_root, upload_resolver):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    (root_directory / "a.txt").write_text("")
    subdirectory_path = root_directory / "subdir"
    subdirectory_path.mkdir()
    (subdirectory_path / "nested.txt").write_text("")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve("/data/", "output")
    )

    assert set(resolved_pairs) == {
        ("/data/a.txt", "output/a.txt"),
        ("/data/subdir/nested.txt", "output/subdir/nested.txt"),
    }


@pytest.mark.asyncio
async def test_missing_source_raises(fs_without_root, caplog, upload_resolver):
    missing_source_path = "/nonexistent/a.txt"
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(missing_source_path, "output/")
            )

    message = "Source does not exist."
    assert message in caplog.text

    message = "Source path is invalid or missing: {0!r}".format(missing_source_path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_symlink_source_raises(fs_without_root, caplog, upload_resolver):
    target_file_path = pathlib.Path("/data/real.txt")
    target_file_path.parent.mkdir()
    target_file_path.write_text("")

    source_link_path = pathlib.Path("/data/link.txt")
    source_link_path.symlink_to(target_file_path)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(str(source_link_path), "output/")
            )

    message = "Unsupported source type."
    assert message in caplog.text

    message = "Source points to a symlink and cannot be processed: {0!r}".format(
        str(source_link_path)
    )
    assert message in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["/data/a.txt/", "/data/a.txt/*"])
async def test_trailing_suffix_on_file_source_raises(
    fs_without_root, caplog, upload_resolver, source
):
    source_file_path = pathlib.Path("/data/a.txt")
    source_file_path.parent.mkdir()
    source_file_path.write_text("")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(upload_resolver.resolve(source, "output/"))

    message = "File source has an unsupported suffix."
    assert message in caplog.text

    message = "Trailing slash or wildcard applies to directories only: {0!r}".format(
        str(source_file_path)
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_many_sources_to_one_destination(fs_without_root, upload_resolver):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    (root_directory / "1.txt").write_text("")
    (root_directory / "2.txt").write_text("")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(
            [str(root_directory / "1.txt"), str(root_directory / "2.txt")],
            "output/",
        )
    )

    assert set(resolved_pairs) == {
        ("/data/1.txt", "output/1.txt"),
        ("/data/2.txt", "output/2.txt"),
    }


@pytest.mark.asyncio
async def test_many_sources_to_many_destinations(fs_without_root, upload_resolver):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    (root_directory / "1.txt").write_text("")
    (root_directory / "2.txt").write_text("")

    resolved_pairs = await _drain_async_iterator(
        upload_resolver.resolve(
            [str(root_directory / "1.txt"), str(root_directory / "2.txt")],
            ["output/a.txt", "output/b.txt"],
        )
    )

    assert resolved_pairs == [
        ("/data/1.txt", "output/a.txt"),
        ("/data/2.txt", "output/b.txt"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_count, destination_count",
    [
        (2, 1),
        (1, 2),
    ],
)
async def test_many_sources_to_many_destinations_length_mismatch_raises(
    fs_without_root,
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
        source_path.write_text("")
    destination_paths = [
        "output/{0}.txt".format(index) for index in range(1, destination_count + 1)
    ]

    with caplog.at_level(logging.ERROR):
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
async def test_many_sources_to_many_destinations_non_string_destination_raises(
    fs_without_root, caplog, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    source_path = root_directory / "1.txt"
    source_path.write_text("")
    source_value = str(source_path)
    destination_value = 42

    with caplog.at_level(logging.ERROR):
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
async def test_many_sources_to_one_destination_empty_source_list(upload_resolver):
    result = await _drain_async_iterator(upload_resolver.resolve([], "output/"))
    assert result == []


@pytest.mark.asyncio
async def test_empty_directory_yields_nothing(fs_without_root, upload_resolver):
    source_directory = pathlib.Path("/data")
    source_directory.mkdir()
    result = await _drain_async_iterator(upload_resolver.resolve("/data/", "output"))
    assert result == []


@pytest.mark.asyncio
async def test_many_sources_with_non_string_source_raises(
    fs_without_root, caplog, upload_resolver
):
    root_directory = pathlib.Path("/data")
    root_directory.mkdir()
    source_path = root_directory / "1.txt"
    source_path.write_text("")
    invalid_source_value = 42
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError) as error:
            await _drain_async_iterator(
                upload_resolver.resolve(
                    [str(source_path), invalid_source_value],
                    "output/",
                )
            )

    message = "Each source must be a string."
    assert message in caplog.text

    message = "Provided source is not a string: {0!r}".format(invalid_source_value)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_invalid_argument_types_raise_type_error(
    fs_without_root, caplog, upload_resolver
):
    source_path = pathlib.Path("/data/file.txt")
    source_path.parent.mkdir()
    source_path.write_text("")
    destination_paths = ["output/"]
    with caplog.at_level(logging.ERROR):
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
