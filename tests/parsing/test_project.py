import os
from pathlib import Path

import pytest

from py2anki.parse.parse import ParsedProject
from py2anki.parse.parsed_entities import ParsedFolder


@pytest.fixture
def parsed_project() -> ParsedProject:
    return ParsedProject(
        path=str(Path(__file__).parent / "mock" / "exampleproject" / "exampleproject"),
        package_name="exampleproject"
    )

def test_project_metadata(parsed_project: ParsedProject) -> None:
    assert parsed_project.path == str(Path(__file__).parent / "mock" / "exampleproject" / "exampleproject")  # noqa: E501
    assert parsed_project.package_name == "exampleproject"

def test_project_folders(parsed_project: ParsedProject) -> None:
    def _get_folder_subfolder(path: Path) -> ParsedFolder:
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

    root_path = Path(__file__).parent / "mock" / "exampleproject" / "exampleproject"
    assert parsed_project.root_folder.path == str(root_path)

    # Traverse the subfolders
    for root, dirs, files in os.walk(root_path):
        if Path(root).parts[-1].startswith("__"):
            continue  # ignore __pycache__

        folder = _get_folder_subfolder(Path(root))
        num_files = len(files) if "__init__.py" not in files else len(files) - 1
        num_subfolders = sum(
            1 for subfolder in dirs
            if "__init__.py" in os.listdir(Path(root) / subfolder)
            and not subfolder.startswith("__")  # ignore __pycache__
        ) # number of subpackages
        assert folder.path == str(Path(root))
        assert len(folder.files) == num_files
        assert len(folder.subfolders) == num_subfolders
