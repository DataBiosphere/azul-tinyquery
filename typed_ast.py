"""A set of AST classes with types and aliases filled in."""

import collections
import compiler


class Select(collections.namedtuple(
        'Select', ['select_fields', 'table', 'where_expr'])):
    """Currently, you can only select directly from table columns."""
    pass


class SelectField(collections.namedtuple('SelectField', ['expr', 'alias'])):
    pass


class TypeContext(collections.namedtuple(
        'TypeContext', ['columns', 'aliases', 'ambig_aliases'])):
    """Defines the types available at a point in code.

    This class is responsible for resolving column names into fully-qualified
    names. For example, if table1 and table2 are joined

    Fields:
        columns: An OrderedDict mapping from column name to type.
        aliases: A dict mapping any allowed aliases to their values. For
            example, the "value" column on a table "table" has full name
            "table.value" but the alias "value" also refers to it (as long as
            there are no other tables with a column named "value").
        ambig_aliases: A set of aliases that cannot be used because they are
            ambiguous. This is used for
    """
    def column_ref_for_name(self, name):
        """Gets the full identifier for a """
        if name in self.columns:
            return ColumnRef(name, self.columns[name])
        elif name in self.aliases:
            full_name = self.aliases[name]
            return ColumnRef(full_name, self.columns[full_name])
        elif name in self.ambig_aliases:
            raise compiler.CompileError('Ambiguous field: {}'.format(name))
        else:
            raise compiler.CompileError('Field not found: {}'.format(name))


class TableExpression(object):
    """Abstract class for all table expression ASTs."""
    def __init__(self):
        assert hasattr(self, 'type_ctx')


class NoTable(collections.namedtuple('NoTable', []), TableExpression):
    @property
    def type_ctx(self):
        return TypeContext(collections.OrderedDict(), {}, [])


class Table(collections.namedtuple('Table', ['name', 'type_ctx'])):
    pass


class Expression(object):
    """Abstract interface for all expression ASTs."""
    def __init__(self, *args):
        assert hasattr(self, 'type')


class FunctionCall(collections.namedtuple(
        'FunctionCall', ['func', 'args', 'type']), Expression):
    """Expression representing a call to a built-in function.

    Fields:
        func: A runtime.Function for the function to call.
        args: A list of expressions to pass in as the function's arguments.
        type: The result type of the expression.
    """


class Literal(collections.namedtuple('Literal', ['value', 'type'])):
    pass


class ColumnRef(collections.namedtuple('ColumnRef', ['column', 'type'])):
    """References a column from the current context."""
