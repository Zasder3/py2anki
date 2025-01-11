from typing import List, Optional


class CodeEntity:  # Base class
    name: str
    dependencies: List[str]
    docstring: str
    source_code: str
    def find_dependencies(self): ...

class Function(CodeEntity):
    parameters: List[str]
    return_type: Optional[str]

class Class(CodeEntity):
    methods: List[Function]
    attributes: List[str]
    parent_classes: List[str]  # For inheritance

class File(CodeEntity):
    functions: List[Function]
    classes: List[Class]
    imports: List[Function | Class]  # Importing functions or classes