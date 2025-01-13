def base_function():
    """A simple base function with no dependencies."""
    return "I'm a base function"

def helper_function():
    """Another base function used by others."""
    return "I'm a helper"

def dependent_function():
    """Function that depends on base_function."""
    result = base_function()
    return f"Processed: {result}"

def multiple_dependencies():
    """Function with multiple dependencies."""
    first = base_function()
    second = helper_function()
    return f"Combined: {first} and {second}"

def nested_dependency():
    """Function that calls another dependent function."""
    return f"Nested: {dependent_function()}"

class ExampleClass:
    def method_with_dependency(self):
        """Class method that depends on external function."""
        return base_function()

    def internal_dependency(self):
        """Method that depends on another method."""
        return self.method_with_dependency()
