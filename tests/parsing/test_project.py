import os
from pathlib import Path

import pytest

from py2anki.parse.parse import ParsedProject
from py2anki.parse.parsed_entities import ParsedFile, ParsedFolder


@pytest.fixture
def parsed_project() -> ParsedProject:
    return ParsedProject(
        path=str(Path(__file__).parent / "mock" / "exampleproject" / "exampleproject"),
        package_name="exampleproject",
    )


def test_project_metadata(parsed_project: ParsedProject) -> None:
    assert parsed_project.path == str(
        Path(__file__).parent / "mock" / "exampleproject" / "exampleproject"
    )
    assert parsed_project.package_name == "exampleproject"


def _get_folder_subfolder(parsed_project: ParsedProject, path: Path) -> ParsedFolder:
    """Helper function to traverse and find a specific folder in the project structure."""
    current_folder = parsed_project.root_folder
    next_folder = None
    while current_folder.path != str(path):
        rel_path = path.relative_to(current_folder.path)
        addition = Path(rel_path).parts[0]
        for subfolder in current_folder.subfolders:
            if subfolder.path == str(Path(current_folder.path) / addition):
                next_folder = subfolder
                break
        if next_folder is None:
            raise ValueError(f"Folder {addition} not found in {current_folder.path}")
        current_folder = next_folder
        next_folder = None
    return current_folder


def _get_folder_file(parsed_project: ParsedProject, path: Path) -> ParsedFile:
    folder = _get_folder_subfolder(parsed_project, path.parent)
    for file in folder.files:
        if file.path == str(path):
            return file
    raise ValueError(f"File {path} not found in {folder.path}")


def test_project_folders(parsed_project: ParsedProject) -> None:
    root_path = Path(__file__).parent / "mock" / "exampleproject" / "exampleproject"
    assert parsed_project.root_folder.path == str(root_path)

    # Traverse the subfolders
    for root, dirs, files in os.walk(root_path):
        if Path(root).parts[-1].startswith("__"):
            continue  # ignore __pycache__

        folder = _get_folder_subfolder(parsed_project, Path(root))
        num_files = len(files) if "__init__.py" not in files else len(files) - 1
        num_subfolders = sum(
            1
            for subfolder in dirs
            if "__init__.py" in os.listdir(Path(root) / subfolder)
            and not subfolder.startswith("__")  # ignore __pycache__
        )  # number of subpackages
        assert folder.path == str(Path(root))
        assert len(folder.files) == num_files
        assert len(folder.subfolders) == num_subfolders


def test_project_file_dependencies(parsed_project: ParsedProject) -> None:
    # exampleproject/main.py
    main_file = _get_folder_file(
        parsed_project,
        Path(__file__).parent
        / "mock"
        / "exampleproject"
        / "exampleproject"
        / "main.py",
    )
    assert len(main_file.dependencies) == 1
    assert (
        "exampleproject.subpackage2.nested.extranested.deepfn" in main_file.dependencies
    )
    assert (
        "exampleproject.subpackage2.nested.extranested.deepfn"
        in main_file.functions[0].dependencies
    )

    # exampleproject/subpackage1/foo.py
    foo_file = _get_folder_file(
        parsed_project,
        Path(__file__).parent
        / "mock"
        / "exampleproject"
        / "exampleproject"
        / "subpackage1"
        / "foo.py",
    )
    assert len(foo_file.dependencies) == 0

    # exampleproject/subpackage2/bar.py
    bar_file = _get_folder_file(
        parsed_project,
        Path(__file__).parent
        / "mock"
        / "exampleproject"
        / "exampleproject"
        / "subpackage2"
        / "bar.py",
    )
    assert len(bar_file.dependencies) == 1
    assert "exampleproject.subpackage1.foo.A" in bar_file.dependencies
    assert "exampleproject.subpackage1.foo.A" in bar_file.classes[0].dependencies
    assert len(bar_file.classes[0].methods[0].dependencies) == 0

    # exampleproject/subpackage2/nested/nest.py
    nest_file = _get_folder_file(
        parsed_project,
        Path(__file__).parent
        / "mock"
        / "exampleproject"
        / "exampleproject"
        / "subpackage2"
        / "nested"
        / "nest.py",
    )
    assert len(nest_file.dependencies) == 1
    assert "exampleproject.subpackage2.bar.B" in nest_file.dependencies
    assert len(nest_file.functions[0].dependencies) == 1
    assert "exampleproject.subpackage2.bar.B" in nest_file.functions[0].dependencies

    # exampleproject/subpackage2/nested/extranested/deep.py
    deep_file = _get_folder_file(
        parsed_project,
        Path(__file__).parent
        / "mock"
        / "exampleproject"
        / "exampleproject"
        / "subpackage2"
        / "nested"
        / "extranested"
        / "deep.py",
    )
    assert len(deep_file.dependencies) == 3
    assert "exampleproject.subpackage2.bar.B" in deep_file.dependencies
    assert "exampleproject.subpackage2.nested.nest.nest" in deep_file.dependencies
    assert (
        "exampleproject.subpackage2.nested.extranested.other.other"
        in deep_file.dependencies
    )
    assert len(deep_file.functions[0].dependencies) == 3
    assert "exampleproject.subpackage2.bar.B" in deep_file.functions[0].dependencies
    assert (
        "exampleproject.subpackage2.nested.nest.nest"
        in deep_file.functions[0].dependencies
    )
    assert (
        "exampleproject.subpackage2.nested.extranested.other.other"
        in deep_file.functions[0].dependencies
    )

    # exampleproject/subpackage2/nested/extranested/other.py
    other_file = _get_folder_file(
        parsed_project,
        Path(__file__).parent
        / "mock"
        / "exampleproject"
        / "exampleproject"
        / "subpackage2"
        / "nested"
        / "extranested"
        / "other.py",
    )
    assert len(other_file.dependencies) == 0
    assert len(other_file.functions[0].dependencies) == 0
