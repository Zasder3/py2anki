class Foo:
    name: str

    def __init__(self, name: str):
        self.name = name
    
    def say_hello(self) -> str:
        def _private():
            return "Hello"
        return f"{_private()}, {self.name}"

def bar(x: int) -> int:
    """
    Perform the Collatz conjecture on the input number x.

    Parameters:
        x: The input number
    
    Returns:
        The number of steps it took to reach 1
    """
    i = 0
    while x != 1:
        i += 1
        if x % 2 == 0:
            x = x // 2
        else:
            x = 3 * x + 1
    
    return i
