"""Implementation of the standard built-in functions."""
import abc
import tq_types

class Function(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def check_types(self, *arg_types):
        """Return the type of the result as a function of the arg types.

        Raises a SyntaxError if the types are disallowed.
        """

    @abc.abstractmethod
    def evaluate(self, *args):
        """Evaluates the function itself."""


class ArithmeticOperator(Function):
    """Basic operators like +."""
    def __init__(self, func):
        self.func = func

    def check_types(self, type1, type2):
        # TODO: Fail if types are wrong.
        return tq_types.INT

    def evaluate(self, arg1, arg2):
        return self.func(arg1, arg2)


class ComparisonOperator(Function):
    def __init__(self, func):
        self.func = func

    def check_types(self, type1, type2):
        # TODO: Fail if types are wrong.
        return tq_types.BOOL

    def evaluate(self, arg1, arg2):
        return self.func(arg1, arg2)


class UnaryIntOperator(Function):
    def __init__(self, func):
        self.func = func

    def check_types(self, arg):
        assert arg == tq_types.INT
        return tq_types.INT

    def evaluate(self, arg):
        return self.func(arg)


_UNARY_OPERATORS = {
    '-': UnaryIntOperator(lambda a: -a)
}


_BINARY_OPERATORS = {
    '+': ArithmeticOperator(lambda a, b: a + b),
    '-': ArithmeticOperator(lambda a, b: a - b),
    '*': ArithmeticOperator(lambda a, b: a * b),
    '/': ArithmeticOperator(lambda a, b: a / b),
    '%': ArithmeticOperator(lambda a, b: a % b),
    '=': ComparisonOperator(lambda a, b: a == b),
    '!=': ComparisonOperator(lambda a, b: a != b),
    '>': ComparisonOperator(lambda a, b: a > b),
    '<': ComparisonOperator(lambda a, b: a < b),
    '>=': ComparisonOperator(lambda a, b: a >= b),
    '<=': ComparisonOperator(lambda a, b: a <= b),
}


def get_unary_op(name):
    result = _UNARY_OPERATORS[name]
    assert isinstance(result, Function)
    return result


def get_binary_op(name):
    result = _BINARY_OPERATORS[name]
    assert isinstance(result, Function)
    return result
