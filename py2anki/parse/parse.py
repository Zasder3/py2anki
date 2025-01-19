import ast
import importlib
import logging
import os
import sys
from ast import NodeVisitor

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
    Parse all __init__.py by executing it and capturing its final state.

    Arguments:
        path: Path to the __init__.py file
        project: Project context for adding aliases

    Returns:
        None
    """
    # Create a controlled module environment
    module_dir = os.path.dirname(path)
    relative_path = os.path.relpath(module_dir, project.path)
    package_parts = relative_path.split(os.sep)

    # Create the full module name
    module_name = f"{project.package_name}.{'.'.join(package_parts)}"

    # Store original state
    original_modules = dict(sys.modules)
    original_path = list(sys.path)

    try:
        # Add project root to path so imports work
        project_root = os.path.dirname(project.path)
        sys.path.insert(0, project_root)

        # Set up parent packages in sys.modules
        current_pkg = project.package_name
        current_path = os.path.join(project_root, project.package_name)

        # Initialize root package
        spec = importlib.util.spec_from_file_location(
            current_pkg,
            os.path.join(current_path, "__init__.py")
        )
        if spec and spec.loader:
            root_module = importlib.util.module_from_spec(spec)
            sys.modules[current_pkg] = root_module
            spec.loader.exec_module(root_module)

        # Initialize each subpackage
        for part in package_parts:
            current_pkg = f"{current_pkg}.{part}"
            current_path = os.path.join(current_path, part)
            init_path = os.path.join(current_path, "__init__.py")

            if os.path.exists(init_path):
                spec = importlib.util.spec_from_file_location(current_pkg, init_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[current_pkg] = module
                    spec.loader.exec_module(module)

        # Now load and execute the target module
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load module at {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Capture __all__ contents
        all_contents = getattr(module, '__all__', [])

        # Map shortened names to full paths
        for name in all_contents:
            if item := getattr(module, name, None):
                if module_name := getattr(item, '__module__', None):
                    short_path = f"{relative_path.replace(os.sep, '.')}.{name}"
                    full_path = f"{module_name}.{name}"
                    project.aliases[short_path] = full_path

    except Exception as e:
        logging.warning(f"Warning: Failed to execute {path}: {e}")

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
