from pathlib import Path

import pytest

from py2anki.parse import ParsedFile, parse_file


@pytest.fixture
def parsed_file() -> ParsedFile:
    return parse_file(str(Path(__file__).parent / "mock" / "basic.py"))


def test_file_metadata(parsed_file: ParsedFile) -> None:
    assert parsed_file.path == str(Path(__file__).parent / "mock" / "basic.py")
    with open(parsed_file.path) as f:
        assert parsed_file.source_code == f.read()

def test_file_content_counts(parsed_file: ParsedFile) -> None:
    assert len(parsed_file.functions) == 1
    assert len(parsed_file.classes) == 1
    assert len(parsed_file.imports) == 0
    assert len(parsed_file.dependencies) == 0

def test_function_parsing(parsed_file: ParsedFile) -> None:
    function = parsed_file.functions[0]

    assert function.name == "bar"
    assert function.docstring == """Perform the Collatz conjecture on the input number x.

Parameters:
    x: The input number

Returns:
    The number of steps it took to reach 1"""  # noqa: E501
    assert function.source_code.strip() == """def bar(x: int) -> int:
    \"""
    Perform the Collatz conjecture on the input number x.

    Parameters:
        x: The input number
    
    Returns:
        The number of steps it took to reach 1
    \"""
    i = 0
    while x != 1:
        i += 1
        if x % 2 == 0:
            x = x // 2
        else:
            x = 3 * x + 1
    
    return i""".strip()  # noqa: W293

def test_class_parsing(parsed_file: ParsedFile) -> None:
    class_ = parsed_file.classes[0]

    assert class_.name == "Foo"
    assert class_.docstring is None
    assert class_.source_code.strip() == """class Foo:
    name: str

    def __init__(self, name: str):
        self.name = name
    
    def say_hello(self) -> str:
        def _private() -> str:
            return "Hello"
        return f"{_private()}, {self.name}\"""".strip()  # noqa: W293
    assert len(class_.methods) == 2
    assert len(class_.parent_classes) == 0
    assert len(class_.dependencies) == 0
