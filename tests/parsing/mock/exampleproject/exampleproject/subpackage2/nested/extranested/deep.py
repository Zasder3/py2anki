"""
Test out . and .. in imports.
"""
from ...bar import B
from ..nest import nest
from .other import other


def deepfn():
    b = B()
    b.foo()
    b.bar()
    nest()
    other()
    return "I'm super deep in here!"
