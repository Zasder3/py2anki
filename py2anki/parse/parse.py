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
    
    def parse_function(self, node) -> ParsedFunction:
        function = ParsedFunction(
            docstring=ast.get_docstring(node),
            source_code=get_source_code(node, self.file.source_code),
            name=node.name,
        )

        # TODO: Parse the function body to find dependencies
        
        return function
    
    def visit_FunctionDef(self, node):
        self.file.functions.append(self.parse_function(node))
    
    def visit_ClassDef(self, node):
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

        self.file.classes.append(ParsedClass(
            dependencies=dependencies,
            name=node.name,
            docstring=ast.get_docstring(node),
            source_code=source_code,
            methods=methods,
            parent_classes=[base.id for base in node.bases]
        ))

def parse_file(path: str) -> ParsedFile:
    parser = FileParser(path)

    parser.visit(ast.parse(parser.file.source_code))

    return parser.file

if __name__ == "__main__":
    parse_file("tests/parsing/mock/basic.py") 