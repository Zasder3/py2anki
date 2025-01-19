import ast
import importlib
import logging
import os
import sys
from ast import NodeVisitor
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from py2anki.parse.parsed_entities import (
    ParsedClass,
    ParsedFile,
    ParsedFolder,
    ParsedFunction,
)
from py2anki.parse.utils import ManagedModules, get_source_code

logger = logging.getLogger(__name__)

class FileParser(NodeVisitor):
    def __init__(self, path: str, project_root: str):
        with open(path, "r") as f:
            source_code = f.read()
        self.file = ParsedFile(
            path=path,
            source_code=source_code
        )
        self.project_root = project_root
        self.imports: List[str] = []

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

    # import package.module.Class -> store string "package.module.Class"
    # import notpackage.module.Class -> don't store anything
    # import .module.Class -> find the root folder and store "package.module.Class"
    # from package.module import Class -> store string "package.module.Class"

    def _resolve_relative_import(self, relative_import: str, import_level: int) -> str:
        # find the root folder and store "package.module.Class"
        logger.debug(f"Starting with {self.file.path} and import level {import_level}")
        rel_path_of_current_file = os.path.relpath(self.file.path, self.project_root)
        logger.debug(f"Rel path of current file: {rel_path_of_current_file}")
        for _ in range(import_level):
            rel_path_of_current_file = os.path.dirname(rel_path_of_current_file)
        logger.debug(f"Rel path of current file after {import_level} levels: {rel_path_of_current_file}")
        rel_path_of_current_file = rel_path_of_current_file.replace(os.sep, ".")
        return f"{rel_path_of_current_file}.{relative_import}"

    def visit_Import(self, node: ast.Import) -> None:
        logger.debug(f"Import: {node}")
        for alias in node.names:
            logger.debug(f"Alias: {alias.name}")
            if import_level := getattr(node, "level", 0):
                self.imports.append(
                    self._resolve_relative_import(alias.name, import_level))
                logger.debug(f"{self._resolve_relative_import(alias.name, import_level)}")
            else:
                self.imports.append(alias.name)
                logger.debug(f"{alias.name}")
        # dump the node
        logger.debug(f"Node: {ast.dump(node)}")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        logger.debug(f"ImportFrom: {node}")
        if import_level := getattr(node, "level", 0):
            prefix = self._resolve_relative_import(node.module, import_level)
        else:
            prefix = node.module
        for alias in node.names:
            self.imports.append(f"{prefix}.{alias.name}")
            logger.debug(f"{prefix}.{alias.name}")
        # dump the node
        logger.debug(f"Node: {ast.dump(node)}")


def parse_file(path: str, project_root: str) -> ParsedFile:
    parser = FileParser(path, project_root)
    parser.visit(ast.parse(parser.file.source_code))
    return parser.file


class ParsedProject(BaseModel):
    path: str = Field(description="Project path")
    package_name: str = Field(description="Package name")
    root_folder: Optional[ParsedFolder] = Field(
        default=None,
        description="Root folder of the project"
    )
    aliases: Dict[str, str] = Field(
        default_factory=dict,
        description="Dictionary of function and class aliases"
    )

    def model_post_init(self, _) -> None:
        self.parse_init()
        self.root_folder = self.parse_folder(self.path)

    @ManagedModules()
    def parse_init(self) -> None:
        """
        Parse all __init__.py by executing it and capturing its final state.
        """
        try:
            # Add project root to path so imports work
            project_root = os.path.dirname(self.path)
            sys.path.insert(0, project_root)

            # Start with the root package
            root_pkg = self.package_name
            root_path = os.path.join(project_root, root_pkg)

            queue = [(root_path, root_pkg)]

            while queue:
                current_path, current_pkg = queue.pop(0)
                init_path = os.path.join(current_path, "__init__.py")

                # If the __init__.py file exists, execute it and capture its final state
                if os.path.exists(init_path):
                    spec = importlib.util.spec_from_file_location(
                        current_pkg, init_path)
                    if spec and spec.loader:
                        self.execute_and_capture(
                            current_pkg,
                            project_root,
                            current_path,
                            init_path,
                            spec
                        )

                    # Add subfolders to the queue with their full package names
                    for subfolder in os.listdir(current_path):
                        subfolder_path = os.path.join(current_path, subfolder)
                        if os.path.isdir(subfolder_path):
                            subfolder_pkg = f"{current_pkg}.{subfolder}"
                            queue.append((subfolder_path, subfolder_pkg))

        except Exception as e:
            logger.warning(f"Warning: Failed to execute {current_path}: {e}")

    def execute_and_capture(
            self,
            current_pkg: str,
            project_root: str,
            path: str,
            init_path: str,
            spec: importlib.machinery.ModuleSpec
    ) -> None:
        """
        Execute an __init__.py file and capture its exported names.

        Args:
            current_pkg: The full package name (e.g. 'mypackage.submodule')
            project_root: Root directory of the project
            path: Current directory path
            init_path: Path to the __init__.py file
            spec: Module spec for importing
        """
        def _pkg_from_path(path: str) -> str:
            rel_path = os.path.relpath(path, project_root)
            return rel_path.replace(os.sep, '.')

        module = importlib.util.module_from_spec(spec)
        sys.modules[current_pkg] = module
        spec.loader.exec_module(module)
        logger.info(f"Executed {init_path}")

        all_contents = getattr(module, '__all__', [])
        for name in all_contents:
            if item := getattr(module, name, None):
                if module_name := getattr(item, '__module__', None):
                    short_path = f"{_pkg_from_path(path)}.{name}"
                    full_path = f"{module_name}.{name}"
                    self.aliases[short_path] = full_path
                    logger.debug(f"Added alias: {short_path} -> {full_path}")
                else:
                    logger.warning(
                        f"Warning: {name} in {current_pkg} has no __module__ attribute")
            else:
                logger.warning(
                    f"Warning: {name} in {current_pkg} is not a valid module")

    def parse_folder(self, path: str):
        folder = ParsedFolder(
            path=path,
        )
        files = os.listdir(path)
        # remove hidden files and pycache
        files = filter(lambda x: not x.startswith("."), files)
        files = filter(lambda x: not x.endswith(".pyc"), files)
        project_root = os.path.dirname(self.path)
        for file in files:
            if os.path.isfile(os.path.join(path, file)):
                if file != "__init__.py":
                    parsed_file = parse_file(os.path.join(path, file), project_root)
                    folder.files.append(parsed_file)
            elif os.path.isdir(os.path.join(path, file)):
                parsed_sub_folder = self.parse_folder(os.path.join(path, file))
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
    return project

if __name__ == "__main__":
    # Configure basic logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    project = parse_project(
        "tests/parsing/mock/exampleproject/exampleproject", "exampleproject"
    )
    print(project.aliases)
