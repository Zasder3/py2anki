import os


class A:
    def foo(self):
        return os.path.join(os.path.dirname(__file__), "bar.py")
