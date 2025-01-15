import ast
import importlib
import os
import sys
from ast import NodeVisitor
from types import ModuleType

from py2anki.parse.parsed_entities import (
    ParsedClass,
    ParsedFile,
    ParsedFolder,
    ParsedFunction,
    ParsedProject,
)
from py2anki.parse.utils import get_source_code


class FileParser(NodeVisitor):
    def __init__(self, path: str):
        with open(path, "r") as f:
            print(f"Parsing {path}")
            source_code = f.read()
        self.file = ParsedFile(
            path=path,
            source_code=source_code
        )

    def _get_attribute_string(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_attribute_string(node.value)}.{node.attr}"
        raise ValueError(f"Unsupported expression type: {type(node)}")

    def parse_function(self, node: ast.FunctionDef) -> ParsedFunction:
        function = ParsedFunction(
            docstring=ast.get_docstring(node),
            source_code=get_source_code(node, self.file.source_code),
            name=node.name,
        )

        # Walk the function body to find dependencies, excluding local functions
        local_functions = set()
        for child in ast.walk(node):
            if isinstance(child, ast.FunctionDef):
                local_functions.add(child.name)
            elif isinstance(child, ast.Call):
                if hasattr(child.func, 'id') and child.func.id not in local_functions:
                    function.dependencies.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    function.dependencies.append(self._get_attribute_string(child.func))

        return function

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.file.functions.append(self.parse_function(node))

    def _get_attribute_string(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_attribute_string(node.value)}.{node.attr}"
        return "<unknown>"  # fallback for unsupported expression types

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        source_code = get_source_code(node, self.file.source_code)
        methods = []
        # walk only top level functions
        for child in node.body:
            if isinstance(child, ast.FunctionDef):
                methods.append(self.parse_function(child))

        # unpack method dependencies
        dependencies = []
        for method in methods:
            dependencies.extend(
                filter(lambda x: not x.startswith("self."), method.dependencies)
            )

        # Handle different types of base class expressions
        parent_classes = []
        # TODO: this should be a separate ast.NodeVisitor to account for nested ops
        for base in node.bases:
            if isinstance(base, ast.Name):
                parent_classes.append(base.id)
            elif isinstance(base, ast.Attribute):
                # Handle nested module access like a.b.ClassA
                parent_classes.append(self._get_attribute_string(base))

        self.file.classes.append(ParsedClass(
            dependencies=dependencies,
            name=node.name,
            docstring=ast.get_docstring(node),
            source_code=source_code,
            methods=methods,
            parent_classes=parent_classes
        ))

def parse_file(path: str) -> ParsedFile:
    parser = FileParser(path)

    parser.visit(ast.parse(parser.file.source_code))

    return parser.file

def parse_init(path: str, project: ParsedProject) -> None:
    """
    Parse __init__.py by executing it and capturing its final state.

    Args:
        path: Path to the __init__.py file
        project: Project context for adding aliases

    Returns:
        None
    """
    # At this point, future devlopers may ask: why didn't we just parse the file?
    # The answer is that parsing the state of __init__.py is challenging, as it
    # it might be updated with complex conditional logic, list operations, etc.
    # Instead, we execute the file in a controlled environment capturing the end state.

    # Create a controlled module environment
    mock_module = ModuleType('mock_module')
    mock_module.__file__ = path
    mock_module.__package__ = project.package_name

    # Store original state
    original_modules = dict(sys.modules)
    original_path = list(sys.path)

    try:
        # Add parent directory to path so relative imports work
        parent_dir = os.path.dirname(os.path.dirname(path))
        sys.path.insert(0, parent_dir)

        # Load and execute the module
        spec = importlib.util.spec_from_file_location("mock_module", path)
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load module at {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules['mock_module'] = module
        spec.loader.exec_module(module)

        # Capture __all__ contents
        all_contents = getattr(module, '__all__', [])

        # Map shortened names to full paths
        module_dir = os.path.dirname(path)
        relative_path = os.path.relpath(module_dir, project.path)
        package_prefix = relative_path.replace(os.sep, '.')

        # Inspect module contents and create aliases
        for name in all_contents:
            if hasattr(module, name):
                item = getattr(module, name)
                if hasattr(item, '__module__') and item.__module__:
                    # Create alias: package.subpackage.name -> package.subpackage.module.name  # noqa: E501
                    short_path = f"{package_prefix}.{name}" if package_prefix != '.' else name  # noqa: E501
                    full_path = f"{item.__module__}.{name}"
                    project.aliases[short_path] = full_path

    except Exception as e:
        print(f"Warning: Failed to execute {path}: {e}")

    finally:
        # Restore original state
        sys.modules.clear()
        sys.modules.update(original_modules)
        sys.path[:] = original_path

def parse_folder(path: str, project: ParsedProject):
    folder = ParsedFolder(
        path=path,
    )
    files = os.listdir(path)
    # remove hidden files and pycache
    files = filter(lambda x: not x.startswith("."), files)
    files = filter(lambda x: not x.endswith(".pyc"), files)
    for file in files:
        if os.path.isfile(os.path.join(path, file)):
            if file == "__init__.py":
                parse_init(os.path.join(path, file), project)
            else:
                parsed_file = parse_file(os.path.join(path, file))
                folder.files.append(parsed_file)
        elif os.path.isdir(os.path.join(path, file)):
            parsed_sub_folder = parse_folder(os.path.join(path, file), project)
            folder.subfolders.append(parsed_sub_folder)
    return folder


def parse_project(path: str, package_name: str) -> ParsedProject:
    """
    Parse an entire python package from source directory.

    Arguments:
        path: location of the package
        package_name: alias which the package uses (e.g. torch)
    Returns:
        A parsed structure of the project linking function dependencies.
    """
    project = ParsedProject(
        path=path,
        package_name=package_name,
    )
    project.root_folder = parse_folder(path, project)
    return project

if __name__ == "__main__":
    project = parse_project(
        "tests/parsing/mock/exampleproject/exampleproject", "exampleproject"
    )
    print(project.aliases)
