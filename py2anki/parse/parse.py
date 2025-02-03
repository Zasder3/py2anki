import ast
import importlib
import logging
import os
import sys
from ast import NodeVisitor
from typing import Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from py2anki.parse.parsed_entities import (
    ParsedClass,
    ParsedCodeEntity,
    ParsedFile,
    ParsedFolder,
    ParsedFunction,
)
from py2anki.parse.utils import ManagedModules, get_source_code

logger = logging.getLogger(__name__)


class FileParser(NodeVisitor):
    def __init__(self, path: str, project_root: str, package_name: str):
        with open(path, "r") as f:
            source_code = f.read()
        self.file = ParsedFile(path=path, source_code=source_code)
        self.project_root = project_root
        self.imports: List[str] = []
        self.aliases: Dict[str, str] = {}
        self.package_name = package_name

    def resolve_imports(self) -> None:
        """
        For each function and class, resolve imports to their full paths. Then
        remove any imports that are not in the aliases. Ending by adding the
        imports to the file.
        """
        # Remove imports irrelevant to the package
        self.imports = list(
            filter(lambda x: x.startswith(self.package_name), self.imports)
        )
        self.aliases = {
            k: v for k, v in self.aliases.items() if v.startswith(self.package_name)
        }

        for function in self.file.functions:
            for i, import_str in enumerate(function.dependencies):
                if import_str in self.aliases:
                    function.dependencies[i] = self.aliases[import_str]
        for class_ in self.file.classes:
            for i, import_str in enumerate(class_.dependencies):
                if import_str in self.aliases:
                    class_.dependencies[i] = self.aliases[import_str]

        # remove all dependencies that are not package imports or functions/classes
        # defined in the file
        defined_functions = {
            function.name: function for function in self.file.functions
        }
        defined_classes = {class_.name: class_ for class_ in self.file.classes}

        def _filter_fn(x: str) -> bool:
            return x in self.imports or x in defined_functions or x in defined_classes

        for function in self.file.functions:
            function.dependencies = list(filter(_filter_fn, function.dependencies))
        for class_ in self.file.classes:
            class_.dependencies = list(filter(_filter_fn, class_.dependencies))

        # make the files dependencies the union of
        # all the functions and classes dependencies
        # Collect all dependencies from functions and classes
        all_dependencies = []
        for function in self.file.functions:
            all_dependencies.extend(function.dependencies)
        for class_ in self.file.classes:
            all_dependencies.extend(class_.dependencies)

        # Convert to set to remove duplicates and back to list
        self.file.dependencies = list(set(all_dependencies))

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
                if hasattr(child.func, "id") and child.func.id not in local_functions:
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
        # add the parent classes to the dependencies
        dependencies.extend(parent_classes)

        self.file.classes.append(
            ParsedClass(
                dependencies=dependencies,
                name=node.name,
                docstring=ast.get_docstring(node),
                source_code=source_code,
                methods=methods,
                parent_classes=parent_classes,
            )
        )

    # import package.module.Class -> store string "package.module.Class"
    # import notpackage.module.Class -> don't store anything
    # import .module.Class -> find the root folder and store "package.module.Class"
    # from package.module import Class -> store string "package.module.Class"

    def _resolve_relative_import(self, relative_import: str, import_level: int) -> str:
        # find the root folder and store "package.module.Class"
        rel_path_of_current_file = os.path.relpath(self.file.path, self.project_root)
        for _ in range(import_level):
            rel_path_of_current_file = os.path.dirname(rel_path_of_current_file)
        rel_path_of_current_file = rel_path_of_current_file.replace(os.sep, ".")
        return f"{rel_path_of_current_file}.{relative_import}"

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if import_level := getattr(node, "level", 0):
                self.imports.append(
                    self._resolve_relative_import(alias.name, import_level)
                )
            else:
                self.imports.append(alias.name)
                if alias.asname is not None:
                    self.aliases[alias.asname] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if import_level := getattr(node, "level", 0):
            prefix = self._resolve_relative_import(node.module, import_level)
        else:
            prefix = node.module
        for alias in node.names:
            self.imports.append(f"{prefix}.{alias.name}")
            if alias.asname is not None:
                self.aliases[alias.asname] = f"{prefix}.{alias.name}"
            else:
                self.aliases[alias.name] = f"{prefix}.{alias.name}"


def parse_file(path: str, project_root: str, package_name: str) -> ParsedFile:
    parser = FileParser(path, project_root, package_name)
    parser.visit(ast.parse(parser.file.source_code))
    parser.resolve_imports()
    return parser.file


class ParsedProject(BaseModel):
    path: str = Field(description="Project path")
    package_name: str = Field(description="Package name")
    root_folder: Optional[ParsedFolder] = Field(
        default=None, description="Root folder of the project"
    )
    aliases: Dict[str, str] = Field(
        default_factory=dict, description="Dictionary of function and class aliases"
    )
    references: Dict[str, ParsedCodeEntity] = Field(
        default_factory=dict,
        description="Dictionary of function and class references",
        exclude=True,
    )

    def model_post_init(self, _) -> None:
        self.parse_init()
        self.root_folder = self.parse_folder(self.path)
        self.resolve_project_aliases_and_references()

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
                        current_pkg, init_path
                    )
                    if spec and spec.loader:
                        self.execute_and_capture(
                            current_pkg, project_root, current_path, init_path, spec
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
        spec: importlib.machinery.ModuleSpec,
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
            return rel_path.replace(os.sep, ".")

        module = importlib.util.module_from_spec(spec)
        sys.modules[current_pkg] = module
        spec.loader.exec_module(module)

        all_contents = getattr(module, "__all__", [])
        for name in all_contents:
            if item := getattr(module, name, None):
                if module_name := getattr(item, "__module__", None):
                    short_path = f"{_pkg_from_path(path)}.{name}"
                    full_path = f"{module_name}.{name}"
                    self.aliases[short_path] = full_path
                else:
                    logger.warning(
                        f"Warning: {name} in {current_pkg} has no __module__ attribute"
                    )
            else:
                logger.warning(
                    f"Warning: {name} in {current_pkg} is not a valid module"
                )

    def add_file_to_references(self, file: ParsedFile, parsed_suffix: str) -> None:
        self.references[f"{self.package_name}.{parsed_suffix}"] = file
        for function in file.functions:
            self.references[f"{self.package_name}.{parsed_suffix}.{function.name}"] = (
                function
            )
        for class_ in file.classes:
            self.references[f"{self.package_name}.{parsed_suffix}.{class_.name}"] = (
                class_
            )

    def parse_folder(self, path: str):
        folder = ParsedFolder(
            path=path,
        )
        files = os.listdir(path)
        # remove hidden files and pycache
        files = filter(lambda x: not x.startswith("."), files)
        files = filter(lambda x: not x.endswith(".pyc"), files)
        files = filter(lambda x: not x.startswith("__"), files)
        project_root = os.path.dirname(self.path)
        for file in files:
            if os.path.isfile(os.path.join(path, file)):
                if file != "__init__.py":
                    parsed_file = parse_file(
                        os.path.join(path, file), project_root, self.package_name
                    )
                    # Drop the prefix of the project root and the .py suffix
                    parsed_suffix = parsed_file.path.replace(project_root, "")[1:-3]
                    # Drop the folder name so that we may prefix with the package name
                    parsed_suffix = ".".join(parsed_suffix.split("/")[1:])
                    self.add_file_to_references(parsed_file, parsed_suffix)
                    folder.files.append(parsed_file)
            elif os.path.isdir(os.path.join(path, file)):
                parsed_sub_folder = self.parse_folder(os.path.join(path, file))
                folder.subfolders.append(parsed_sub_folder)
        return folder

    def resolve_project_aliases_and_references(self) -> None:
        # starting at the root folder, resolve the aliases
        def _walk_and_map(fn: Callable[[ParsedCodeEntity], None]) -> None:
            queue = [self.root_folder]
            while queue:
                current_folder = queue.pop(0)
                for file in current_folder.files:
                    fn(file)
                for subfolder in current_folder.subfolders:
                    queue.append(subfolder)

        _walk_and_map(self._resolve_file_aliases)
        _walk_and_map(self._resolve_file_references)

    def _resolve_file_aliases(self, file: ParsedFile) -> None:
        def resolve_aliases(deps: List[str]) -> List[str]:
            return [self.aliases.get(d, d) for d in deps]

        for function in file.functions:
            function.dependencies = resolve_aliases(function.dependencies)
        for class_ in file.classes:
            class_.dependencies = resolve_aliases(class_.dependencies)
        file.dependencies = resolve_aliases(file.dependencies)

    def _resolve_file_references(self, file: ParsedFile) -> None:
        def resolve_refs(deps: List[str]) -> Dict[str, ParsedCodeEntity]:
            return {d: self.references[d] for d in deps}

        for function in file.functions:
            function.dependency_refs = resolve_refs(function.dependencies)
        for class_ in file.classes:
            class_.dependency_refs = resolve_refs(class_.dependencies)
        file.dependency_refs = resolve_refs(file.dependencies)


if __name__ == "__main__":
    # Configure basic logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    project = ParsedProject(
        path="tests/parsing/mock/exampleproject/exampleproject",
        package_name="exampleproject",
    )
    print(project.aliases)
