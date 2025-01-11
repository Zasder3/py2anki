import ast
from ast import NodeVisitor

from py2anki.entity import File, Function
from py2anki.parse.utils import get_source_code


class FileParser(NodeVisitor):
    def __init__(self, path: str):
        self.file = File()
        self.file.path = path
    
        with open(path, "r") as f:
            self.file.source_code = f.read()
    
    def parse_function(self, node) -> Function:
        function = Function()
        function.name = node.name
        function.docstring = ast.get_docstring(node)
        function.source_code = get_source_code(node, self.file.source_code)
        function.parameters = [arg.arg for arg in node.args.args]
        function.return_type = node.returns
        
        return function
    
    def visit_FunctionDef(self, node):
        print(ast.dump(node, indent=4))
        if parent := getattr(node, "parent", None):
            print("Printing parent:")
            print(ast.dump(parent, indent=4))
        
        source_code = self.file.source_code.split("\n")[node.lineno - 1:node.end_lineno]
        print("Source code:")
        print("\n".join(source_code))
    
    def visit_ClassDef(self, node):
        print(ast.dump(node, indent=4))
        if parent := getattr(node, "parent", None):
            print("Printing parent:")
            print(ast.dump(parent, indent=4))

def parse_file(path: str) -> File:
    parser = FileParser(path)

    parser.visit(ast.parse(parser.file.source_code))

    return parser.file

    


if __name__ == "__main__":
    parse_file("tests/parsing/mock/basic.py") 