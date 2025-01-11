class Foo:
    def __init__(self, name: str):
        self.name = name
    
    def say_hello(self) -> str:
        return f"Hello, {self.name}"

def bar(x: int) -> int:
    i = 0
    while x != 1:
        i += 1
        if x % 2 == 0:
            x = x // 2
        else:
            x = 3 * x + 1
    
    return i
