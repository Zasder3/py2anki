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
    
    def parse_function(self, node: ast.FunctionDef) -> ParsedFunction:
        function = ParsedFunction(
            docstring=ast.get_docstring(node),
            source_code=get_source_code(node, self.file.source_code),
            name=node.name,
        )

        # TODO: Parse the function body to find dependencies
        
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
            dependencies.extend(method.dependencies)

        # Handle different types of base class expressions
        parent_classes = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                parent_classes.append(base.id)
            elif isinstance(base, ast.Attribute):
                # Handle nested module access like a.b.ClassA
                parent_classes.append(self._get_attribute_string(base))
            # Add more cases if needed for other expression types

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
    parse_file("tests/parsing/mock/basic.py") 