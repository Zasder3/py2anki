import ast
from ast import NodeVisitor

from py2anki.parse.parsed_entities import ParsedClass, ParsedFile, ParsedFunction
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

if __name__ == "__main__":
    file = parse_file("tests/parsing/mock/dependency.py")
    for function in file.functions:
        print(function.name)
        print(function.dependencies)
        print(function.docstring)

    for class_ in file.classes:
        print(class_.name)
        print(class_.dependencies)
        print(class_.docstring)
        for method in class_.methods:
            print(method.name)
            print(method.dependencies)
            print(method.docstring)
