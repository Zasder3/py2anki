import ast
from typing import List, Union


def remove_extra_indentation(lines: List[str]) -> str:
    """
    Remove extra indentation from the text.

    Args:
        text: The text to remove extra indentation from.

    Returns:
        The text with extra indentation removed.
    """
    if lines:
        indent = len(lines[0]) - len(lines[0].lstrip())
    else:
        indent = 0
    return "\n".join(line[indent:] for line in lines)


def get_source_code(
        node: Union[ast.FunctionDef, ast.ClassDef],
        source_code: str
) -> str:
    """
    Get the source code of the node.

    Args:
        node: The node to get the source code of.
        source_code: The source code of the file.

    Returns:
        The source code of the node.
    """
    return remove_extra_indentation(
        source_code.split("\n")[node.lineno - 1 : node.end_lineno]
    )
