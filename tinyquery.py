"""Implementation of the TinyQuery service."""
import collections
import itertools

import compiler
import type_context
import typed_ast


class TinyQuery(object):
    def __init__(self):
        self.tables_by_name = {}

    def load_table(self, table):
        """Create a table.

        Arguments:
            name: The name of the table.
            data: A dict mapping column name to list of values.
        """
        self.tables_by_name[table.name] = table

    def get_all_tables(self):
        return self.tables_by_name

    def evaluate_query(self, query):
        select_ast = compiler.compile_text(query, self.tables_by_name)
        return self.evaluate_select(select_ast)

    def evaluate_select(self, select_ast):
        """Given a select statement, return a Context with the results."""
        assert isinstance(select_ast, typed_ast.Select)

        table_context = self.evaluate_table_expr(select_ast.table)
        mask_column = self.evaluate_expr(select_ast.where_expr, table_context)
        select_context = mask_context(table_context, mask_column)

        if select_ast.group_set is not None:
            return self.evaluate_groups(
                select_ast.select_fields, select_ast.group_set, select_context)
        else:
            return self.evaluate_select_fields(
                select_ast.select_fields, select_context)

    def evaluate_groups(self, select_fields, group_set, select_context):
        """Evaluate a list of select fields, grouping by some of the values.

        Arguments:
            select_fields: A list of SelectField instances to evaluate.
            group_set: The groups (either fields in select_context or aliases
                referring to an element of select_fields) to group by.
            select_context: A context with the data that the select statement
                has access to.

        Returns:
            A context with the results.
        """
        field_groups = group_set.field_groups
        alias_groups = group_set.alias_groups
        alias_group_list = sorted(alias_groups)

        group_key_select_fields = [
            f for f in select_fields if f.alias in alias_groups]
        aggregate_select_fields = [
            f for f in select_fields if f.alias not in alias_groups]

        alias_group_result_context = self.evaluate_select_fields(
            group_key_select_fields, select_context)

        # Dictionary mapping (singleton) group key context to the context of
        # values for that key.
        group_contexts = {}
        # TODO: Seems pretty ugly and wasteful to use a whole context as a
        # group key.
        for i in xrange(select_context.num_rows):
            key = self.get_group_key(
                field_groups, alias_group_list, select_context,
                alias_group_result_context, i)
            if key not in group_contexts:
                new_group_context = empty_context_from_template(select_context)
                group_contexts[key] = new_group_context
            group_context = group_contexts[key]
            append_row_to_context(src_context=select_context, index=i,
                                  dest_context=group_context)

        result_context = self.empty_context_from_select_fields(select_fields)
        result_col_names = [field.alias for field in select_fields]
        for context_key, group_context in group_contexts.iteritems():
            group_eval_context = Context(1, context_key.columns, group_context)
            group_aggregate_result_context = self.evaluate_select_fields(
                aggregate_select_fields, group_eval_context)
            full_result_row_context = self.merge_contexts_for_select_fields(
                result_col_names, group_aggregate_result_context, context_key)
            append_row_to_context(full_result_row_context, 0, result_context)
        return result_context

    def merge_contexts_for_select_fields(self, col_names, context1, context2):
        """Build a context that combines columns of two contexts.

        The col_names argument is a list of strings that specifies the order of
        the columns in the result. Note that not every column must be used, and
        columns in context1 take precedence over context2 (this happens in
        practice with non-alias groups that are part of the group key).
        """
        assert context1.num_rows == context2.num_rows
        assert context1.aggregate_context is None
        assert context2.aggregate_context is None
        columns1, columns2 = context1.columns, context2.columns
        return Context(context1.num_rows, collections.OrderedDict(
            (col_name, columns1.get(col_name) or columns2[col_name])
            for col_name in col_names
        ), None)

    def get_group_key(self, field_groups, alias_groups, select_context,
                      alias_group_result_context, index):
        """Computes a singleton context with the values for a group key.

        The evaluation has already been done; this method just selects the
        values out of the right contexts.
        """
        result_columns = collections.OrderedDict()
        for field_group in field_groups:
            column_name = field_group.column
            source_column = select_context.columns[column_name]
            result_columns[column_name] = Column(
                source_column.type, [source_column.values[index]])
        for alias_group in alias_groups:
            column_name = alias_group
            source_column = alias_group_result_context.columns[column_name]
            result_columns[column_name] = Column(
                source_column.type, [source_column.values[index]])
        return Context(1, result_columns, None)


    def empty_context_from_select_fields(self, select_fields):
        return Context(
            0,
            collections.OrderedDict(
                (select_field.alias, Column(select_field.expr.type, []))
                for select_field in select_fields
            ),
            None)

    def evaluate_select_fields(self, select_fields, context):
        """Evaluate a table result given the data the fields have access to.

        Arguments:
            select_fields: A list of typed_ast.SelectField values to evaluate.
            context: The "source" context that the expressions can access when
                being evaluated.
        """
        return Context(context.num_rows,
                       collections.OrderedDict(
                           self.evaluate_select_field(select_field, context)
                           for select_field in select_fields),
                       None)

    def evaluate_select_field(self, select_field, context):
        """Given a typed select field, return a resulting name and Column."""
        assert isinstance(select_field, typed_ast.SelectField)
        results = self.evaluate_expr(select_field.expr, context)
        return select_field.alias, Column(select_field.expr.type, results)

    def evaluate_table_expr(self, table_expr):
        """Given a table expression, return a Context with its values."""
        try:
            method = getattr(self,
                             'eval_table_' + table_expr.__class__.__name__)
        except AttributeError:
            raise NotImplementedError(
                'Missing handler for table type {}'.format(
                    table_expr.__class__.__name__))
        return method(table_expr)

    def eval_table_NoTable(self, table_expr):
        # If the user isn't selecting from any tables, just specify that there
        # is one column to return and no table accessible.
        return Context(1, collections.OrderedDict(), None)

    def eval_table_Table(self, table_expr):
        """Get the values from the table.

        The type context in the table expression determines the actual column
        names to output, since that accounts for any alias on the table.
        """
        table = self.tables_by_name[table_expr.name]
        return context_from_table(table, table_expr.type_ctx)

    def eval_table_TableUnion(self, table_expr):
        result_context = empty_context_from_type_context(table_expr.type_ctx)
        for table in table_expr.tables:
            table_result = self.evaluate_table_expr(table)
            append_partial_context_to_context(table_result, result_context)
        return result_context

    def eval_table_Select(self, table_expr):
        return self.evaluate_select(table_expr)

    def evaluate_expr(self, expr, context):
        """Computes the raw data for the output column for the expression."""
        try:
            method = getattr(self, 'evaluate_' + expr.__class__.__name__)
        except AttributeError:
            raise NotImplementedError(
                'Missing handler for type {}'.format(expr.__class__.__name__))
        return method(expr, context)

    def evaluate_FunctionCall(self, func_call, context):
        arg_results = [self.evaluate_expr(arg, context)
                       for arg in func_call.args]
        return func_call.func.evaluate(context.num_rows, *arg_results)

    def evaluate_AggregateFunctionCall(self, func_call, context):
        # Switch to the aggregate context when evaluating the arguments to the
        # aggregate.
        assert context.aggregate_context is not None, (
            'Aggregate function called without a valid aggregate context.')
        arg_results = [self.evaluate_expr(arg, context.aggregate_context)
                       for arg in func_call.args]
        return func_call.func.evaluate(context.num_rows, *arg_results)

    def evaluate_Literal(self, literal, context):
        return [literal.value for _ in xrange(context.num_rows)]

    def evaluate_ColumnRef(self, column_ref, context):
        column = context.columns[column_ref.column]
        return column.values


class Table(collections.namedtuple('Table', ['name', 'num_rows', 'columns'])):
    """Information containing metadata and contents of a table.

    Fields:
        columns: A dict mapping column name to column.
    """
    def __init__(self, name, num_rows, columns):
        assert isinstance(columns, collections.OrderedDict)
        for name, column in columns.iteritems():
            assert len(column.values) == num_rows, (
                'Column %s had %s rows, expected %s.' % (
                    name, len(column.values), num_rows))
        super(Table, self).__init__()


class Context(object):
    """Represents the columns accessible when evaluating an expression.

    Fields:
        num_rows: The number of rows for all columns in this context.
        columns: An OrderedDict from column name to Column.
        aggregate_context: Either None, indicating that aggregate functions
            aren't allowed, or another Context to use whenever we enter into an
            aggregate function.
    """
    def __init__(self, num_rows, columns, aggregate_context):
        assert isinstance(columns, collections.OrderedDict)
        for name, column in columns.iteritems():
            assert len(column.values) == num_rows, (
                'Column %s had %s rows, expected %s.' % (
                    name, len(column.values), num_rows))
        if aggregate_context is not None:
            assert isinstance(aggregate_context, Context)
        self.num_rows = num_rows
        self.columns = columns
        self.aggregate_context = aggregate_context

    def __repr__(self):
        return 'Context({}, {}, {})'.format(self.num_rows, self.columns,
                                            self.aggregate_context)

    def __eq__(self, other):
        return ((self.num_rows, self.columns, self.aggregate_context) ==
                other.num_rows, other.columns, other.aggregate_context)

    def __hash__(self):
        return hash((
            self.num_rows,
            tuple(tuple(column.values) for column in self.columns.values()),
            self.aggregate_context))


class Column(collections.namedtuple('Column', ['type', 'values'])):
    """Represents a single column of data.

    Fields:
        type: A constant from the tq_types module.
        values: A list of raw values for the column contents.
    """


def context_from_table(table, type_context):
    """Given a table and a type context, build a context with those values.

    The order of the columns in the type context must match the order of the
    columns in the table.
    """
    any_column = table.columns.itervalues().next()
    new_columns = collections.OrderedDict([
        (column_name, column)
        for (column_name, column) in zip(type_context.columns.iterkeys(),
                                         table.columns.itervalues())
    ])
    return Context(len(any_column.values), new_columns, None)


def empty_context_from_type_context(type_context):
    assert type_context.aggregate_context is None
    result_columns = collections.OrderedDict(
        (col_name, Column(col_type, []))
        for col_name, col_type in type_context.columns.iteritems()
    )
    return Context(0, result_columns, None)


def mask_context(context, mask):
    """Apply a row filter to a given context.

    Arguments:
        context: A Context to filter.
        mask: A column of type bool. Each row in this column should be True if
            the row should be kept for the whole context and False otherwise.
    """
    assert context.aggregate_context is None, (
        'Cannot mask a context with an aggregate context.')
    new_columns = collections.OrderedDict([
        (column_name,
         Column(column.type, list(itertools.compress(column.values, mask))))
        for (column_name, column) in context.columns.iteritems()
    ])
    return Context(sum(mask), new_columns, None)


def empty_context_from_template(context):
    """Returns a new context that has the same columns as the given context."""
    return Context(num_rows=0,
                   columns=collections.OrderedDict(
                       (name, empty_column_from_template(column))
                       for name, column in context.columns.iteritems()
                   ),
                   aggregate_context=None)


def empty_column_from_template(column):
    """Returns a new empty column with the same type as the given one."""
    return Column(column.type, [])


def append_row_to_context(src_context, index, dest_context):
    """Take row i from src_context and append it to dest_context.

    The schemas of the two contexts must match.
    """
    dest_context.num_rows += 1
    for name, column in dest_context.columns.iteritems():
        column.values.append(src_context.columns[name].values[index])


def append_partial_context_to_context(src_context, dest_context):
    """Modifies dest_context to include all rows in src_context.

    The schemas don't need to match exactly; src_context just needs to have a
    subset, and all other columns will be given a null value.

    Also, it is assumed that the destination context only uses short column
    names rather than fully-qualified names.
    """
    dest_context.num_rows += src_context.num_rows
    # Ignore fully-qualified names for this operation.
    short_named_src_column_values = {
        type_context.TypeContext.short_column_name(col_name): column.values
        for col_name, column in src_context.columns.iteritems()}

    for col_name, dest_column in dest_context.columns.iteritems():
        src_column_values = short_named_src_column_values.get(col_name)
        if src_column_values is None:
            dest_column.values.extend([None] * src_context.num_rows)
        else:
            dest_column.values.extend(src_column_values)
