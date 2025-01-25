from pathlib import Path

import pytest

from py2anki.parse.parse import parse_file
from py2anki.parse.parsed_entities import ParsedFile


@pytest.fixture
def dependency_file() -> ParsedFile:
    root_path = Path(__file__).parent / "mock"
    return parse_file(str(root_path / "dependency.py"), str(root_path))


def test_base_function(dependency_file: ParsedFile):
    assert dependency_file.functions[0].dependencies == []

def test_helper_function(dependency_file: ParsedFile):
    assert dependency_file.functions[1].dependencies == []

def test_dependent_function(dependency_file: ParsedFile):
    assert dependency_file.functions[2].dependencies == ["base_function"]

def test_multiple_dependencies(dependency_file: ParsedFile):
    assert dependency_file.functions[3].dependencies == [
        "base_function", "helper_function"]

def test_nested_dependency(dependency_file: ParsedFile):
    assert dependency_file.functions[4].dependencies == ["dependent_function"]

def test_example_class(dependency_file: ParsedFile):
    assert dependency_file.classes[0].methods[0].dependencies == ["base_function"]
    assert dependency_file.classes[0].methods[1].dependencies == [
        "self.method_with_dependency"]
    assert dependency_file.classes[0].dependencies == ["base_function"]
