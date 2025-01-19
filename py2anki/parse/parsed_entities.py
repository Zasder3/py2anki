import logging
from typing import List, Optional, Type

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

class ParsedCodeEntity(BaseModel):  # Base class
    dependencies: List[str] = Field(
        default_factory=list,
        description="List of dependencies"
    )
    docstring: Optional[str] = Field(
        default=None,
        description="Documentation string"
    )
    source_code: str = Field(description="Source code of the entity")

    @field_validator('dependencies')
    @classmethod
    def ensure_unique(cls: Type['ParsedCodeEntity'], v: List[str]) -> List[str]:
        return list(dict.fromkeys(v))


class ParsedFunction(ParsedCodeEntity):
    name: str = Field(description="Function name")


class ParsedClass(ParsedCodeEntity):
    name: str = Field(description="Class name")
    methods: List[ParsedFunction] = Field(
        default_factory=list,
        description="List of class methods"
    )
    parent_classes: List[str] = Field(
        default_factory=list,
        description="List of parent classes"
    )


class ParsedFile(ParsedCodeEntity):
    path: str = Field(description="File path")
    functions: List[ParsedFunction] = Field(
        default_factory=list,
        description="List of functions in the file"
    )
    classes: List[ParsedClass] = Field(
        default_factory=list,
        description="List of classes in the file"
    )
    imports: List[ParsedFunction | ParsedClass] = Field(
        default_factory=list,
        description="List of imported functions or classes"
    )

class ParsedFolder(BaseModel):
    path: str = Field(description="File path")
    files: List['ParsedFile'] = Field(
        default_factory=list,
        description="List of files in the folder"
    )
    subfolders: List['ParsedFolder'] = Field(
        default_factory=list,
        description="List of subfolders"
    )

