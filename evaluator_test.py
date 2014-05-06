import collections
import mock
import unittest

import context
import tinyquery
import tq_types


class EvaluatorTest(unittest.TestCase):
    def setUp(self):
        self.tq = tinyquery.TinyQuery()
        self.tq.load_table(tinyquery.Table(
            'test_table',
            5,
            collections.OrderedDict([
                ('val1', context.Column(tq_types.INT, [4, 1, 8, 1, 2])),
                ('val2', context.Column(tq_types.INT, [8, 2, 4, 1, 6]))
            ])))
        self.tq.load_table(tinyquery.Table(
            'test_table_2',
            2,
            collections.OrderedDict([
                ('val3', context.Column(tq_types.INT, [3, 8])),
                ('val2', context.Column(tq_types.INT, [2, 7])),
            ])))
        self.tq.load_table(tinyquery.Table(
            'test_table_3',
            5,
            collections.OrderedDict([
                ('foo', context.Column(tq_types.INT, [1, 2, 4, 5, 1])),
                ('bar', context.Column(tq_types.INT, [2, 7, 3, 1, 1])),
            ])))
        self.tq.load_table(tinyquery.Table(
            'null_table',
            4,
            collections.OrderedDict([
                ('foo', context.Column(tq_types.INT, [1, None, None, 5])),
            ])))
        self.tq.load_table(tinyquery.Table(
            'string_table',
            2,
            collections.OrderedDict([
                ('str', context.Column(tq_types.STRING, ['hello', 'world'])),
            ])))

    def assert_query_result(self, query, expected_result):
        result = self.tq.evaluate_query(query)
        self.assertEqual(expected_result, result)

    def make_context(self, name_type_values_triples):
        num_rows = len(name_type_values_triples[0][2])
        # The constructor does all relevant invariant checks, so we don't have
        # to do that here.
        return context.Context(
            num_rows,
            collections.OrderedDict(
                ((None, name), context.Column(col_type, values))
                for name, col_type, values in name_type_values_triples),
            None)

    def test_select_literal(self):
        self.assert_query_result(
            'SELECT 0',
            self.make_context([('f0_', tq_types.INT, [0])])
        )

    def test_simple_arithmetic(self):
        self.assert_query_result(
            'SELECT 1 + 2',
            self.make_context([('f0_', tq_types.INT, [3])])
        )

    def test_precedence(self):
        self.assert_query_result(
            'SELECT 2 * (3 + 1) + 2 * 3',
            self.make_context([('f0_', tq_types.INT, [14])])
        )

    def test_negative_number(self):
        self.assert_query_result(
            'SELECT -3',
            self.make_context([('f0_', tq_types.INT, [-3])])
        )

    def test_function_calls(self):
        with mock.patch('time.time', lambda: 15):
            self.assert_query_result(
                'SELECT ABS(-2), POW(2, 3), NOW()',
                self.make_context([
                    ('f0_', tq_types.INT, [2]),
                    ('f1_', tq_types.INT, [8]),
                    ('f2_', tq_types.INT, [15000000]),
                ])
            )

    def test_select_from_table(self):
        self.assert_query_result(
            'SELECT val1 FROM test_table',
            self.make_context([('val1', tq_types.INT, [4, 1, 8, 1, 2])])
        )

    def test_select_comparison(self):
        self.assert_query_result(
            'SELECT val1 = val2 FROM test_table',
            self.make_context([
                ('f0_', tq_types.BOOL, [False, False, False, True, False])
            ])
        )

    def test_where(self):
        self.assert_query_result(
            'SELECT val1 + 2 FROM test_table WHERE val2 > 3',
            self.make_context([('f0_', tq_types.INT, [6, 10, 4])])
        )

    def test_multiple_select(self):
        self.assert_query_result(
            'SELECT val1 + 1 foo, val2, val2 * 2'
            'FROM test_table WHERE val1 < 5',
            self.make_context([
                ('foo', tq_types.INT, [5, 2, 2, 3]),
                ('val2', tq_types.INT, [8, 2, 1, 6]),
                ('f0_', tq_types.INT, [16, 4, 2, 12]),
            ])
        )

    def test_simple_aggregate(self):
        self.assert_query_result(
            'SELECT SUM(val1) + MIN(val2) FROM test_table',
            self.make_context([('f0_', tq_types.INT, [17])])
        )

    def test_aggregate_evaluation(self):
        self.assert_query_result(
            'SELECT 2 * SUM(val1 + 1) FROM test_table WHERE val1 < 5',
            self.make_context([('f0_', tq_types.INT, [24])])
        )

    def test_group_by_field(self):
        result = self.tq.evaluate_query(
            'SELECT SUM(val2) FROM test_table GROUP BY val1')
        self.assertEqual([3, 4, 6, 8],
                         sorted(result.columns[(None, 'f0_')].values))

    def test_group_by_used_field(self):
        result = self.tq.evaluate_query(
            'SELECT val1 + SUM(val2) FROM test_table GROUP BY val1')
        self.assertEqual([4, 8, 12, 12],
                         sorted(result.columns[(None, 'f0_')].values))

    def test_group_by_alias(self):
        result = self.tq.evaluate_query(
            'SELECT val1 % 3 AS cat, MAX(val1) FROM test_table GROUP BY cat')
        result_rows = zip(result.columns[(None, 'cat')].values,
                          result.columns[(None, 'f0_')].values)
        self.assertEqual([(1, 4), (2, 8)], sorted(result_rows))

    def test_mixed_group_by(self):
        result = self.tq.evaluate_query(
            'SELECT val2 % 2 AS foo, SUM(val2) AS bar '
            'FROM test_table GROUP BY val1, foo')
        result_rows = zip(result.columns[(None, 'foo')].values,
                          result.columns[(None, 'bar')].values)
        self.assertEqual([(0, 2), (0, 4), (0, 6), (0, 8), (1, 1)],
                         sorted(result_rows))

    def test_select_multiple_tables(self):
        self.assert_query_result(
            'SELECT val1, val2, val3 FROM test_table, test_table_2',
            self.make_context([
                ('val1', tq_types.INT, [4, 1, 8, 1, 2, None, None]),
                ('val2', tq_types.INT, [8, 2, 4, 1, 6, 2, 7]),
                ('val3', tq_types.INT, [None, None, None, None, None, 3, 8]),
            ])
        )

    def test_subquery(self):
        self.assert_query_result(
            'SELECT foo * 2, foo + 1 '
            'FROM (SELECT val1 + val2 AS foo FROM test_table)',
            self.make_context([
                ('f0_', tq_types.INT, [24, 6, 24, 4, 16]),
                ('f1_', tq_types.INT, [13, 4, 13, 3, 9]),
            ])
        )

    def test_fully_qualified_name(self):
        self.assert_query_result(
            'SELECT test_table.val1 FROM test_table',
            self.make_context([
                ('test_table.val1', tq_types.INT, [4, 1, 8, 1, 2])])
        )

    def test_table_alias(self):
        self.assert_query_result(
            'SELECT t.val1 FROM test_table t',
            self.make_context([('t.val1', tq_types.INT, [4, 1, 8, 1, 2])]))

    def test_join(self):
        result = self.tq.evaluate_query(
            'SELECT bar'
            '    FROM test_table JOIN test_table_3'
            '    ON test_table.val1 = test_table_3.foo')
        result_rows = result.columns[(None, 'bar')].values
        # Four results for the 1 key, then one each for 2 and 4.
        self.assertEqual([1, 1, 2, 2, 3, 7], sorted(result_rows))

    def test_multiple_join(self):
        result = self.tq.evaluate_query(
            'SELECT foo, bar'
            '    FROM test_table t1 JOIN test_table_3 t2'
            '    ON t1.val1 = t2.foo AND t2.bar = t1.val2')
        result_rows = zip(result.columns[(None, 'foo')].values,
                          result.columns[(None, 'bar')].values)
        self.assertEqual([(1, 1), (1, 2)], sorted(result_rows))

    def test_null_comparisons(self):
        self.assert_query_result(
            'SELECT foo IS NULL, foo IS NOT NULL FROM null_table',
            self.make_context([
                ('f0_', tq_types.BOOL, [False, True, True, False]),
                ('f1_', tq_types.BOOL, [True, False, False, True]),
            ]))

    def test_string_comparison(self):
        self.assert_query_result(
            'SELECT str = "hello" FROM string_table',
            self.make_context([
                ('f0_', tq_types.BOOL, [True, False])]))

    def test_boolean_literals(self):
        self.assert_query_result(
            'SELECT false OR true',
            self.make_context([
                ('f0_', tq_types.BOOL, [True])
            ])
        )

    def test_null_literal(self):
        self.assert_query_result(
            'SELECT NULL IS NULL',
            self.make_context([
                ('f0_', tq_types.BOOL, [True])
            ])
        )

    def test_in_literals(self):
        self.assert_query_result(
            'SELECT 2 IN (1, 2, 3), 4 in (1, 2, 3)',
            self.make_context([
                ('f0_', tq_types.BOOL, [True]),
                ('f1_', tq_types.BOOL, [False]),
            ])
        )

    def test_if(self):
        self.assert_query_result(
            'SELECT IF(val1 % 2 = 0, "a", "b") FROM test_table',
            self.make_context([
                ('f0_', tq_types.STRING, ['a', 'b', 'a', 'b', 'a'])
            ]))

    def test_join_subquery(self):
        self.assert_query_result(
            'SELECT t2.val '
            'FROM test_table t1 JOIN (SELECT 1 AS val) t2 ON t1.val1 = t2.val',
            self.make_context([
                ('t2.val', tq_types.INT, [1, 1])
            ])
        )

    def test_count(self):
        self.assert_query_result(
            'SELECT COUNT(1) FROM test_table WHERE val1 = 1',
            self.make_context([
                ('f0_', tq_types.INT, [2])]))

    def test_count_distinct(self):
        self.assert_query_result(
            'SELECT COUNT(DISTINCT val1) FROM test_table',
            self.make_context([
                ('f0_', tq_types.INT, [4])
            ]))

    def test_count_star(self):
        self.assert_query_result(
            'SELECT COUNT(foo), COUNT(*) FROM null_table',
            self.make_context([
                ('f0_', tq_types.INT, [2]),
                ('f1_', tq_types.INT, [4]),
            ])
        )

    def test_select_star_from_table(self):
        self.assert_query_result(
            'SELECT * FROM test_table_3',
            self.make_context([
                ('foo', tq_types.INT, [1, 2, 4, 5, 1]),
                ('bar', tq_types.INT, [2, 7, 3, 1, 1])
            ])
        )

    def test_select_star_from_join(self):
        self.assert_query_result(
            'SELECT * '
            'FROM test_table t1 JOIN test_table_2 t2 ON t1.val1 = t2.val3',
            self.make_context([
                ('t1.val1', tq_types.INT, [8]),
                ('t1.val2', tq_types.INT, [4]),
                ('t2.val3', tq_types.INT, [8]),
                ('t2.val2', tq_types.INT, [7])
            ])
        )
