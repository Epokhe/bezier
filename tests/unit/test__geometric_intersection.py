# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import unittest.mock

import numpy as np
import six

from tests import utils as base_utils
from tests.unit import utils


SPACING = np.spacing  # pylint: disable=no-member
UNIT_SQUARE = np.asfortranarray([
    [0.0, 0.0],
    [1.0, 0.0],
    [1.0, 1.0],
    [0.0, 1.0],
])


class Test__bbox_intersect(unittest.TestCase):

    @staticmethod
    def _call_function_under_test(nodes1, nodes2):
        from bezier import _geometric_intersection

        return _geometric_intersection._bbox_intersect(nodes1, nodes2)

    def test_intersect(self):
        from bezier import _geometric_intersection

        nodes = UNIT_SQUARE + np.asfortranarray([[0.5, 0.5]])
        result = self._call_function_under_test(UNIT_SQUARE, nodes)
        expected = _geometric_intersection.BoxIntersectionType.INTERSECTION
        self.assertEqual(result, expected)

    def test_far_apart(self):
        from bezier import _geometric_intersection

        nodes = UNIT_SQUARE + np.asfortranarray([[100.0, 100.0]])
        result = self._call_function_under_test(UNIT_SQUARE, nodes)
        expected = _geometric_intersection.BoxIntersectionType.DISJOINT
        self.assertEqual(result, expected)

    def test_disjoint_but_aligned(self):
        from bezier import _geometric_intersection

        nodes = UNIT_SQUARE + np.asfortranarray([[1.0, 2.0]])
        result = self._call_function_under_test(UNIT_SQUARE, nodes)
        expected = _geometric_intersection.BoxIntersectionType.DISJOINT
        self.assertEqual(result, expected)

    def test_tangent(self):
        from bezier import _geometric_intersection

        nodes = UNIT_SQUARE + np.asfortranarray([[1.0, 0.0]])
        result = self._call_function_under_test(UNIT_SQUARE, nodes)
        expected = _geometric_intersection.BoxIntersectionType.TANGENT
        self.assertEqual(result, expected)

    def test_almost_tangent(self):
        from bezier import _geometric_intersection

        x_val = 1.0 + SPACING(1.0)
        nodes = UNIT_SQUARE + np.asfortranarray([[x_val, 0.0]])
        result = self._call_function_under_test(UNIT_SQUARE, nodes)
        expected = _geometric_intersection.BoxIntersectionType.DISJOINT
        self.assertEqual(result, expected)


@utils.needs_curve_intersection_speedup
class Test_speedup_bbox_intersect(Test__bbox_intersect):

    @staticmethod
    def _call_function_under_test(nodes1, nodes2):
        from bezier import _curve_intersection_speedup

        return _curve_intersection_speedup.bbox_intersect(nodes1, nodes2)


class Test__linearization_error(unittest.TestCase):

    @staticmethod
    def _call_function_under_test(nodes):
        from bezier import _geometric_intersection

        return _geometric_intersection._linearization_error(nodes)

    def test_linear(self):
        nodes = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 2.0],
        ])
        error_val = self._call_function_under_test(nodes)
        self.assertEqual(error_val, 0.0)

    def test_degree_elevated_linear(self):
        nodes = np.asfortranarray([
            [0.0, 0.0],
            [0.5, 1.0],
            [1.0, 2.0],
        ])
        error_val = self._call_function_under_test(nodes)
        self.assertEqual(error_val, 0.0)

        nodes = np.asfortranarray([
            [0.0, 0.0],
            [0.25, 0.5],
            [0.5, 1.0],
            [0.75, 1.5],
            [1.0, 2.0],
        ])
        error_val = self._call_function_under_test(nodes)
        self.assertEqual(error_val, 0.0)

    def test_hidden_linear(self):
        # NOTE: This is the line 3 y = 4 x, but with the parameterization
        #       x(s) = 3 s (4 - 3 s).
        nodes = np.asfortranarray([
            [0.0, 0.0],
            [6.0, 8.0],
            [3.0, 4.0],
        ])
        error_val = self._call_function_under_test(nodes)
        # D^2 v = [-9, -12]
        expected = 0.125 * 2 * 1 * 15.0
        self.assertEqual(error_val, expected)

    def test_quadratic(self):
        from bezier import _curve_helpers

        nodes = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
            [5.0, 6.0],
        ])
        # NOTE: This is hand picked so that
        #             d Nodes = [1, 1], [4, 5]
        #           d^2 Nodes = [3, 4]
        #       so that sqrt(3^2 + 4^2) = 5.0
        error_val = self._call_function_under_test(nodes)
        expected = 0.125 * 2 * 1 * 5.0
        self.assertEqual(error_val, expected)

        # For a degree two curve, the 2nd derivative is constant
        # so by subdividing, our error should drop by a factor
        # of (1/2)^2 = 4.
        left_nodes, right_nodes = _curve_helpers.subdivide_nodes(nodes)
        error_left = self._call_function_under_test(left_nodes)
        error_right = self._call_function_under_test(right_nodes)
        self.assertEqual(error_left, 0.25 * expected)
        self.assertEqual(error_right, 0.25 * expected)

    def test_higher_dimension(self):
        nodes = np.asfortranarray([
            [1.5, 0.0, 6.25],
            [3.5, -5.0, 10.25],
            [8.5, 2.0, 10.25],
        ])
        # NOTE: This is hand picked so that
        #             d Nodes = [2, -5, 4], [5, 7, 0]
        #           d^2 Nodes = [3, 12, -4]
        #       so that sqrt(3^2 + 12^2 + 4^2) = 13.0
        error_val = self._call_function_under_test(nodes)
        expected = 0.125 * 2 * 1 * 13.0
        self.assertEqual(error_val, expected)

    def test_hidden_quadratic(self):
        # NOTE: This is the quadratic y = 1 + x^2 / 4, but with the
        #       parameterization x(s) = (3 s - 1)^2.
        nodes = np.asfortranarray([
            [1.0, 1.25],
            [-0.5, 0.5],
            [-0.5, 2.0],
            [1.0, -1.0],
            [4.0, 5.0],
        ])
        error_val = self._call_function_under_test(nodes)
        # D^2 v = [1.5, 2.25], [1.5, -4.5], [1.5, 9]
        expected = 0.125 * 4 * 3 * np.sqrt(1.5**2 + 9.0**2)
        local_eps = abs(SPACING(expected))
        self.assertAlmostEqual(error_val, expected, delta=local_eps)

    def test_cubic(self):
        nodes = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
            [5.0, 6.0],
            [6.0, 7.0],
        ])
        # NOTE: This is hand picked so that
        #             d Nodes = [1, 1], [4, 5], [1, 1]
        #           d^2 Nodes = [3, 4], [-3, -4]
        #       so that sqrt(3^2 + 4^2) = 5.0
        error_val = self._call_function_under_test(nodes)
        expected = 0.125 * 3 * 2 * 5.0
        self.assertEqual(error_val, expected)

    def test_quartic(self):
        nodes = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
            [5.0, 6.0],
            [6.0, 7.0],
            [4.0, 7.0],
        ])
        # NOTE: This is hand picked so that
        #             d Nodes = [1, 1], [4, 5], [1, 1], [-2, 0]
        #           d^2 Nodes = [3, 4], [-3, -4], [-3, -1]
        #       so that sqrt(3^2 + 4^2) = 5.0
        error_val = self._call_function_under_test(nodes)
        expected = 0.125 * 4 * 3 * 5.0
        self.assertEqual(error_val, expected)

    def test_degree_weights_on_the_fly(self):
        nodes = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
            [7.0, 3.0],
            [11.0, 8.0],
            [15.0, 1.0],
            [16.0, -3.0],
        ])
        # NOTE: This is hand picked so that
        #             d Nodes = [1, 1], [6, 2], [4, 5], [4, -7], [1, -4]
        #           d^2 Nodes = [5, 1], [-2, 3], [0, -12], [-3, 3]
        #       so that sqrt(5^2 + 12^2) = 13.0
        error_val = self._call_function_under_test(nodes)
        expected = 0.125 * 5 * 4 * 13.0
        self.assertEqual(error_val, expected)


@utils.needs_curve_intersection_speedup
class Test_speedup_linearization_error(Test__linearization_error):

    @staticmethod
    def _call_function_under_test(nodes):
        from bezier import _curve_intersection_speedup

        return _curve_intersection_speedup.linearization_error(nodes)


class Test__segment_intersection(unittest.TestCase):

    @staticmethod
    def _call_function_under_test(start0, end0, start1, end1):
        from bezier import _geometric_intersection

        return _geometric_intersection._segment_intersection(
            start0, end0, start1, end1)

    def _helper(self, intersection, s_val, direction0,
                t_val, direction1, **kwargs):
        start0 = intersection + s_val * direction0
        end0 = intersection + (s_val - 1.0) * direction0
        start1 = intersection + t_val * direction1
        end1 = intersection + (t_val - 1.0) * direction1

        return self._call_function_under_test(
            start0, end0, start1, end1, **kwargs)

    def test_success(self):
        intersection = np.asfortranarray([[1.0, 2.0]])
        s_val = 0.25
        t_val = 0.625
        direction0 = np.asfortranarray([[3.0, 0.5]])
        direction1 = np.asfortranarray([[-2.0, 1.0]])
        # D0 x D1 == 4.0, so there will be no round-off in answer.
        computed_s, computed_t, success = self._helper(
            intersection, s_val, direction0, t_val, direction1)

        self.assertEqual(computed_s, s_val)
        self.assertEqual(computed_t, t_val)
        self.assertTrue(success)

    def test_parallel(self):
        intersection = np.asfortranarray([[0.0, 0.0]])
        s_val = 0.5
        t_val = 0.5
        direction0 = np.asfortranarray([[0.0, 1.0]])
        direction1 = np.asfortranarray([[0.0, 2.0]])
        computed_s, computed_t, success = self._helper(
            intersection, s_val,
            direction0, t_val, direction1)

        self.assertIsNone(computed_s)
        self.assertIsNone(computed_t)
        self.assertFalse(success)


@utils.needs_curve_intersection_speedup
class Test_speedup_segment_intersection(Test__segment_intersection):

    @staticmethod
    def _call_function_under_test(start0, end0, start1, end1):
        from bezier import _curve_intersection_speedup

        return _curve_intersection_speedup.segment_intersection(
            start0, end0, start1, end1)


class Test__parallel_different(unittest.TestCase):

    @staticmethod
    def _call_function_under_test(start0, end0, start1, end1):
        from bezier import _geometric_intersection

        return _geometric_intersection._parallel_different(
            start0, end0, start1, end1)

    def test_same_line_no_overlap(self):
        start0 = np.asfortranarray([[0.0, 0.0]])
        end0 = np.asfortranarray([[3.0, 4.0]])
        start1 = np.asfortranarray([[6.0, 8.0]])
        end1 = np.asfortranarray([[9.0, 12.0]])
        self.assertTrue(
            self._call_function_under_test(start0, end0, start1, end1))

    def test_same_line_overlap_at_start(self):
        start0 = np.asfortranarray([[6.0, -3.0]])
        end0 = np.asfortranarray([[-7.0, 1.0]])
        start1 = np.asfortranarray([[1.125, -1.5]])
        end1 = np.asfortranarray([[-5.375, 0.5]])
        self.assertFalse(
            self._call_function_under_test(start0, end0, start1, end1))

    def test_same_line_overlap_at_end(self):
        start0 = np.asfortranarray([[1.0, 2.0]])
        end0 = np.asfortranarray([[3.0, 5.0]])
        start1 = np.asfortranarray([[-0.5, -0.25]])
        end1 = np.asfortranarray([[2.0, 3.5]])
        self.assertFalse(
            self._call_function_under_test(start0, end0, start1, end1))

    def test_same_line_contained(self):
        start0 = np.asfortranarray([[-9.0, 0.0]])
        end0 = np.asfortranarray([[4.0, 5.0]])
        start1 = np.asfortranarray([[23.5, 12.5]])
        end1 = np.asfortranarray([[-25.25, -6.25]])
        self.assertFalse(
            self._call_function_under_test(start0, end0, start1, end1))

    def test_different_line(self):
        start0 = np.asfortranarray([[3.0, 2.0]])
        end0 = np.asfortranarray([[3.0, 0.75]])
        start1 = np.asfortranarray([[0.0, 0.0]])
        end1 = np.asfortranarray([[0.0, 2.0]])
        self.assertTrue(
            self._call_function_under_test(start0, end0, start1, end1))


@utils.needs_curve_intersection_speedup
class Test_speedup_parallel_different(Test__parallel_different):

    @staticmethod
    def _call_function_under_test(start0, end0, start1, end1):
        from bezier import _curve_intersection_speedup

        return _curve_intersection_speedup.parallel_different(
            start0, end0, start1, end1)


class Test_wiggle_pair(unittest.TestCase):

    @staticmethod
    def _call_function_under_test(s_val, t_val):
        from bezier import _geometric_intersection

        return _geometric_intersection.wiggle_pair(s_val, t_val)

    def test_success(self):
        s_val = float.fromhex('-0x1.fffffffffffffp-46')
        t_val = 0.75
        new_s, new_t = self._call_function_under_test(s_val, t_val)
        self.assertEqual(new_s, 0.0)
        self.assertEqual(new_t, t_val)

    def test_failure(self):
        with self.assertRaises(ValueError):
            self._call_function_under_test(-0.5, 0.5)


class Test__from_linearized_low_level(utils.NumPyTestCase):

    # pylint: disable=too-many-arguments
    @staticmethod
    def _call_function_under_test(
            error1, start1, end1, start_node1, end_node1, nodes1,
            error2, start2, end2, start_node2, end_node2, nodes2):
        from bezier import _geometric_intersection

        return _geometric_intersection._from_linearized_low_level(
            error1, start1, end1, start_node1, end_node1, nodes1,
            error2, start2, end2, start_node2, end_node2, nodes2)
    # pylint: enable=too-many-arguments

    def test_it(self):
        start_node1 = np.asfortranarray([[0.0, 0.0]])
        end_node1 = np.asfortranarray([[1.0, 1.0]])
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [0.5, 1.0],
            [1.0, 1.0],
        ])
        # NOTE: This curve isn't close to linear, but that's OK.
        error1 = np.nan

        start_node2 = np.asfortranarray([[0.0, 1.0]])
        end_node2 = np.asfortranarray([[1.0, 0.0]])
        nodes2 = np.asfortranarray([
            [0.0, 1.0],
            [0.5, 1.0],
            [1.0, 0.0],
        ])
        # NOTE: This curve isn't close to linear, but that's OK.
        error2 = np.nan

        refined_s, refined_t, success = self._call_function_under_test(
            error1, 0.0, 1.0, start_node1, end_node1, nodes1,
            error2, 0.0, 1.0, start_node2, end_node2, nodes2)
        self.assertTrue(success)
        self.assertEqual(refined_s, 0.5)
        self.assertEqual(refined_t, 0.5)

    def _no_intersect_help(self, swap=False):
        # The bounding boxes intersect but the lines do not.
        start_node1 = np.asfortranarray([[0.0, 0.0]])
        end_node1 = np.asfortranarray([[1.0, 1.0]])
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
        ])
        error1 = 0.0
        args1 = (error1, 0.0, 1.0, start_node1, end_node1, nodes1)

        start_node2 = np.asfortranarray([[1.75, -0.75]])
        end_node2 = np.asfortranarray([[0.75, 0.25]])
        nodes2 = np.asfortranarray([
            [1.75, -0.75],
            [0.75, 0.25],
        ])
        error2 = 0.0
        args2 = (error2, 0.0, 1.0, start_node2, end_node2, nodes2)

        if swap:
            args1, args2 = args2, args1

        args = args1 + args2
        _, _, success = self._call_function_under_test(*args)
        self.assertFalse(success)

    def test_no_intersection_bad_t(self):
        self._no_intersect_help()

    def test_no_intersection_bad_s(self):
        self._no_intersect_help(swap=True)

    def _no_intersect_help_non_line(self, swap=False):
        # The bounding boxes intersect but the lines do not.
        start_node1 = np.asfortranarray([[0.0, 0.0]])
        end_node1 = np.asfortranarray([[1.0, 1.0]])
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [0.5, 0.0],
            [1.0, 1.0],
        ])
        error1 = 0.25
        args1 = (error1, 0.0, 1.0, start_node1, end_node1, nodes1)

        start_node2 = np.asfortranarray([[1.75, -0.75]])
        end_node2 = np.asfortranarray([[0.75, 0.25]])
        nodes2 = np.asfortranarray([
            [1.75, -0.75],
            [1.25, -0.75],
            [0.75, 0.25],
        ])
        error2 = 0.25
        args2 = (error2, 0.0, 1.0, start_node2, end_node2, nodes2)

        if swap:
            args1, args2 = args2, args1

        args = args1 + args2
        _, _, success = self._call_function_under_test(*args)
        self.assertFalse(success)

    def test_no_intersection_bad_t_non_line(self):
        self._no_intersect_help_non_line()

    def test_no_intersection_bad_s_non_line(self):
        self._no_intersect_help_non_line(swap=True)

    def test_parallel_intersection(self):
        start_node1 = np.asfortranarray([[0.0, 0.0]])
        end_node1 = np.asfortranarray([[1.0, 1.0]])
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
        ])
        error1 = 0.0

        start_node2 = np.asfortranarray([[0.0, 1.0]])
        end_node2 = np.asfortranarray([[1.0, 2.0]])
        nodes2 = np.asfortranarray([
            [0.0, 1.0],
            [1.0, 2.0],
        ])
        error2 = 0.0

        _, _, success = self._call_function_under_test(
            error1, 0.0, 1.0, start_node1, end_node1, nodes1,
            error2, 0.0, 1.0, start_node2, end_node2, nodes2)
        self.assertFalse(success)

    def test_same_line_intersection(self):
        start_node1 = np.asfortranarray([[0.0, 0.0]])
        end_node1 = np.asfortranarray([[1.0, 1.0]])
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
        ])
        error1 = 0.0

        start_node2 = np.asfortranarray([[0.5, 0.5]])
        end_node2 = np.asfortranarray([[3.0, 3.0]])
        nodes2 = np.asfortranarray([
            [0.5, 0.5],
            [3.0, 3.0],
        ])
        error2 = 0.0

        with self.assertRaises(NotImplementedError):
            self._call_function_under_test(
                error1, 0.0, 1.0, start_node1, end_node1, nodes1,
                error2, 0.0, 1.0, start_node2, end_node2, nodes2)

    def test_parallel_non_degree_one_disjoint(self):
        start_node1 = np.asfortranarray([[0.0, 0.0]])
        end_node1 = np.asfortranarray([[1.0, 1.0]])
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
        ])
        error1 = 0.0

        start_node2 = np.asfortranarray([[2.0, 2.0]])
        end_node2 = np.asfortranarray([[3.0, 3.0]])
        nodes2 = np.asfortranarray([
            [2.0, 2.0],
            [2.5009765625, 2.5009765625],
            [3.0, 3.0],
        ])
        error2 = np.nan

        _, _, success = self._call_function_under_test(
            error1, 0.0, 1.0, start_node1, end_node1, nodes1,
            error2, 0.0, 1.0, start_node2, end_node2, nodes2)
        self.assertFalse(success)

    def test_parallel_non_degree_not_disjoint(self):
        start_node1 = np.asfortranarray([[0.0, 0.0]])
        end_node1 = np.asfortranarray([[1.0, 1.0]])
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
        ])
        error1 = 0.0

        start_node2 = np.asfortranarray([[0.5, 0.75]])
        end_node2 = np.asfortranarray([[1.5, 1.75]])
        nodes2 = np.asfortranarray([
            [0.5, 0.75],
            [1.0009765625, 1.2509765625],
            [1.5, 1.75],
        ])
        error2 = np.nan

        with self.assertRaises(NotImplementedError):
            self._call_function_under_test(
                error1, 0.0, 1.0, start_node1, end_node1, nodes1,
                error2, 0.0, 1.0, start_node2, end_node2, nodes2)


@utils.needs_curve_intersection_speedup
class Test_speedup_from_linearized_low_level(Test__from_linearized_low_level):

    # pylint: disable=too-many-arguments
    @staticmethod
    def _call_function_under_test(
            error1, start1, end1, start_node1, end_node1, nodes1,
            error2, start2, end2, start_node2, end_node2, nodes2):
        from bezier import _curve_intersection_speedup

        return _curve_intersection_speedup.from_linearized_low_level(
            error1, start1, end1, start_node1, end_node1, nodes1,
            error2, start2, end2, start_node2, end_node2, nodes2)
    # pylint: enable=too-many-arguments


class Test_from_linearized(utils.NumPyTestCase):

    @staticmethod
    def _call_function_under_test(first, second, intersections):
        from bezier import _geometric_intersection

        return _geometric_intersection.from_linearized(
            first, second, intersections)

    def test_success(self):
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [0.5, 1.0],
            [1.0, 1.0],
        ])
        curve1 = subdivided_curve(nodes1)
        # NOTE: This curve isn't close to linear, but that's OK.
        lin1 = make_linearization(curve1)

        nodes2 = np.asfortranarray([
            [0.0, 1.0],
            [0.5, 1.0],
            [1.0, 0.0],
        ])
        curve2 = subdivided_curve(nodes2)
        # NOTE: This curve isn't close to linear, but that's OK.
        lin2 = make_linearization(curve2)

        intersections = []
        self.assertIsNone(
            self._call_function_under_test(lin1, lin2, intersections))
        self.assertEqual(intersections, [(0.5, 0.5)])

    def test_failure(self):
        # The bounding boxes intersect but the lines do not.
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
        ])
        curve1 = subdivided_curve(nodes1)
        lin1 = make_linearization(curve1, 0.0)

        nodes2 = np.asfortranarray([
            [1.75, -0.75],
            [0.75, 0.25],
        ])
        curve2 = subdivided_curve(nodes2)
        lin2 = make_linearization(curve2, 0.0)

        intersections = []
        self.assertIsNone(
            self._call_function_under_test(lin1, lin2, intersections))
        self.assertEqual(len(intersections), 0)


class Test_add_intersection(unittest.TestCase):

    @staticmethod
    def _call_function_under_test(s, t, intersections):
        from bezier import _geometric_intersection

        return _geometric_intersection.add_intersection(s, t, intersections)

    def test_new(self):
        intersections = [(0.5, 0.5)]
        self.assertIsNone(
            self._call_function_under_test(0.75, 0.25, intersections))

        expected = [
            (0.5, 0.5),
            (0.75, 0.25),
        ]
        self.assertEqual(intersections, expected)

    def test_existing(self):
        intersections = [(0.0, 1.0)]
        self.assertIsNone(
            self._call_function_under_test(0.0, 1.0, intersections))

        self.assertEqual(intersections, [(0.0, 1.0)])

    def test_ulp_wiggle(self):
        from bezier import _geometric_intersection

        delta = 3 * SPACING(0.5)
        intersections = [(0.5, 0.5)]
        s_val = 0.5 + delta
        t_val = 0.5

        patch = unittest.mock.patch.object(
            _geometric_intersection, '_SIMILAR_ULPS', new=10)
        with patch:
            self.assertIsNone(
                self._call_function_under_test(s_val, t_val, intersections))
            # No change since delta is within 10 ULPs.
            self.assertEqual(intersections, [(0.5, 0.5)])

        patch = unittest.mock.patch.object(
            _geometric_intersection, '_SIMILAR_ULPS', new=3)
        with patch:
            self.assertIsNone(
                self._call_function_under_test(s_val, t_val, intersections))
            # No change since delta is within 3 ULPs.
            self.assertEqual(intersections, [(0.5, 0.5)])

        patch = unittest.mock.patch.object(
            _geometric_intersection, '_SIMILAR_ULPS', new=2)
        with patch:
            self.assertIsNone(
                self._call_function_under_test(s_val, t_val, intersections))
            # Add new intersection since delta is not within 2 ULPs.
            self.assertEqual(intersections, [(0.5, 0.5), (s_val, t_val)])


class Test_endpoint_check(utils.NumPyTestCase):

    @staticmethod
    def _call_function_under_test(
            first, node_first, s, second, node_second, t, intersections):
        from bezier import _geometric_intersection

        return _geometric_intersection.endpoint_check(
            first, node_first, s, second, node_second, t, intersections)

    def test_not_close(self):
        node_first = np.asfortranarray([[0.0, 0.0]])
        node_second = np.asfortranarray([[1.0, 1.0]])
        intersections = []
        self._call_function_under_test(
            None, node_first, None, None, node_second, None, intersections)
        self.assertEqual(intersections, [])

    def test_same(self):
        nodes_first = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
        ])
        first = subdivided_curve(nodes_first)
        nodes_second = np.asfortranarray([
            [1.0, 1.0],
            [2.0, 1.0],
        ])
        second = subdivided_curve(nodes_second)

        s_val = 1.0
        node_first = np.asfortranarray(first.nodes_REFACTOR[[1], :])
        t_val = 0.0
        node_second = np.asfortranarray(second.nodes_REFACTOR[[0], :])

        intersections = []
        self._call_function_under_test(
            first, node_first, s_val,
            second, node_second, t_val, intersections)

        self.assertEqual(intersections, [(s_val, t_val)])

    def test_subcurves_middle(self):
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [0.5, 1.0],
            [1.0, 0.0],
        ])
        root1 = subdivided_curve(nodes1)
        first, _ = root1.subdivide()
        nodes2 = np.asfortranarray([
            [1.0, 1.5],
            [0.0, 0.5],
            [1.0, -0.5],
        ])
        root2 = subdivided_curve(nodes2)
        _, second = root2.subdivide()

        s_val = 1.0
        node_first = np.asfortranarray(first.nodes_REFACTOR[[2], :])
        t_val = 0.0
        node_second = np.asfortranarray(second.nodes_REFACTOR[[0], :])

        intersections = []
        self._call_function_under_test(
            first, node_first, s_val,
            second, node_second, t_val, intersections)

        self.assertEqual(intersections, [(0.5, 0.5)])


class Test_tangent_bbox_intersection(utils.NumPyTestCase):

    @staticmethod
    def _call_function_under_test(first, second, intersections):
        from bezier import _geometric_intersection

        return _geometric_intersection.tangent_bbox_intersection(
            first, second, intersections)

    def test_one_endpoint(self):
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 2.0],
            [2.0, 0.0],
        ])
        curve1 = subdivided_curve(nodes1)
        nodes2 = np.asfortranarray([
            [2.0, 0.0],
            [3.0, 2.0],
            [4.0, 0.0],
        ])
        curve2 = subdivided_curve(nodes2)

        intersections = []
        self.assertIsNone(
            self._call_function_under_test(curve1, curve2, intersections))
        self.assertEqual(intersections, [(1.0, 0.0)])

    def test_two_endpoints(self):
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [-1.0, 0.5],
            [0.0, 1.0],
        ])
        curve1 = subdivided_curve(nodes1)
        nodes2 = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 0.5],
            [0.0, 1.0],
        ])
        curve2 = subdivided_curve(nodes2)

        intersections = []
        self.assertIsNone(
            self._call_function_under_test(curve1, curve2, intersections))
        expected = [
            (0.0, 0.0),
            (1.0, 1.0),
        ]
        self.assertEqual(intersections, expected)

    def test_no_endpoints(self):
        # Lines have tangent bounding boxes but don't intersect.
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [2.0, 1.0],
        ])
        curve1 = subdivided_curve(nodes1)
        nodes2 = np.asfortranarray([
            [0.5, 1.0],
            [2.5, 2.0],
        ])
        curve2 = subdivided_curve(nodes2)

        intersections = []
        self.assertIsNone(
            self._call_function_under_test(curve1, curve2, intersections))
        self.assertEqual(intersections, [])


class Test__bbox_line_intersect(utils.NumPyTestCase):

    @staticmethod
    def _call_function_under_test(nodes, line_start, line_end):
        from bezier import _geometric_intersection

        return _geometric_intersection._bbox_line_intersect(
            nodes, line_start, line_end)

    def test_start_in_bbox(self):
        from bezier import _geometric_intersection

        line_start = np.asfortranarray([[0.5, 0.5]])
        line_end = np.asfortranarray([[0.5, 1.5]])

        result = self._call_function_under_test(
            UNIT_SQUARE, line_start, line_end)
        expected = _geometric_intersection.BoxIntersectionType.INTERSECTION
        self.assertEqual(result, expected)

    def test_end_in_bbox(self):
        from bezier import _geometric_intersection

        line_start = np.asfortranarray([[-1.0, 0.5]])
        line_end = np.asfortranarray([[0.5, 0.5]])

        result = self._call_function_under_test(
            UNIT_SQUARE, line_start, line_end)
        expected = _geometric_intersection.BoxIntersectionType.INTERSECTION
        self.assertEqual(result, expected)

    def test_segment_intersect_bbox_bottom(self):
        from bezier import _geometric_intersection

        line_start = np.asfortranarray([[0.5, -0.5]])
        line_end = np.asfortranarray([[0.5, 1.5]])

        result = self._call_function_under_test(
            UNIT_SQUARE, line_start, line_end)
        expected = _geometric_intersection.BoxIntersectionType.INTERSECTION
        self.assertEqual(result, expected)

    def test_segment_intersect_bbox_right(self):
        from bezier import _geometric_intersection

        line_start = np.asfortranarray([[-0.5, 0.5]])
        line_end = np.asfortranarray([[1.5, 0.5]])

        result = self._call_function_under_test(
            UNIT_SQUARE, line_start, line_end)
        expected = _geometric_intersection.BoxIntersectionType.INTERSECTION
        self.assertEqual(result, expected)

    def test_segment_intersect_bbox_top(self):
        from bezier import _geometric_intersection

        line_start = np.asfortranarray([[-0.25, 0.5]])
        line_end = np.asfortranarray([[0.5, 1.25]])

        result = self._call_function_under_test(
            UNIT_SQUARE, line_start, line_end)
        expected = _geometric_intersection.BoxIntersectionType.INTERSECTION
        self.assertEqual(result, expected)

    def test_disjoint(self):
        from bezier import _geometric_intersection

        line_start = np.asfortranarray([[2.0, 2.0]])
        line_end = np.asfortranarray([[2.0, 5.0]])

        result = self._call_function_under_test(
            UNIT_SQUARE, line_start, line_end)
        expected = _geometric_intersection.BoxIntersectionType.DISJOINT
        self.assertEqual(result, expected)


@utils.needs_curve_intersection_speedup
class Test_speedup_bbox_line_intersect(Test__bbox_line_intersect):

    @staticmethod
    def _call_function_under_test(nodes, line_start, line_end):
        from bezier import _curve_intersection_speedup

        return _curve_intersection_speedup.bbox_line_intersect(
            nodes, line_start, line_end)


class Test_intersect_one_round(utils.NumPyTestCase):

    # NOTE: QUADRATIC1 is a specialization of [0, 0], [1/2, 1], [1, 1]
    #       onto the interval [1/4, 1].
    QUADRATIC1 = np.asfortranarray([
        [0.25, 0.4375],
        [0.625, 1.0],
        [1.0, 1.0],
    ])
    # NOTE: QUADRATIC2 is a specialization of [0, 1], [1/2, 1], [1, 0]
    #       onto the interval [0, 3/4].
    QUADRATIC2 = np.asfortranarray([
        [0.0, 1.0],
        [0.375, 1.0],
        [0.75, 0.4375],
    ])
    LINE1 = np.asfortranarray([
        [0.0, 0.0],
        [1.0, 1.0],
    ])
    LINE2 = np.asfortranarray([
        [0.0, 1.0],
        [1.0, 0.0],
    ])

    @staticmethod
    def _call_function_under_test(candidates, intersections):
        from bezier import _geometric_intersection

        return _geometric_intersection.intersect_one_round(
            candidates, intersections)

    def _curves_compare(self, curve1, curve2):
        import bezier
        from bezier import _geometric_intersection

        if isinstance(curve1, _geometric_intersection.Linearization):
            self.assertIsInstance(
                curve2, _geometric_intersection.Linearization)
            # We just check identity, since we assume a ``Linearization``
            # can't be subdivided.
            self.assertIs(curve1, curve2)
        else:
            self.assertIsInstance(
                curve1, _geometric_intersection.SubdividedCurve)
            self.assertIsInstance(
                curve2, _geometric_intersection.SubdividedCurve)
            self.assertIs(curve1.original_REFACTOR, curve2.original_REFACTOR)
            self.assertEqual(curve1.start_REFACTOR, curve2.start_REFACTOR)
            self.assertEqual(curve1.end_REFACTOR, curve2.end_REFACTOR)
            self.assertEqual(curve1.nodes_REFACTOR, curve2.nodes_REFACTOR)

    def _candidates_compare(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for first, second in zip(actual, expected):
            self.assertEqual(len(first), 2)
            self.assertEqual(len(second), 2)
            self._curves_compare(first[0], second[0])
            self._curves_compare(first[1], second[1])

    def test_simple(self):
        curve1 = subdivided_curve(self.QUADRATIC1)
        curve2 = subdivided_curve(self.QUADRATIC2)
        candidates = [(curve1, curve2)]
        next_candidates = self._call_function_under_test(
            candidates, [])

        left1, right1 = curve1.subdivide()
        left2, right2 = curve2.subdivide()
        expected = [
            (left1, left2),
            (left1, right2),
            (right1, left2),
            (right1, right2),
        ]
        self._candidates_compare(next_candidates, expected)

    def test_first_linearized(self):
        curve1 = subdivided_curve(self.LINE1)
        lin1 = make_linearization(curve1, 0.0)
        curve2 = subdivided_curve(self.QUADRATIC2)

        intersections = []
        next_candidates = self._call_function_under_test(
            [(lin1, curve2)], intersections)

        self.assertEqual(intersections, [])
        left2, right2 = curve2.subdivide()
        expected = [
            (lin1, left2),
            (lin1, right2),
        ]
        self._candidates_compare(next_candidates, expected)

    def test_second_linearized(self):
        curve1 = subdivided_curve(self.QUADRATIC1)
        curve2 = subdivided_curve(self.LINE2)
        lin2 = make_linearization(curve2, 0.0)

        intersections = []
        next_candidates = self._call_function_under_test(
            [(curve1, lin2)], intersections)

        self.assertEqual(intersections, [])
        left1, right1 = curve1.subdivide()
        expected = [
            (left1, lin2),
            (right1, lin2),
        ]
        self._candidates_compare(next_candidates, expected)

    def test_both_linearized(self):
        curve1 = subdivided_curve(self.LINE1)
        lin1 = make_linearization(curve1, 0.0)
        curve2 = subdivided_curve(self.LINE2)
        lin2 = make_linearization(curve2, 0.0)

        intersections = []
        next_candidates = self._call_function_under_test(
            [(lin1, lin2)], intersections)
        self.assertEqual(next_candidates, [])
        self.assertEqual(intersections, [(0.5, 0.5)])

    def test_failure_due_to_parallel(self):
        from bezier import _geometric_intersection

        curve1 = subdivided_curve(self.LINE1)
        lin1 = make_linearization(curve1, 0.0)
        nodes2 = np.asfortranarray([
            [0.5, 0.5],
            [3.0, 3.0],
        ])
        curve2 = subdivided_curve(nodes2)
        lin2 = make_linearization(curve2, 0.0)

        intersections = []
        with self.assertRaises(NotImplementedError) as exc_info:
            self._call_function_under_test([(lin1, lin2)], intersections)

        exc_args = exc_info.exception.args
        self.assertEqual(
            exc_args, (_geometric_intersection._SEGMENTS_PARALLEL,))
        self.assertEqual(intersections, [])

    def test_disjoint_bboxes(self):
        curve1 = subdivided_curve(self.QUADRATIC1)
        nodes2 = np.asfortranarray([
            [1.0, 1.25],
            [0.0, 2.0],
        ])
        curve2 = subdivided_curve(nodes2)
        lin2 = make_linearization(curve2, 0.0)

        intersections = []
        next_candidates = self._call_function_under_test(
            [(curve1, lin2)], intersections)
        self.assertEqual(next_candidates, [])
        self.assertEqual(intersections, [])

    def test_tangent_bboxes(self):
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [0.5, 1.0],
            [1.0, 0.0],
        ])
        curve1 = subdivided_curve(nodes1)
        nodes2 = np.asfortranarray([
            [1.0, 0.0],
            [1.5, 0.5],
            [2.0, -0.25],
        ])
        curve2 = subdivided_curve(nodes2)

        intersections = []
        next_candidates = self._call_function_under_test(
            [(curve1, curve2)], intersections)
        self.assertEqual(next_candidates, [])
        self.assertEqual(intersections, [(1.0, 0.0)])


class Test__all_intersections(utils.NumPyTestCase):

    @staticmethod
    def _call_function_under_test(nodes_first, nodes_second, **kwargs):
        from bezier import _geometric_intersection

        return _geometric_intersection._all_intersections(
            nodes_first, nodes_second, **kwargs)

    def test_no_intersections(self):
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
        ])
        nodes2 = np.asfortranarray([
            [3.0, 3.0],
            [4.0, 3.0],
        ])
        intersections = self._call_function_under_test(nodes1, nodes2)
        self.assertEqual(intersections.shape, (0, 2))

    def test_quadratics_intersect_once(self):
        # NOTE: ``nodes1`` is a specialization of [0, 0], [1/2, 1], [1, 1]
        #       onto the interval [1/4, 1] and ``nodes`` is a specialization
        #       of [0, 1], [1/2, 1], [1, 0] onto the interval [0, 3/4].
        #       We expect them to intersect at s = 1/3, t = 2/3, which is
        #       the point [1/2, 3/4].
        nodes1 = np.asfortranarray([
            [0.25, 0.4375],
            [0.625, 1.0],
            [1.0, 1.0],
        ])
        nodes2 = np.asfortranarray([
            [0.0, 1.0],
            [0.375, 1.0],
            [0.75, 0.4375],
        ])
        s_val = 1.0 / 3.0
        if base_utils.IS_64_BIT or base_utils.IS_WINDOWS:  # pragma: NO COVER
            # Due to round-off, the answer is wrong by a tiny wiggle.
            s_val += SPACING(s_val)
        t_val = 2.0 / 3.0

        intersections = self._call_function_under_test(nodes1, nodes2)
        expected = np.asfortranarray([[s_val, t_val]])
        self.assertEqual(intersections, expected)

    def test_parallel_failure(self):
        from bezier import _geometric_intersection

        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [0.375, 0.75],
            [0.75, 0.375],
        ])
        nodes2 = np.asfortranarray([
            [0.25, 0.625],
            [0.625, 0.25],
            [1.0, 1.0],
        ])
        with self.assertRaises(NotImplementedError) as exc_info:
            self._call_function_under_test(nodes1, nodes2)

        exc_args = exc_info.exception.args
        self.assertEqual(
            exc_args, (_geometric_intersection._SEGMENTS_PARALLEL,))

    def test_too_many_candidates(self):
        from bezier import _geometric_intersection

        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [-0.5, 1.5],
            [1.0, 1.0],
        ])
        nodes2 = np.asfortranarray([
            [-1.0, 1.0],
            [0.5, 0.5],
            [0.0, 2.0],
        ])
        with self.assertRaises(NotImplementedError) as exc_info:
            self._call_function_under_test(nodes1, nodes2)

        exc_args = exc_info.exception.args
        expected = _geometric_intersection._TOO_MANY_TEMPLATE.format(88)
        self.assertEqual(exc_args, (expected,))

    def test_non_convergence(self):
        from bezier import _geometric_intersection

        multiplier = 16384.0
        nodes1 = multiplier * np.asfortranarray([
            [0.0, 0.0],
            [4.5, 9.0],
            [9.0, 0.0],
        ])
        nodes2 = multiplier * np.asfortranarray([
            [0.0, 8.0],
            [6.0, 0.0],
        ])
        with self.assertRaises(ValueError) as exc_info:
            self._call_function_under_test(nodes1, nodes2)

        exc_args = exc_info.exception.args
        expected = _geometric_intersection._NO_CONVERGE_TEMPLATE.format(
            _geometric_intersection._MAX_INTERSECT_SUBDIVISIONS)
        self.assertEqual(exc_args, (expected,))

    def test_duplicates(self):
        # After three subdivisions, there are 8 pairs of curve segments
        # which have bounding boxes that touch at corners (these corners are
        # also intersections). This test makes sure the duplicates are
        # de-duplicated.
        nodes1 = np.asfortranarray([
            [0.0, 0.0],
            [0.5, 1.0],
            [1.0, 0.0],
        ])
        nodes2 = np.asfortranarray([
            [0.0, 0.75],
            [0.5, -0.25],
            [1.0, 0.75],
        ])
        intersections = self._call_function_under_test(nodes1, nodes2)
        expected = np.asfortranarray([
            [0.25, 0.25],
            [0.75, 0.75],
        ])
        self.assertEqual(intersections, expected)


@utils.needs_curve_intersection_speedup
class Test_speedup_all_intersections(Test__all_intersections):

    @staticmethod
    def _call_function_under_test(nodes_first, nodes_second, **kwargs):
        from bezier import _curve_intersection_speedup

        return _curve_intersection_speedup.all_intersections(
            nodes_first, nodes_second, **kwargs)

    def test_workspace_resize(self):
        from bezier import _curve_intersection_speedup

        nodes1 = np.asfortranarray([
            [-3.0, 0.0],
            [5.0, 0.0],
        ])
        nodes2 = np.asfortranarray([
            [-7.0, -9.0],
            [9.0, 13.0],
            [-7.0, -13.0],
            [9.0, 9.0],
        ])
        # NOTE: These curves intersect 3 times, so a workspace of
        #       2 is not large enough.
        _curve_intersection_speedup.reset_workspace(2)
        intersections = self._call_function_under_test(nodes1, nodes2)
        expected = np.asfortranarray([
            [0.5, 0.5],
            [0.375, 0.25],
            [0.625, 0.75],
        ])
        self.assertEqual(intersections, expected)
        # Make sure the workspace was resized.
        self.assertEqual(_curve_intersection_speedup.workspace_size(), 3)

    def test_workspace_too_small(self):
        from bezier import _curve_intersection_speedup

        nodes1 = np.asfortranarray([
            [-3.0, 0.0],
            [5.0, 0.0],
        ])
        nodes2 = np.asfortranarray([
            [-7.0, -9.0],
            [9.0, 13.0],
            [-7.0, -13.0],
            [9.0, 9.0],
        ])
        # NOTE: These curves intersect 3 times, so a workspace of
        #       2 is not large enough.
        _curve_intersection_speedup.reset_workspace(2)
        with self.assertRaises(ValueError) as exc_info:
            self._call_function_under_test(
                nodes1, nodes2, allow_resize=False)

        exc_args = exc_info.exception.args
        expected = _curve_intersection_speedup.TOO_SMALL_TEMPLATE.format(2, 3)
        self.assertEqual(exc_args, (expected,))
        # Make sure the workspace was **not** resized.
        self.assertEqual(_curve_intersection_speedup.workspace_size(), 2)


class TestBoxIntersectionType(unittest.TestCase):

    @staticmethod
    def _get_target_class():
        from bezier import _geometric_intersection

        return _geometric_intersection.BoxIntersectionType

    def _is_magic_method(self, name):
        if name.startswith('_'):
            self.assertTrue(name.startswith('__'))
            self.assertTrue(name.endswith('__'))
            return True
        else:
            return False

    @utils.needs_curve_intersection_speedup
    def test_verify_fortran_enums(self):
        from bezier import _curve_intersection_speedup

        klass = self._get_target_class()
        props = set(
            name
            for name in six.iterkeys(klass.__dict__)
            if not self._is_magic_method(name)
        )
        expected_props = set(['INTERSECTION', 'TANGENT', 'DISJOINT'])
        self.assertEqual(props, expected_props)

        # Actually verify the enums.
        curve_mod = _curve_intersection_speedup
        self.assertEqual(
            klass.INTERSECTION, curve_mod.BoxIntersectionType_INTERSECTION)
        self.assertEqual(klass.TANGENT, curve_mod.BoxIntersectionType_TANGENT)
        self.assertEqual(
            klass.DISJOINT, curve_mod.BoxIntersectionType_DISJOINT)


class TestLinearization(utils.NumPyTestCase):

    NODES = np.asfortranarray([
        [0.0, 0.0],
        [1.0, 1.0],
        [5.0, 6.0],
    ])

    @staticmethod
    def _get_target_class():
        from bezier import _geometric_intersection

        return _geometric_intersection.Linearization

    def _make_one(self, *args, **kwargs):
        klass = self._get_target_class()
        return klass(*args, **kwargs)

    def _simple_curve(self):
        return subdivided_curve(self.NODES)

    def test_constructor(self):
        nodes = np.asfortranarray([
            [4.0, -5.0],
            [0.0, 7.0],
        ])
        curve = subdivided_curve(nodes)
        error = 0.125
        linearization = self._make_one(curve, error)
        self.assertIs(linearization.curve, curve)
        self.assertEqual(linearization.error, error)
        self.assertEqual(
            np.asfortranarray(linearization.start_node),
            np.asfortranarray(nodes[[0], :]))
        self.assertEqual(
            np.asfortranarray(linearization.end_node),
            np.asfortranarray(nodes[[1], :]))

    def test_subdivide(self):
        linearization = self._make_one(self._simple_curve(), np.nan)
        self.assertEqual(linearization.subdivide(), (linearization,))

    def test_start_node_attr(self):
        curve = self._simple_curve()
        linearization = self._make_one(curve, np.nan)
        expected = np.asfortranarray(self.NODES[[0], :])
        self.assertEqual(
            np.asfortranarray(linearization.start_node), expected)
        # Make sure the data is "original" (was previously a view).
        self.assertIsNone(linearization.start_node.base)
        self.assertTrue(linearization.start_node.flags.owndata)

    def test_end_node_attr(self):
        curve = self._simple_curve()
        linearization = self._make_one(curve, np.nan)
        expected = np.asfortranarray(self.NODES[[2], :])
        self.assertEqual(
            np.asfortranarray(linearization.end_node), expected)
        # Make sure the data is "original" (was previously a view).
        self.assertIsNone(linearization.end_node.base)
        self.assertTrue(linearization.end_node.flags.owndata)

    def test_from_shape_factory_not_close_enough(self):
        curve = self._simple_curve()
        klass = self._get_target_class()
        new_shape = klass.from_shape(curve)
        self.assertIs(new_shape, curve)

    def test_from_shape_factory_close_enough(self):
        scale_factor = 2.0**(-27)
        nodes = self.NODES * scale_factor
        curve = subdivided_curve(nodes)
        klass = self._get_target_class()
        new_shape = klass.from_shape(curve)

        self.assertIsInstance(new_shape, klass)
        self.assertIs(new_shape.curve, curve)
        # NODES has constant second derivative equal to 2 * [3.0, 4.0].
        expected_error = 0.125 * 2 * 1 * 5.0 * scale_factor
        self.assertEqual(new_shape.error, expected_error)

    def test_from_shape_factory_no_error(self):
        nodes = np.asfortranarray([
            [0.0, 0.0],
            [1.0, 1.0],
        ])
        curve = subdivided_curve(nodes)
        klass = self._get_target_class()
        new_shape = klass.from_shape(curve)
        self.assertIsInstance(new_shape, klass)
        self.assertIs(new_shape.curve, curve)
        # ``nodes`` is linear, so error is 0.0.
        self.assertEqual(new_shape.error, 0.0)

    def test_from_shape_factory_already_linearized(self):
        error = 0.078125
        linearization = self._make_one(self._simple_curve(), error)

        klass = self._get_target_class()
        new_shape = klass.from_shape(linearization)
        self.assertIs(new_shape, linearization)
        self.assertEqual(new_shape.error, error)


def subdivided_curve(nodes):
    from bezier import _geometric_intersection

    return _geometric_intersection.SubdividedCurve(nodes, nodes)


def make_linearization(curve, error=np.nan):
    from bezier import _geometric_intersection

    return _geometric_intersection.Linearization(curve, error)
