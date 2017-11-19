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

"""Private helper methods for :mod:`bezier.surface`.

As a convention, the functions defined here with a leading underscore
(e.g. :func:`_jacobian_det`) have a special meaning.

Each of these functions have a Cython speedup with the exact same
interface which calls out to a Fortran implementation. The speedup
will be used if the extension can be built. The name **without** the
leading underscore will be surfaced as the actual interface (e.g.
``jacobian_det``) whether that is the pure Python implementation
or the speedup.

.. |eacute| unicode:: U+000E9 .. LATIN SMALL LETTER E WITH ACUTE
   :trim:
"""


import collections
import enum
import functools
import itertools
import operator

import numpy as np
import six

from bezier import _curve_helpers
from bezier import _helpers
from bezier import _intersection_helpers
from bezier import curved_polygon
try:
    from bezier import _surface_speedup
except ImportError:  # pragma: NO COVER
    _surface_speedup = None


_MAX_POLY_SUBDIVISIONS = 5
_SIGN = np.sign  # pylint: disable=no-member
_FLOAT64 = np.float64  # pylint: disable=no-member
_SAME_CURVATURE = 'Tangent curves have same curvature.'
_BAD_TANGENT = (
    'Curves moving in opposite direction but define '
    'overlapping arcs.')
_WRONG_CURVE = 'Start and end node not defined on same curve'
# NOTE: The ``SUBDIVIDE`` matrices are public since used in
#       the ``surface`` module.
LINEAR_SUBDIVIDE_A = np.asfortranarray([
    [2, 0, 0],
    [1, 1, 0],
    [1, 0, 1],
], dtype=_FLOAT64) / 2.0
LINEAR_SUBDIVIDE_B = np.asfortranarray([
    [0, 1, 1],
    [1, 0, 1],
    [1, 1, 0],
], dtype=_FLOAT64) / 2.0
LINEAR_SUBDIVIDE_C = np.asfortranarray([
    [1, 1, 0],
    [0, 2, 0],
    [0, 1, 1],
], dtype=_FLOAT64) / 2.0
LINEAR_SUBDIVIDE_D = np.asfortranarray([
    [1, 0, 1],
    [0, 1, 1],
    [0, 0, 2],
], dtype=_FLOAT64) / 2.0
QUADRATIC_SUBDIVIDE_A = np.asfortranarray([
    [4, 0, 0, 0, 0, 0],
    [2, 2, 0, 0, 0, 0],
    [1, 2, 1, 0, 0, 0],
    [2, 0, 0, 2, 0, 0],
    [1, 1, 0, 1, 1, 0],
    [1, 0, 0, 2, 0, 1],
], dtype=_FLOAT64) / 4.0
QUADRATIC_SUBDIVIDE_B = np.asfortranarray([
    [0, 0, 1, 0, 2, 1],
    [0, 1, 0, 1, 1, 1],
    [1, 0, 0, 2, 0, 1],
    [0, 1, 1, 1, 1, 0],
    [1, 1, 0, 1, 1, 0],
    [1, 2, 1, 0, 0, 0],
], dtype=_FLOAT64) / 4.0
QUADRATIC_SUBDIVIDE_C = np.asfortranarray([
    [1, 2, 1, 0, 0, 0],
    [0, 2, 2, 0, 0, 0],
    [0, 0, 4, 0, 0, 0],
    [0, 1, 1, 1, 1, 0],
    [0, 0, 2, 0, 2, 0],
    [0, 0, 1, 0, 2, 1],
], dtype=_FLOAT64) / 4.0
QUADRATIC_SUBDIVIDE_D = np.asfortranarray([
    [1, 0, 0, 2, 0, 1],
    [0, 1, 0, 1, 1, 1],
    [0, 0, 1, 0, 2, 1],
    [0, 0, 0, 2, 0, 2],
    [0, 0, 0, 0, 2, 2],
    [0, 0, 0, 0, 0, 4],
], dtype=_FLOAT64) / 4.0
CUBIC_SUBDIVIDE_A = np.asfortranarray([
    [8, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [4, 4, 0, 0, 0, 0, 0, 0, 0, 0],
    [2, 4, 2, 0, 0, 0, 0, 0, 0, 0],
    [1, 3, 3, 1, 0, 0, 0, 0, 0, 0],
    [4, 0, 0, 0, 4, 0, 0, 0, 0, 0],
    [2, 2, 0, 0, 2, 2, 0, 0, 0, 0],
    [1, 2, 1, 0, 1, 2, 1, 0, 0, 0],
    [2, 0, 0, 0, 4, 0, 0, 2, 0, 0],
    [1, 1, 0, 0, 2, 2, 0, 1, 1, 0],
    [1, 0, 0, 0, 3, 0, 0, 3, 0, 1],
], dtype=_FLOAT64) / 8.0
CUBIC_SUBDIVIDE_B = np.asfortranarray([
    [0, 0, 0, 1, 0, 0, 3, 0, 3, 1],
    [0, 0, 1, 0, 0, 2, 1, 1, 2, 1],
    [0, 1, 0, 0, 1, 2, 0, 2, 1, 1],
    [1, 0, 0, 0, 3, 0, 0, 3, 0, 1],
    [0, 0, 1, 1, 0, 2, 2, 1, 1, 0],
    [0, 1, 1, 0, 1, 2, 1, 1, 1, 0],
    [1, 1, 0, 0, 2, 2, 0, 1, 1, 0],
    [0, 1, 2, 1, 1, 2, 1, 0, 0, 0],
    [1, 2, 1, 0, 1, 2, 1, 0, 0, 0],
    [1, 3, 3, 1, 0, 0, 0, 0, 0, 0],
], dtype=_FLOAT64) / 8.0
CUBIC_SUBDIVIDE_C = np.asfortranarray([
    [1, 3, 3, 1, 0, 0, 0, 0, 0, 0],
    [0, 2, 4, 2, 0, 0, 0, 0, 0, 0],
    [0, 0, 4, 4, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 8, 0, 0, 0, 0, 0, 0],
    [0, 1, 2, 1, 1, 2, 1, 0, 0, 0],
    [0, 0, 2, 2, 0, 2, 2, 0, 0, 0],
    [0, 0, 0, 4, 0, 0, 4, 0, 0, 0],
    [0, 0, 1, 1, 0, 2, 2, 1, 1, 0],
    [0, 0, 0, 2, 0, 0, 4, 0, 2, 0],
    [0, 0, 0, 1, 0, 0, 3, 0, 3, 1],
], dtype=_FLOAT64) / 8.0
CUBIC_SUBDIVIDE_D = np.asfortranarray([
    [1, 0, 0, 0, 3, 0, 0, 3, 0, 1],
    [0, 1, 0, 0, 1, 2, 0, 2, 1, 1],
    [0, 0, 1, 0, 0, 2, 1, 1, 2, 1],
    [0, 0, 0, 1, 0, 0, 3, 0, 3, 1],
    [0, 0, 0, 0, 2, 0, 0, 4, 0, 2],
    [0, 0, 0, 0, 0, 2, 0, 2, 2, 2],
    [0, 0, 0, 0, 0, 0, 2, 0, 4, 2],
    [0, 0, 0, 0, 0, 0, 0, 4, 0, 4],
    [0, 0, 0, 0, 0, 0, 0, 0, 4, 4],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 8],
], dtype=_FLOAT64) / 8.0
QUARTIC_SUBDIVIDE_A = np.asfortranarray([
    [16, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [8, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [4, 8, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [2, 6, 6, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 4, 6, 4, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [8, 0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [4, 4, 0, 0, 0, 4, 4, 0, 0, 0, 0, 0, 0, 0, 0],
    [2, 4, 2, 0, 0, 2, 4, 2, 0, 0, 0, 0, 0, 0, 0],
    [1, 3, 3, 1, 0, 1, 3, 3, 1, 0, 0, 0, 0, 0, 0],
    [4, 0, 0, 0, 0, 8, 0, 0, 0, 4, 0, 0, 0, 0, 0],
    [2, 2, 0, 0, 0, 4, 4, 0, 0, 2, 2, 0, 0, 0, 0],
    [1, 2, 1, 0, 0, 2, 4, 2, 0, 1, 2, 1, 0, 0, 0],
    [2, 0, 0, 0, 0, 6, 0, 0, 0, 6, 0, 0, 2, 0, 0],
    [1, 1, 0, 0, 0, 3, 3, 0, 0, 3, 3, 0, 1, 1, 0],
    [1, 0, 0, 0, 0, 4, 0, 0, 0, 6, 0, 0, 4, 0, 1],
], dtype=_FLOAT64) / 16.0
QUARTIC_SUBDIVIDE_B = np.asfortranarray([
    [0, 0, 0, 0, 1, 0, 0, 0, 4, 0, 0, 6, 0, 4, 1],
    [0, 0, 0, 1, 0, 0, 0, 3, 1, 0, 3, 3, 1, 3, 1],
    [0, 0, 1, 0, 0, 0, 2, 2, 0, 1, 4, 1, 2, 2, 1],
    [0, 1, 0, 0, 0, 1, 3, 0, 0, 3, 3, 0, 3, 1, 1],
    [1, 0, 0, 0, 0, 4, 0, 0, 0, 6, 0, 0, 4, 0, 1],
    [0, 0, 0, 1, 1, 0, 0, 3, 3, 0, 3, 3, 1, 1, 0],
    [0, 0, 1, 1, 0, 0, 2, 3, 1, 1, 3, 2, 1, 1, 0],
    [0, 1, 1, 0, 0, 1, 3, 2, 0, 2, 3, 1, 1, 1, 0],
    [1, 1, 0, 0, 0, 3, 3, 0, 0, 3, 3, 0, 1, 1, 0],
    [0, 0, 1, 2, 1, 0, 2, 4, 2, 1, 2, 1, 0, 0, 0],
    [0, 1, 2, 1, 0, 1, 3, 3, 1, 1, 2, 1, 0, 0, 0],
    [1, 2, 1, 0, 0, 2, 4, 2, 0, 1, 2, 1, 0, 0, 0],
    [0, 1, 3, 3, 1, 1, 3, 3, 1, 0, 0, 0, 0, 0, 0],
    [1, 3, 3, 1, 0, 1, 3, 3, 1, 0, 0, 0, 0, 0, 0],
    [1, 4, 6, 4, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
], dtype=_FLOAT64) / 16.0
QUARTIC_SUBDIVIDE_C = np.asfortranarray([
    [1, 4, 6, 4, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 2, 6, 6, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 4, 8, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 8, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 16, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 3, 3, 1, 1, 3, 3, 1, 0, 0, 0, 0, 0, 0],
    [0, 0, 2, 4, 2, 0, 2, 4, 2, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 4, 4, 0, 0, 4, 4, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 8, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0],
    [0, 0, 1, 2, 1, 0, 2, 4, 2, 1, 2, 1, 0, 0, 0],
    [0, 0, 0, 2, 2, 0, 0, 4, 4, 0, 2, 2, 0, 0, 0],
    [0, 0, 0, 0, 4, 0, 0, 0, 8, 0, 0, 4, 0, 0, 0],
    [0, 0, 0, 1, 1, 0, 0, 3, 3, 0, 3, 3, 1, 1, 0],
    [0, 0, 0, 0, 2, 0, 0, 0, 6, 0, 0, 6, 0, 2, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 4, 0, 0, 6, 0, 4, 1],
], dtype=_FLOAT64) / 16.0
QUARTIC_SUBDIVIDE_D = np.asfortranarray([
    [1, 0, 0, 0, 0, 4, 0, 0, 0, 6, 0, 0, 4, 0, 1],
    [0, 1, 0, 0, 0, 1, 3, 0, 0, 3, 3, 0, 3, 1, 1],
    [0, 0, 1, 0, 0, 0, 2, 2, 0, 1, 4, 1, 2, 2, 1],
    [0, 0, 0, 1, 0, 0, 0, 3, 1, 0, 3, 3, 1, 3, 1],
    [0, 0, 0, 0, 1, 0, 0, 0, 4, 0, 0, 6, 0, 4, 1],
    [0, 0, 0, 0, 0, 2, 0, 0, 0, 6, 0, 0, 6, 0, 2],
    [0, 0, 0, 0, 0, 0, 2, 0, 0, 2, 4, 0, 4, 2, 2],
    [0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 4, 2, 2, 4, 2],
    [0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 6, 0, 6, 2],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 0, 8, 0, 4],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 4, 4, 4],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 8, 4],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 0, 8],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 8],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 16],
], dtype=_FLOAT64) / 16.0
_WEIGHTS_SUBDIVIDE0 = np.asfortranarray([1.0, 0.0, 0.0])
_WEIGHTS_SUBDIVIDE1 = np.asfortranarray([0.5, 0.5, 0.0])
_WEIGHTS_SUBDIVIDE2 = np.asfortranarray([0.5, 0.0, 0.5])
_WEIGHTS_SUBDIVIDE3 = np.asfortranarray([0.0, 0.5, 0.5])
_WEIGHTS_SUBDIVIDE4 = np.asfortranarray([0.0, 1.0, 0.0])
_WEIGHTS_SUBDIVIDE5 = np.asfortranarray([0.0, 0.0, 1.0])
# The Jacobian of a quadratric (in any dimension) as given by
# dB/ds = [-2L1, 2(L1 - L2), 2L2, -2L3, 2L3, 0] * nodes
# dB/dt = [-2L1, -2L2, 0, 2(L1 - L3), 2L2, 2L3] * nodes
# We evaluate this at each of the 6 points in the quadratic
# triangle and then stack them (2 rows * 6 = 12 rows)
# pylint: disable=bad-whitespace
_QUADRATIC_JACOBIAN_HELPER = np.asfortranarray([
    [-2,  2, 0,  0, 0, 0],
    [-2,  0, 0,  2, 0, 0],
    [-1,  0, 1,  0, 0, 0],
    [-1, -1, 0,  1, 1, 0],
    [ 0, -2, 2,  0, 0, 0],  # noqa: E201
    [ 0, -2, 0,  0, 2, 0],  # noqa: E201
    [-1,  1, 0, -1, 1, 0],
    [-1,  0, 0,  0, 0, 1],
    [ 0, -1, 1, -1, 1, 0],  # noqa: E201
    [ 0, -1, 0, -1, 1, 1],  # noqa: E201
    [ 0,  0, 0, -2, 2, 0],  # noqa: E201
    [ 0,  0, 0, -2, 0, 2],  # noqa: E201
], dtype=_FLOAT64)
_QUADRATIC_TO_BERNSTEIN = np.asfortranarray([
    [ 2, 0,  0, 0, 0,  0],  # noqa: E201
    [-1, 4, -1, 0, 0,  0],
    [ 0, 0,  2, 0, 0,  0],  # noqa: E201
    [-1, 0,  0, 4, 0, -1],
    [ 0, 0, -1, 0, 4, -1],  # noqa: E201
    [ 0, 0,  0, 0, 0,  2],  # noqa: E201
], dtype=_FLOAT64) / 2.0
# pylint: enable=bad-whitespace
# The Jacobian of a cubic (in any dimension) as given by
# dB/ds = [-3 L1^2, 3 L1(L1 - 2 L2), 3 L2(2 L1 - L2), 3 L2^2, -6 L1 L3,
#          6 L3(L1 - L2), 6 L2 L3, -3 L3^2, 3 L3^2, 0] * nodes
# dB/dt = [-3 L1^2, -6 L1 L2, -3 L2^2, 0, 3 L1(L1 - 2 L3), 6 L2 (L1 - L3),
#          3 L2^2, 3 L3(2 L1 - L3), 6 L2 L3, 3 L3^2] * nodes
# We evaluate this at each of the 15 points in the quartic
# triangle and then stack them (2 rows * 15 = 30 rows)
# pylint: disable=bad-whitespace
_CUBIC_JACOBIAN_HELPER = np.asfortranarray([
    [-48,  48,   0,  0,   0,   0,  0,   0,  0,  0],
    [-48,   0,   0,  0,  48,   0,  0,   0,  0,  0],
    [-27,   9,  15,  3,   0,   0,  0,   0,  0,  0],
    [-27, -18,  -3,  0,  27,  18,  3,   0,  0,  0],
    [-12, -12,  12, 12,   0,   0,  0,   0,  0,  0],
    [-12, -24, -12,  0,  12,  24, 12,   0,  0,  0],
    [ -3, -15,  -9, 27,   0,   0,  0,   0,  0,  0],  # noqa: E201
    [ -3, -18, -27,  0,   3,  18, 27,   0,  0,  0],  # noqa: E201
    [  0,   0, -48, 48,   0,   0,  0,   0,  0,  0],  # noqa: E201
    [  0,   0, -48,  0,   0,   0, 48,   0,  0,  0],  # noqa: E201
    [-27,  27,   0,  0, -18,  18,  0,  -3,  3,  0],
    [-27,   0,   0,  0,   9,   0,  0,  15,  0,  3],
    [-12,   0,   9,  3, -12,   6,  6,  -3,  3,  0],
    [-12, -12,  -3,  0,   0,   6,  3,   9,  6,  3],
    [ -3,  -9,   0, 12,  -6,  -6, 12,  -3,  3,  0],  # noqa: E201
    [ -3, -12, -12,  0,  -3,   0, 12,   3, 12,  3],  # noqa: E201
    [  0,   0, -27, 27,   0, -18, 18,  -3,  3,  0],  # noqa: E201
    [  0,   0, -27,  0,   0, -18, 27,  -3, 18,  3],  # noqa: E201
    [-12,  12,   0,  0, -24,  24,  0, -12, 12,  0],
    [-12,   0,   0,  0, -12,   0,  0,  12,  0, 12],
    [ -3,  -3,   3,  3, -12,   0, 12, -12, 12,  0],  # noqa: E201
    [ -3,  -6,  -3,  0,  -9,  -6,  3,   0, 12, 12],  # noqa: E201
    [  0,   0, -12, 12,   0, -24, 24, -12, 12,  0],  # noqa: E201
    [  0,   0, -12,  0,   0, -24, 12, -12, 24, 12],  # noqa: E201
    [ -3,   3,   0,  0, -18,  18,  0, -27, 27,  0],  # noqa: E201
    [ -3,   0,   0,  0, -15,   0,  0,  -9,  0, 27],  # noqa: E201
    [  0,   0,  -3,  3,   0, -18, 18, -27, 27,  0],  # noqa: E201
    [  0,   0,  -3,  0,   0, -18,  3, -27, 18, 27],  # noqa: E201
    [  0,   0,   0,  0,   0,   0,  0, -48, 48,  0],  # noqa: E201
    [  0,   0,   0,  0,   0,   0,  0, -48,  0, 48],  # noqa: E201
], dtype=_FLOAT64) / 16.0
# pylint: enable=bad-whitespace
_QUARTIC_TO_BERNSTEIN = np.asfortranarray([
    [36, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [-39, 144, -108, 48, -9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [26, -128, 240, -128, 26, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [-9, 48, -108, 144, -39, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 36, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [-39, 0, 0, 0, 0, 144, 0, 0, 0, -108, 0, 0, 48, 0, -9],
    [26, -64, -24, 32, -9, -64, 288, -96, 16, -24, -96, 12, 32, 16, -9],
    [-9, 32, -24, -64, 26, 16, -96, 288, -64, 12, -96, -24, 16, 32, -9],
    [0, 0, 0, 0, -39, 0, 0, 0, 144, 0, 0, -108, 0, 48, -9],
    [26, 0, 0, 0, 0, -128, 0, 0, 0, 240, 0, 0, -128, 0, 26],
    [-9, 16, 12, 16, -9, 32, -96, -96, 32, -24, 288, -24, -64, -64, 26],
    [0, 0, 0, 0, 26, 0, 0, 0, -128, 0, 0, 240, 0, -128, 26],
    [-9, 0, 0, 0, 0, 48, 0, 0, 0, -108, 0, 0, 144, 0, -39],
    [0, 0, 0, 0, -9, 0, 0, 0, 48, 0, 0, -108, 0, 144, -39],
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 36],
], dtype=_FLOAT64)
# NOTE: We avoid round-off until after ``_QUARTIC_TO_BERNSTEIN``
#       has been applied.
_QUARTIC_BERNSTEIN_FACTOR = 36.0
# List of constants for ``make_intersection``. In each constant, each row is
# a return value of ``ends_to_curve``. The second and third constant are
# just obtained from the first by rotating the rows.
FIRST_SURFACE_INFO = (
    (
        (True, 0, 0.0, 1.0),
        (True, 1, 0.0, 1.0),
        (True, 2, 0.0, 1.0),
    ), (
        (True, 1, 0.0, 1.0),
        (True, 2, 0.0, 1.0),
        (True, 0, 0.0, 1.0),
    ), (
        (True, 2, 0.0, 1.0),
        (True, 0, 0.0, 1.0),
        (True, 1, 0.0, 1.0),
    ),
)
SECOND_SURFACE_INFO = (
    (
        (False, 0, 0.0, 1.0),
        (False, 1, 0.0, 1.0),
        (False, 2, 0.0, 1.0),
    ), (
        (False, 1, 0.0, 1.0),
        (False, 2, 0.0, 1.0),
        (False, 0, 0.0, 1.0),
    ), (
        (False, 2, 0.0, 1.0),
        (False, 0, 0.0, 1.0),
        (False, 1, 0.0, 1.0),
    ),
)


def polynomial_sign(poly_surface, degree):
    r"""Determine the "sign" of a polynomial on the reference triangle.

    .. note::

       This is used **only** by :meth:`Surface._compute_valid` (which is
       in turn used to compute / cache the :attr:`Surface.is_valid`
       property).

    Checks if a polynomial :math:`p(s, t)` is positive, negative
    or mixed sign on the reference triangle.

    Does this by utilizing the B |eacute| zier form of :math:`p`: it is a
    convex combination of the Bernstein basis (real numbers) hence
    if the Bernstein basis is all positive, the polynomial must be.

    If the values are mixed, then we can recursively subdivide
    until we are in a region where the coefficients are all one
    sign.

    Args:
        poly_surface (numpy.ndarray): 2D array (with 1 column) of control
            points for a "surface", i.e. a bivariate polynomial.
        degree (int): The degree of the surface / polynomial given by
            ``poly_surface``.

    Returns:
        int: The sign of the polynomial. Will be one of ``-1``, ``1``
        or ``0``. A value of ``0`` indicates a mixed sign or the
        zero polynomial.

    Raises:
        ValueError: If no conclusion is reached after the maximum
            number of subdivisions.
    """
    # The indices where the corner nodes in a surface are.
    corner_indices = (0, degree, -1)
    sub_polys = [poly_surface]
    signs = set()
    for _ in six.moves.xrange(_MAX_POLY_SUBDIVISIONS):
        undecided = []
        for poly in sub_polys:
            # First add all the signs of the corner nodes.
            signs.update(_SIGN(poly[corner_indices, 0]).astype(int))
            # Then check if the ``poly`` nodes are **uniformly** one sign.
            if np.all(poly == 0.0):
                signs.add(0)
            elif np.all(poly > 0.0):
                signs.add(1)
            elif np.all(poly < 0.0):
                signs.add(-1)
            else:
                undecided.append(poly)

            if len(signs) > 1:
                return 0

        sub_polys = functools.reduce(
            operator.add,
            [subdivide_nodes(poly, degree) for poly in undecided],
            (),
        )
        if not sub_polys:
            break

    if sub_polys:
        raise ValueError(
            'Did not reach a conclusion after max subdivisions',
            _MAX_POLY_SUBDIVISIONS)
    else:
        # NOTE: We are guaranteed that ``len(signs) <= 1``.
        return signs.pop()


def two_by_two_det(mat):
    r"""Compute the determinant of a 2x2 matrix.

    .. note::

       This is used **only** by :func:`quadratic_jacobian_polynomial` and
       :func:`cubic_jacobian_polynomial`.

    This is "needed" because :func:`numpy.linalg.det` uses a more generic
    determinant implementation which can introduce rounding even when the
    simple :math:`a d - b c` will suffice. For example:

    .. doctest:: 2-by-2

       >>> import numpy as np
       >>> mat = np.asfortranarray([
       ...     [-1.5   , 0.1875],
       ...     [-1.6875, 0.0   ],
       ... ])
       >>> actual_det = -mat[0, 1] * mat[1, 0]
       >>> np_det = np.linalg.det(mat)
       >>> np.abs(actual_det - np_det) == np.spacing(actual_det)
       True

    Args:
        mat (numpy.ndarray): A 2x2 matrix.

    Returns:
        float: The determinant of ``mat``.
    """
    return mat[0, 0] * mat[1, 1] - mat[0, 1] * mat[1, 0]


def quadratic_jacobian_polynomial(nodes):
    r"""Compute the Jacobian determinant of a quadratic surface.

    .. note::

       This is used **only** by :meth:`Surface._compute_valid` (which is
       in turn used to compute / cache the :attr:`Surface.is_valid`
       property).

    Converts :math:`\det(J(s, t))` to a polynomial on the reference
    triangle and represents it as a surface object.

    .. note::

       This assumes that ``nodes`` is 6x2 but doesn't verify this.
       (However, the multiplication by ``_QUADRATIC_JACOBIAN_HELPER``
       would fail if ``nodes`` wasn't 6xN and then the ensuing
       determinants would fail if there weren't 2 columns.)

    Args:
        nodes (numpy.ndarray): A 6x2 array of nodes in a surface.

    Returns:
        numpy.ndarray: Coefficients in Bernstein basis.
    """
    # First evaluate the Jacobian at each of the 6 nodes.
    # pylint: disable=no-member
    jac_parts = _helpers.matrix_product(
        _QUADRATIC_JACOBIAN_HELPER, nodes)
    # pylint: enable=no-member
    jac_at_nodes = np.empty((6, 1), order='F')
    jac_at_nodes[0, 0] = two_by_two_det(jac_parts[:2, :])
    jac_at_nodes[1, 0] = two_by_two_det(jac_parts[2:4, :])
    jac_at_nodes[2, 0] = two_by_two_det(jac_parts[4:6, :])
    jac_at_nodes[3, 0] = two_by_two_det(jac_parts[6:8, :])
    jac_at_nodes[4, 0] = two_by_two_det(jac_parts[8:10, :])
    jac_at_nodes[5, 0] = two_by_two_det(jac_parts[10:, :])

    # Convert the nodal values to the Bernstein basis...
    bernstein = _helpers.matrix_product(
        _QUADRATIC_TO_BERNSTEIN, jac_at_nodes)
    return bernstein


def cubic_jacobian_polynomial(nodes):
    r"""Compute the Jacobian determinant of a cubic surface.

    .. note::

       This is used **only** by :meth:`Surface._compute_valid` (which is
       in turn used to compute / cache the :attr:`Surface.is_valid`
       property).

    Converts :math:`\det(J(s, t))` to a polynomial on the reference
    triangle and represents it as a surface object.

    .. note::

       This assumes that ``nodes`` is 10x2 but doesn't verify this.
       (However, the multiplication by ``_CUBIC_JACOBIAN_HELPER``
       would fail if ``nodes`` wasn't 10xN and then the ensuing
       determinants would fail if there weren't 2 columns.)

    Args:
        nodes (numpy.ndarray): A 10x2 array of nodes in a surface.

    Returns:
        numpy.ndarray: 15x1 array, coefficients in Bernstein basis.
    """
    # First evaluate the Jacobian at each of the 15 nodes
    # in the quartic triangle.
    jac_parts = _helpers.matrix_product(
        _CUBIC_JACOBIAN_HELPER, nodes)
    jac_at_nodes = np.empty((15, 1), order='F')
    jac_at_nodes[0, 0] = two_by_two_det(jac_parts[:2, :])
    jac_at_nodes[1, 0] = two_by_two_det(jac_parts[2:4, :])
    jac_at_nodes[2, 0] = two_by_two_det(jac_parts[4:6, :])
    jac_at_nodes[3, 0] = two_by_two_det(jac_parts[6:8, :])
    jac_at_nodes[4, 0] = two_by_two_det(jac_parts[8:10, :])
    jac_at_nodes[5, 0] = two_by_two_det(jac_parts[10:12, :])
    jac_at_nodes[6, 0] = two_by_two_det(jac_parts[12:14, :])
    jac_at_nodes[7, 0] = two_by_two_det(jac_parts[14:16, :])
    jac_at_nodes[8, 0] = two_by_two_det(jac_parts[16:18, :])
    jac_at_nodes[9, 0] = two_by_two_det(jac_parts[18:20, :])
    jac_at_nodes[10, 0] = two_by_two_det(jac_parts[20:22, :])
    jac_at_nodes[11, 0] = two_by_two_det(jac_parts[22:24, :])
    jac_at_nodes[12, 0] = two_by_two_det(jac_parts[24:26, :])
    jac_at_nodes[13, 0] = two_by_two_det(jac_parts[26:28, :])
    jac_at_nodes[14, 0] = two_by_two_det(jac_parts[28:, :])

    # Convert the nodal values to the Bernstein basis...
    # pylint: disable=no-member
    bernstein = _helpers.matrix_product(
        _QUARTIC_TO_BERNSTEIN, jac_at_nodes)
    # pylint: enable=no-member
    bernstein /= _QUARTIC_BERNSTEIN_FACTOR
    return bernstein


def _de_casteljau_one_round(nodes, degree, lambda1, lambda2, lambda3):
    r"""Performs one "round" of the de Casteljau algorithm for surfaces.

    .. note::

       There is also a Fortran implementation of this function, which
       will be used if it can be built.

    .. note::

       This is a helper function, used by :func:`make_transform` and
       :func:`_specialize_surface` (and :func:`make_transform` is **only**
       used by :func:`_specialize_surface`).

    Converts the ``nodes`` into a basis for a surface one degree smaller
    by using the barycentric weights:

    .. math::

       q_{i, j, k} = \lambda_1 \cdot p_{i + 1, j, k} +
           \lambda_2 \cdot p_{i, j + 1, k} + \lambda_2 \cdot p_{i, j, k + 1}

    .. note:

       For degree :math:`d`d, the number of nodes should be
       :math:`(d + 1)(d + 2)/2`, but we don't verify this property.

    Args:
        nodes (numpy.ndarray): The nodes to reduce.
        degree (int): The degree of the surface.
        lambda1 (float): Parameter along the reference triangle.
        lambda2 (float): Parameter along the reference triangle.
        lambda3 (float): Parameter along the reference triangle.

    Returns:
        numpy.ndarray: The converted nodes.
    """
    num_nodes, dimension = nodes.shape
    num_new_nodes = num_nodes - degree - 1

    new_nodes = np.empty((num_new_nodes, dimension), order='F')

    index = 0
    # parent_i1 = index + k
    # parent_i2 = index + k + 1
    # parent_i3 = index + degree + 1
    parent_i1 = 0
    parent_i2 = 1
    parent_i3 = degree + 1
    for k in six.moves.xrange(degree):
        for unused_j in six.moves.xrange(degree - k):
            # NOTE: i = (degree - 1) - j - k
            new_nodes[index, :] = (
                lambda1 * nodes[parent_i1, :] +
                lambda2 * nodes[parent_i2, :] +
                lambda3 * nodes[parent_i3, :])
            # Update all the indices.
            parent_i1 += 1
            parent_i2 += 1
            parent_i3 += 1
            index += 1

        # Update the indices that depend on k.
        parent_i1 += 1
        parent_i2 += 1

    return new_nodes


def make_transform(degree, weights_a, weights_b, weights_c):
    """Compute matrices corresponding to the de Casteljau algorithm.

    .. note::

       This is a helper used only by :func:`_specialize_surface`.

    Applies the de Casteljau to the identity matrix, thus
    effectively caching the algorithm in a transformation matrix.

    .. note::

       This is premature optimization. It's unclear if the time
       saved from "caching" one round of de Casteljau is cancelled
       out by the extra storage required for the 3 matrices.

    Args:
        degree (int): The degree of a candidate surface.
        weights_a (numpy.ndarray): Triple (1D array) of barycentric weights
            for a point in the reference triangle
        weights_b (numpy.ndarray): Triple (1D array) of barycentric weights
            for a point in the reference triangle
        weights_c (numpy.ndarray): Triple (1D array) of barycentric weights
            for a point in the reference triangle

    Returns:
        Mapping[int, numpy.ndarray]: Mapping from keys to the de Casteljau
        transformation mappings. The keys are ``0`` corresponding to
        ``weights_a``, ``1`` to ``weights_b`` and ``2`` to ``weights_c``.
    """
    num_nodes = ((degree + 1) * (degree + 2)) // 2
    id_mat = _helpers.eye(num_nodes)

    # Pre-compute the matrices that do the reduction so we don't
    # have to **actually** perform the de Casteljau algorithm
    # every time.
    transform = {
        0: de_casteljau_one_round(id_mat, degree, *weights_a),
        1: de_casteljau_one_round(id_mat, degree, *weights_b),
        2: de_casteljau_one_round(id_mat, degree, *weights_c),
    }
    return transform


def reduced_to_matrix(shape, degree, vals_by_weight):
    r"""Converts a reduced values dictionary into a matrix.

    .. note::

       This is a helper used only by :func:`_specialize_surface`.

    The ``vals_by_weight`` mapping has keys of the form:
    ``(0, ..., 1, ..., 2, ...)`` where the ``0`` corresponds
    to the number of times the first set of barycentric
    weights was used in the reduction process, and similarly
    for ``1`` and ``2``.

    These points correspond to barycentric weights in their
    own right. For example ``(0, 0, 0, 1, 2, 2)`` corresponds to
    the barycentric weight
    :math:`\left(\frac{3}{6}, \frac{1}{6}, \frac{2}{6}\right)`.

    Once the keys in ``vals_by_weight`` have been converted
    to barycentric coordinates, we order them according to
    our rule (bottom to top, left to right) and then return
    them in a single matrix.

    Args:
        shape (tuple): The shape of the result matrix.
        degree (int): The degree of the surface.
        vals_by_weight (Mapping[tuple, numpy.ndarray]): Dictionary
            of reduced nodes according to blending of each of the
            three sets of weights in a reduction.

    Returns:
        numpy.ndarray: The newly created reduced control points.
    """
    result = np.empty(shape, order='F')
    index = 0
    for k in six.moves.xrange(degree + 1):
        for j in six.moves.xrange(degree + 1 - k):
            i = degree - j - k
            key = (0,) * i + (1,) * j + (2,) * k
            result[index, :] = vals_by_weight[key]
            index += 1

    return result


def _specialize_surface(nodes, degree, weights_a, weights_b, weights_c):
    """Specialize a surface to a reparameterization

    .. note::

       There is also a Fortran implementation of this function, which
       will be used if it can be built.

    Does so by taking three points (in barycentric form) within the
    reference triangle and then reparameterizing the surface onto
    the triangle formed by those three points.

    .. note::

       This assumes the surface is degree 1 or greater but doesn't check.

    .. note::

       This is used **only** as a helper for :func:`_subdivide_nodes`, however
       it may be worth adding this to :class:`Surface` as an analogue to
       :meth:`Curve.specialize`.

    Args:
        nodes (numpy.ndarray): Control points for a surface.
        degree (int): The degree of the surface.
        weights_a (numpy.ndarray): Triple (1D array) of barycentric weights
            for a point in the reference triangle
        weights_b (numpy.ndarray): Triple (1D array) of barycentric weights
            for a point in the reference triangle
        weights_c (numpy.ndarray): Triple (1D array) of barycentric weights
            for a point in the reference triangle

    Returns:
        numpy.ndarray: The control points for the specialized surface.
    """
    # Uses A-->0, B-->1, C-->2 to represent the specialization used.
    partial_vals = {
        (0,): de_casteljau_one_round(nodes, degree, *weights_a),
        (1,): de_casteljau_one_round(nodes, degree, *weights_b),
        (2,): de_casteljau_one_round(nodes, degree, *weights_c),
    }

    for reduced_deg in six.moves.xrange(degree - 1, 0, -1):
        new_partial = {}
        transform = make_transform(
            reduced_deg, weights_a, weights_b, weights_c)
        for key, sub_nodes in six.iteritems(partial_vals):
            # Our keys are ascending so we increment from the last value.
            for next_id in six.moves.xrange(key[-1], 2 + 1):
                new_key = key + (next_id,)
                new_partial[new_key] = _helpers.matrix_product(
                    transform[next_id], sub_nodes)

        partial_vals = new_partial

    return reduced_to_matrix(nodes.shape, degree, partial_vals)


def _subdivide_nodes(nodes, degree):
    """Subdivide a surface into four sub-surfaces.

    .. note::

       There is also a Fortran implementation of this function, which
       will be used if it can be built.

    Does so by taking the unit triangle (i.e. the domain of the surface) and
    splitting it into four sub-triangles by connecting the midpoints of each
    side.

    Args:
        nodes (numpy.ndarray): Control points for a surface.
        degree (int): The degree of the surface.

    Returns:
        Tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray, numpy.ndarray]: The
        nodes for the four sub-surfaces.
    """
    if degree == 1:
        nodes_a = _helpers.matrix_product(LINEAR_SUBDIVIDE_A, nodes)
        nodes_b = _helpers.matrix_product(LINEAR_SUBDIVIDE_B, nodes)
        nodes_c = _helpers.matrix_product(LINEAR_SUBDIVIDE_C, nodes)
        nodes_d = _helpers.matrix_product(LINEAR_SUBDIVIDE_D, nodes)
    elif degree == 2:
        nodes_a = _helpers.matrix_product(QUADRATIC_SUBDIVIDE_A, nodes)
        nodes_b = _helpers.matrix_product(QUADRATIC_SUBDIVIDE_B, nodes)
        nodes_c = _helpers.matrix_product(QUADRATIC_SUBDIVIDE_C, nodes)
        nodes_d = _helpers.matrix_product(QUADRATIC_SUBDIVIDE_D, nodes)
    elif degree == 3:
        nodes_a = _helpers.matrix_product(CUBIC_SUBDIVIDE_A, nodes)
        nodes_b = _helpers.matrix_product(CUBIC_SUBDIVIDE_B, nodes)
        nodes_c = _helpers.matrix_product(CUBIC_SUBDIVIDE_C, nodes)
        nodes_d = _helpers.matrix_product(CUBIC_SUBDIVIDE_D, nodes)
    elif degree == 4:
        nodes_a = _helpers.matrix_product(QUARTIC_SUBDIVIDE_A, nodes)
        nodes_b = _helpers.matrix_product(QUARTIC_SUBDIVIDE_B, nodes)
        nodes_c = _helpers.matrix_product(QUARTIC_SUBDIVIDE_C, nodes)
        nodes_d = _helpers.matrix_product(QUARTIC_SUBDIVIDE_D, nodes)
    else:
        nodes_a = specialize_surface(
            nodes, degree,
            _WEIGHTS_SUBDIVIDE0, _WEIGHTS_SUBDIVIDE1, _WEIGHTS_SUBDIVIDE2)
        nodes_b = specialize_surface(
            nodes, degree,
            _WEIGHTS_SUBDIVIDE3, _WEIGHTS_SUBDIVIDE2, _WEIGHTS_SUBDIVIDE1)
        nodes_c = specialize_surface(
            nodes, degree,
            _WEIGHTS_SUBDIVIDE1, _WEIGHTS_SUBDIVIDE4, _WEIGHTS_SUBDIVIDE3)
        nodes_d = specialize_surface(
            nodes, degree,
            _WEIGHTS_SUBDIVIDE2, _WEIGHTS_SUBDIVIDE3, _WEIGHTS_SUBDIVIDE5)

    return nodes_a, nodes_b, nodes_c, nodes_d


def jacobian_s(nodes, degree, dimension):
    r"""Compute :math:`\frac{\partial B}{\partial s}`.

    .. note::

       This is a helper for :func:`_jacobian_both`, which has an
       equivalent Fortran implementation.

    Args:
        nodes (numpy.ndarray): Array of nodes in a surface.
        degree (int): The degree of the surface.
        dimension (int): The dimension the surface lives in.

    Returns:
        numpy.ndarray: Nodes of the Jacobian surface in
            B |eacute| zier form.
    """
    num_nodes = (degree * (degree + 1)) // 2
    result = np.empty((num_nodes, dimension), order='F')

    index = 0
    i = 0
    for num_vals in six.moves.xrange(degree, 0, -1):
        for _ in six.moves.xrange(num_vals):
            result[index, :] = nodes[i + 1, :] - nodes[i, :]
            # Update the indices
            index += 1
            i += 1

        # In between each row, the index gains an extra value.
        i += 1

    return float(degree) * result


def jacobian_t(nodes, degree, dimension):
    r"""Compute :math:`\frac{\partial B}{\partial t}`.

    .. note::

       This is a helper for :func:`_jacobian_both`, which has an
       equivalent Fortran implementation.

    Args:
        nodes (numpy.ndarray): Array of nodes in a surface.
        degree (int): The degree of the surface.
        dimension (int): The dimension the surface lives in.

    Returns:
        numpy.ndarray: Nodes of the Jacobian surface in
            B |eacute| zier form.
    """
    num_nodes = (degree * (degree + 1)) // 2
    result = np.empty((num_nodes, dimension), order='F')

    index = 0
    i = 0
    j = degree + 1
    for num_vals in six.moves.xrange(degree, 0, -1):
        for _ in six.moves.xrange(num_vals):
            result[index, :] = nodes[j, :] - nodes[i, :]
            # Update the indices
            index += 1
            i += 1
            j += 1

        # In between each row, the index gains an extra value.
        i += 1

    return float(degree) * result


def _jacobian_both(nodes, degree, dimension):
    r"""Compute :math:`s` and :math:`t` partial of :math:`B`.

    .. note::

       There is also a Fortran implementation of this function, which
       will be used if it can be built.

    Args:
        nodes (numpy.ndarray): Array of nodes in a surface.
        degree (int): The degree of the surface.
        dimension (int): The dimension the surface lives in.

    Returns:
        numpy.ndarray: Nodes of the Jacobian surfaces in
            B |eacute| zier form.
    """
    num_nodes, _ = nodes.shape
    result = np.empty((num_nodes - degree - 1, 2 * dimension), order='F')
    result[:, :dimension] = jacobian_s(nodes, degree, dimension)
    result[:, dimension:] = jacobian_t(nodes, degree, dimension)
    return result


def _jacobian_det(nodes, degree, st_vals):
    r"""Compute :math:`\det(D B)` at a set of values.

    This requires that :math:`B \in \mathbf{R}^2`.

    .. note::

       This assumes but does not check that each ``(s, t)``
       in ``st_vals`` is inside the reference triangle.

    .. warning::

       This relies on helpers in :mod:`bezier` for computing the
       Jacobian of the surface. However, these helpers are not
       part of the public surface and may change or be removed.

    .. testsetup:: jacobian-det

       import numpy as np

       import bezier
       from bezier._surface_helpers import jacobian_det

    .. doctest:: jacobian-det
       :options: +NORMALIZE_WHITESPACE

       >>> nodes = np.asfortranarray([
       ...     [0.0, 0.0],
       ...     [1.0, 0.0],
       ...     [2.0, 0.0],
       ...     [0.0, 1.0],
       ...     [1.5, 1.5],
       ...     [0.0, 2.0],
       ... ])
       >>> surface = bezier.Surface(nodes, degree=2)
       >>> st_vals = np.asfortranarray([
       ...     [0.25, 0.0  ],
       ...     [0.75, 0.125],
       ...     [0.5 , 0.5  ],
       ... ])
       >>> s_vals, t_vals = st_vals.T
       >>> surface.evaluate_cartesian_multi(st_vals)
       array([[ 0.5    , 0.     ],
              [ 1.59375, 0.34375],
              [ 1.25   , 1.25   ]])
       >>> # B(s, t) = [s(t + 2), t(s + 2)]
       >>> s_vals * (t_vals + 2)
       array([ 0.5 , 1.59375, 1.25 ])
       >>> t_vals * (s_vals + 2)
       array([ 0. , 0.34375, 1.25 ])
       >>> jacobian_det(nodes, 2, st_vals)
       array([ 4.5 , 5.75, 6. ])
       >>> # det(DB) = 2(s + t + 2)
       >>> 2 * (s_vals + t_vals + 2)
       array([ 4.5 , 5.75, 6. ])

    .. note::

       There is also a Fortran implementation of this function, which
       will be used if it can be built.

    Args:
        nodes (numpy.ndarray): Nodes defining a B |eacute| zier
            surface :math:`B(s, t)`.
        degree (int): The degree of the surface :math:`B`.
        st_vals (numpy.ndarray): ``Nx2`` array of Cartesian
            inputs to B |eacute| zier surfaces defined by
            :math:`B_s` and :math:`B_t`.

    Returns:
        numpy.ndarray: Array of all determinant values, one
        for each row in ``st_vals``.
    """
    jac_nodes = jacobian_both(nodes, degree, 2)
    if degree == 1:
        num_vals, _ = st_vals.shape
        bs_bt_vals = np.repeat(jac_nodes, num_vals, axis=0)
    else:
        bs_bt_vals = evaluate_cartesian_multi(
            jac_nodes, degree - 1, st_vals, 4)

    # Take the determinant for each (s, t).
    return (bs_bt_vals[:, 0] * bs_bt_vals[:, 3] -
            bs_bt_vals[:, 1] * bs_bt_vals[:, 2])


def classify_tangent_intersection(
        intersection, nodes1, tangent1, nodes2, tangent2):
    """Helper for func:`classify_intersection` at tangencies.

    .. note::

       This is a helper used only by :func:`classify_intersection`.

    Args:
        intersection (.Intersection): An intersection object.
        nodes1 (numpy.ndarray): Control points for the first curve at
            the intersection.
        tangent1 (numpy.ndarray): The tangent vector to the first curve
            at the intersection.
        nodes2 (numpy.ndarray): Control points for the second curve at
            the intersection.
        tangent2 (numpy.ndarray): The tangent vector to the second curve
            at the intersection.

    Returns:
        IntersectionClassification: The "inside" curve type, based on
        the classification enum. Will either be ``opposed`` or one
        of the ``tangent`` values.

    Raises:
        NotImplementedError: If the curves are tangent, moving in opposite
            directions, but enclose overlapping arcs.
        NotImplementedError: If the curves are tangent at the intersection
            and have the same curvature.
    """
    # Each array is 1x2 (i.e. a row vector), we want the vector dot product.
    dot_prod = np.vdot(tangent1[0, :], tangent2[0, :])
    # NOTE: When computing curvatures we assume that we don't have lines
    #       here, because lines that are tangent at an intersection are
    #       parallel and we don't handle that case.
    curvature1 = _curve_helpers.get_curvature(nodes1, tangent1, intersection.s)
    curvature2 = _curve_helpers.get_curvature(nodes2, tangent2, intersection.t)
    if dot_prod < 0:
        # If the tangent vectors are pointing in the opposite direction,
        # then the curves are facing opposite directions.
        sign1, sign2 = _SIGN([curvature1, curvature2])
        if sign1 == sign2:
            # If both curvatures are positive, since the curves are
            # moving in opposite directions, the tangency isn't part of
            # the surface intersection.
            if sign1 == 1.0:
                return IntersectionClassification.OPPOSED
            else:
                raise NotImplementedError(_BAD_TANGENT)
        else:
            delta_c = abs(curvature1) - abs(curvature2)
            if delta_c == 0.0:
                raise NotImplementedError(_SAME_CURVATURE)
            elif sign1 == _SIGN(delta_c):
                return IntersectionClassification.OPPOSED
            else:
                raise NotImplementedError(_BAD_TANGENT)
    else:
        if curvature1 > curvature2:
            return IntersectionClassification.TANGENT_FIRST
        elif curvature1 < curvature2:
            return IntersectionClassification.TANGENT_SECOND
        else:
            raise NotImplementedError(_SAME_CURVATURE)


def ignored_edge_corner(edge_tangent, corner_tangent, corner_previous_edge):
    """Check ignored when a corner lies **inside** another edge.

    .. note::

       This is a helper used only by :func:`ignored_corner`, which in turn is
       only used by :func:`classify_intersection`.

    Helper for :func:`ignored_corner` where one of ``s`` and
    ``t`` are ``0``, but **not both**.

    Args:
        edge_tangent (numpy.ndarray): Tangent vector along the edge
            that the intersection occurs in the middle of.
        corner_tangent (numpy.ndarray): Tangent vector at the corner
            where intersection occurs (at the beginning of edge).
        corner_previous_edge (numpy.ndarray): Edge that ends at the corner
            intersection (whereas ``corner_tangent`` comes from the edge
            that **begins** at the corner intersection).

    Returns:
        bool: Indicates if the corner intersection should be ignored.
    """
    cross_prod = _helpers.cross_product(edge_tangent, corner_tangent)
    # A negative cross product indicates that ``edge_tangent`` is
    # "inside" / "to the left" of ``corner_tangent`` (due to right-hand rule).
    if cross_prod > 0.0:
        return False

    # Do the same for the **other** tangent at the corner.
    alt_corner_tangent = _curve_helpers.evaluate_hodograph(
        1.0, corner_previous_edge)
    # Change the direction of the "in" tangent so that it points "out".
    alt_corner_tangent *= -1.0
    cross_prod = _helpers.cross_product(edge_tangent, alt_corner_tangent)
    return cross_prod <= 0.0


def ignored_double_corner(intersection, tangent_s, tangent_t, edges1, edges2):
    """Check if an intersection is an "ignored" double corner.

    .. note::

       This is a helper used only by :func:`ignored_corner`, which in turn is
       only used by :func:`classify_intersection`.

    Helper for :func:`ignored_corner` where both ``s`` and
    ``t`` are ``0``.

    Does so by checking if either edge through the ``t`` corner goes
    through the interior of the other surface. An interior check
    is done by checking that a few cross products are positive.

    Args:
        intersection (.Intersection): An intersection to "diagnose".
        tangent_s (numpy.ndarray): The tangent vector to the first curve
            at the intersection.
        tangent_t (numpy.ndarray): The tangent vector to the second curve
            at the intersection.
        edges1 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the first surface being intersected.
        edges2 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the second surface being intersected.

    Returns:
        bool: Indicates if the corner is to be ignored.
    """
    # Compute the other edge for the ``s`` surface.
    prev_index = (intersection.index_first - 1) % 3
    prev_edge = edges1[prev_index]
    alt_tangent_s = _curve_helpers.evaluate_hodograph(
        1.0, prev_edge._nodes)

    # First check if ``tangent_t`` is interior to the ``s`` surface.
    cross_prod1 = _helpers.cross_product(tangent_s, tangent_t)
    # A positive cross product indicates that ``tangent_t`` is
    # interior to ``tangent_s``. Similar for ``alt_tangent_s``.
    # If ``tangent_t`` is interior to both, then the surfaces
    # do more than just "kiss" at the corner, so the corner should
    # not be ignored.
    if cross_prod1 >= 0.0:
        # Only compute ``cross_prod2`` if we need to.
        cross_prod2 = _helpers.cross_product(alt_tangent_s, tangent_t)
        if cross_prod2 >= 0.0:
            return False

    # If ``tangent_t`` is not interior, we check the other ``t``
    # edge that ends at the corner.
    prev_index = (intersection.index_second - 1) % 3
    prev_edge = edges2[prev_index]
    alt_tangent_t = _curve_helpers.evaluate_hodograph(
        1.0, prev_edge._nodes)
    # Change the direction of the "in" tangent so that it points "out".
    alt_tangent_t *= -1.0

    cross_prod3 = _helpers.cross_product(tangent_s, alt_tangent_t)
    if cross_prod3 >= 0.0:
        # Only compute ``cross_prod4`` if we need to.
        cross_prod4 = _helpers.cross_product(alt_tangent_s, alt_tangent_t)
        if cross_prod4 >= 0.0:
            return False

    # If neither of ``tangent_t`` or ``alt_tangent_t`` are interior
    # to the ``s`` surface, one of two things is true. Either
    # the two surfaces have no interior intersection (1) or the
    # ``s`` surface is bounded by both edges of the ``t`` surface
    # at the corner intersection (2). To detect (2), we only need
    # check if ``tangent_s`` is interior to both ``tangent_t``
    # and ``alt_tangent_t``. ``cross_prod1`` contains
    # (tangent_s) x (tangent_t), so it's negative will tell if
    # ``tangent_s`` is interior. Similarly, ``cross_prod3``
    # contains (tangent_s) x (alt_tangent_t), but we also reversed
    # the sign on ``alt_tangent_t`` so switching the sign back
    # and reversing the arguments in the cross product cancel out.
    return not (cross_prod1 <= 0.0 and cross_prod3 >= 0.0)


def ignored_corner(intersection, tangent_s, tangent_t, edges1, edges2):
    """Check if an intersection is an "ignored" corner.

    .. note::

       This is a helper used only by :func:`classify_intersection`.

    An "ignored" corner is one where the surfaces just "kiss" at
    the point of intersection but their interiors do not meet.

    We can determine this by comparing the tangent lines from
    the point of intersection.

    .. note::

       This assumes the ``intersection`` has been shifted to the
       beginning of a curve so only checks if ``s == 0.0`` or ``t == 0.0``
       (rather than also checking for ``1.0``).

    .. note::

       This assumes the first and second curves in ``intersection`` are edges
       in a surface, so the code relies on ``previous_edge`` being valid.

    Args:
        intersection (.Intersection): An intersection to "diagnose".
        tangent_s (numpy.ndarray): The tangent vector to the first curve
            at the intersection.
        tangent_t (numpy.ndarray): The tangent vector to the second curve
            at the intersection.
        edges1 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the first surface being intersected.
        edges2 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the second surface being intersected.

    Returns:
        bool: Indicates if the corner is to be ignored.
    """
    if intersection.s == 0.0:
        if intersection.t == 0.0:
            # Double corner.
            return ignored_double_corner(
                intersection, tangent_s, tangent_t, edges1, edges2)
        else:
            # s-only corner.
            prev_index = (intersection.index_first - 1) % 3
            prev_edge = edges1[prev_index]
            return ignored_edge_corner(tangent_t, tangent_s, prev_edge._nodes)
    elif intersection.t == 0.0:
        # t-only corner.
        prev_index = (intersection.index_second - 1) % 3
        prev_edge = edges2[prev_index]
        return ignored_edge_corner(tangent_s, tangent_t, prev_edge._nodes)
    else:
        # Not a corner.
        return False


def classify_intersection(intersection, edges1, edges2):
    r"""Determine which curve is on the "inside of the intersection".

    .. note::

       This is a helper used only by :meth:`.Surface.intersect`.

    This is intended to be a helper for forming a :class:`.CurvedPolygon`
    from the edge intersections of two :class:`.Surface`-s. In order
    to move from one intersection to another (or to the end of an edge),
    the interior edge must be determined at the point of intersection.

    The "typical" case is on the interior of both edges:

    .. image:: images/classify_intersection1.png
       :align: center

    .. testsetup:: classify-intersection1, classify-intersection2,
                   classify-intersection3, classify-intersection4,
                   classify-intersection5, classify-intersection6,
                   classify-intersection7, classify-intersection8

       import numpy as np
       import bezier
       from bezier import _curve_helpers
       from bezier._intersection_helpers import Intersection
       from bezier._surface_helpers import classify_intersection

       def hodograph(curve, s):
           return _curve_helpers.evaluate_hodograph(
               s, curve._nodes)

       def curvature(curve, s):
           nodes = curve._nodes
           tangent = _curve_helpers.evaluate_hodograph(
               s, nodes)
           return _curve_helpers.get_curvature(
               nodes, tangent, s)

    .. doctest:: classify-intersection1
       :options: +NORMALIZE_WHITESPACE

       >>> nodes1 = np.asfortranarray([
       ...     [1.0 , 0.0 ],
       ...     [1.75, 0.25],
       ...     [2.0 , 1.0 ],
       ... ])
       >>> curve1 = bezier.Curve(nodes1, degree=2)
       >>> nodes2 = np.asfortranarray([
       ...     [0.0   , 0.0   ],
       ...     [1.6875, 0.0625],
       ...     [2.0   , 0.5   ],
       ... ])
       >>> curve2 = bezier.Curve(nodes2, degree=2)
       >>> s, t = 0.25, 0.5
       >>> curve1.evaluate(s) == curve2.evaluate(t)
       array([[ True, True]], dtype=bool)
       >>> tangent1 = hodograph(curve1, s)
       >>> tangent1
       array([[ 1.25, 0.75]])
       >>> tangent2 = hodograph(curve2, t)
       >>> tangent2
       array([[ 2. , 0.5]])
       >>> intersection = Intersection(0, s, 0, t)
       >>> edges1 = (curve1, None, None)
       >>> edges2 = (curve2, None, None)
       >>> classify_intersection(intersection, edges1, edges2)
       <IntersectionClassification.FIRST: 0>

    .. testcleanup:: classify-intersection1

       import make_images
       make_images.classify_intersection1(
           s, curve1, tangent1, curve2, tangent2)

    We determine the interior (i.e. left) one by using the `right-hand rule`_:
    by embedding the tangent vectors in :math:`\mathbf{R}^3`, we
    compute

    .. _right-hand rule: https://en.wikipedia.org/wiki/Right-hand_rule

    .. math::

       \left[\begin{array}{c}
           x_1'(s) \\ y_1'(s) \\ 0 \end{array}\right] \times
       \left[\begin{array}{c}
           x_2'(t) \\ y_2'(t) \\ 0 \end{array}\right] =
       \left[\begin{array}{c}
           0 \\ 0 \\ x_1'(s) y_2'(t) - x_2'(t) y_1'(s) \end{array}\right].

    If the cross product quantity
    :math:`B_1'(s) \times B_2'(t) = x_1'(s) y_2'(t) - x_2'(t) y_1'(s)`
    is positive, then the first curve is "outside" / "to the right", i.e.
    the second curve is interior. If the cross product is negative, the
    first curve is interior.

    When :math:`B_1'(s) \times B_2'(t) = 0`, the tangent
    vectors are parallel, i.e. the intersection is a point of tangency:

    .. image:: images/classify_intersection2.png
       :align: center

    .. doctest:: classify-intersection2
       :options: +NORMALIZE_WHITESPACE

       >>> nodes1 = np.asfortranarray([
       ...     [1.0, 0.0],
       ...     [1.5, 1.0],
       ...     [2.0, 0.0],
       ... ])
       >>> curve1 = bezier.Curve(nodes1, degree=2)
       >>> nodes2 = np.asfortranarray([
       ...     [0.0, 0.0],
       ...     [1.5, 1.0],
       ...     [3.0, 0.0],
       ... ])
       >>> curve2 = bezier.Curve(nodes2, degree=2)
       >>> s, t = 0.5, 0.5
       >>> curve1.evaluate(s) == curve2.evaluate(t)
       array([[ True, True]], dtype=bool)
       >>> intersection = Intersection(0, s, 0, t)
       >>> edges1 = (curve1, None, None)
       >>> edges2 = (curve2, None, None)
       >>> classify_intersection(intersection, edges1, edges2)
       <IntersectionClassification.TANGENT_SECOND: 4>

    .. testcleanup:: classify-intersection2

       import make_images
       make_images.classify_intersection2(s, curve1, curve2)

    Depending on the direction of the parameterizations, the interior
    curve may change, but we can use the (signed) `curvature`_ of each
    curve at that point to determine which is on the interior:

    .. _curvature: https://en.wikipedia.org/wiki/Curvature

    .. image:: images/classify_intersection3.png
       :align: center

    .. doctest:: classify-intersection3
       :options: +NORMALIZE_WHITESPACE

       >>> nodes1 = np.asfortranarray([
       ...     [2.0, 0.0],
       ...     [1.5, 1.0],
       ...     [1.0, 0.0],
       ... ])
       >>> curve1 = bezier.Curve(nodes1, degree=2)
       >>> nodes2 = np.asfortranarray([
       ...     [3.0, 0.0],
       ...     [1.5, 1.0],
       ...     [0.0, 0.0],
       ... ])
       >>> curve2 = bezier.Curve(nodes2, degree=2)
       >>> s, t = 0.5, 0.5
       >>> curve1.evaluate(s) == curve2.evaluate(t)
       array([[ True, True]], dtype=bool)
       >>> intersection = Intersection(0, s, 0, t)
       >>> edges1 = (curve1, None, None)
       >>> edges2 = (curve2, None, None)
       >>> classify_intersection(intersection, edges1, edges2)
       <IntersectionClassification.TANGENT_FIRST: 3>

    .. testcleanup:: classify-intersection3

       import make_images
       make_images.classify_intersection3(s, curve1, curve2)

    When the curves are moving in opposite directions at a point
    of tangency, there is no side to choose. Either the point of tangency
    is not part of any :class:`.CurvedPolygon` intersection

    .. image:: images/classify_intersection4.png
       :align: center

    .. doctest:: classify-intersection4
       :options: +NORMALIZE_WHITESPACE

       >>> nodes1 = np.asfortranarray([
       ...     [2.0, 0.0],
       ...     [1.5, 1.0],
       ...     [1.0, 0.0],
       ... ])
       >>> curve1 = bezier.Curve(nodes1, degree=2)
       >>> nodes2 = np.asfortranarray([
       ...     [0.0, 0.0],
       ...     [1.5, 1.0],
       ...     [3.0, 0.0],
       ... ])
       >>> curve2 = bezier.Curve(nodes2, degree=2)
       >>> s, t = 0.5, 0.5
       >>> curve1.evaluate(s) == curve2.evaluate(t)
       array([[ True, True]], dtype=bool)
       >>> intersection = Intersection(0, s, 0, t)
       >>> edges1 = (curve1, None, None)
       >>> edges2 = (curve2, None, None)
       >>> classify_intersection(intersection, edges1, edges2)
       <IntersectionClassification.OPPOSED: 2>

    .. testcleanup:: classify-intersection4

       import make_images
       make_images.classify_intersection4(s, curve1, curve2)

    or the point of tangency is a "degenerate" part of two
    :class:`.CurvedPolygon` intersections. It is "degenerate"
    because from one direction, the point should be classified as
    :attr:`~._IntersectionClassification.FIRST` and from another as
    :attr:`~._IntersectionClassification.SECOND`.

    .. image:: images/classify_intersection5.png
       :align: center

    .. doctest:: classify-intersection5
       :options: +NORMALIZE_WHITESPACE

       >>> nodes1 = np.asfortranarray([
       ...     [1.0, 0.0],
       ...     [1.5, 1.0],
       ...     [2.0, 0.0],
       ... ])
       >>> curve1 = bezier.Curve(nodes1, degree=2)
       >>> nodes2 = np.asfortranarray([
       ...     [3.0, 0.0],
       ...     [1.5, 1.0],
       ...     [0.0, 0.0],
       ... ])
       >>> curve2 = bezier.Curve(nodes2, degree=2)
       >>> s, t = 0.5, 0.5
       >>> curve1.evaluate(s) == curve2.evaluate(t)
       array([[ True, True]], dtype=bool)
       >>> intersection = Intersection(0, s, 0, t)
       >>> edges1 = (curve1, None, None)
       >>> edges2 = (curve2, None, None)
       >>> classify_intersection(intersection, edges1, edges2)
       Traceback (most recent call last):
         ...
       NotImplementedError: Curves moving in opposite direction
                            but define overlapping arcs.

    .. testcleanup:: classify-intersection5

       import make_images
       make_images.classify_intersection5(s, curve1, curve2)

    However, if the `curvature`_ of each curve is identical, we
    don't try to distinguish further:

    .. image:: images/classify_intersection6.png
       :align: center

    .. doctest:: classify-intersection6
       :options: +NORMALIZE_WHITESPACE

       >>> nodes1 = np.asfortranarray([
       ...     [ 0.375,  0.0625],
       ...     [-0.125, -0.0625],
       ...     [-0.125,  0.0625],
       ... ])
       >>> curve1 = bezier.Curve(nodes1, degree=2)
       >>> nodes2 = np.asfortranarray([
       ...     [ 0.75,  0.25],
       ...     [-0.25, -0.25],
       ...     [-0.25,  0.25],
       ... ])
       >>> curve2 = bezier.Curve(nodes2, degree=2)
       >>> s, t = 0.5, 0.5
       >>> curve1.evaluate(s) == curve2.evaluate(t)
       array([[ True, True]], dtype=bool)
       >>> hodograph(curve1, s)
       array([[-0.5, 0. ]])
       >>> hodograph(curve2, t)
       array([[-1., 0.]])
       >>> curvature(curve1, s)
       -2.0
       >>> curvature(curve2, t)
       -2.0
       >>> intersection = Intersection(0, s, 0, t)
       >>> edges1 = (curve1, None, None)
       >>> edges2 = (curve2, None, None)
       >>> classify_intersection(intersection, edges1, edges2)
       Traceback (most recent call last):
         ...
       NotImplementedError: Tangent curves have same curvature.

    .. testcleanup:: classify-intersection6

       import make_images
       make_images.classify_intersection6(s, curve1, curve2)

    In addition to points of tangency, intersections that happen at
    the end of an edge need special handling:

    .. image:: images/classify_intersection7.png
       :align: center

    .. doctest:: classify-intersection7
       :options: +NORMALIZE_WHITESPACE

       >>> nodes1a = np.asfortranarray([
       ...     [0.0, 0.0 ],
       ...     [4.5, 0.0 ],
       ...     [9.0, 2.25],
       ... ])
       >>> curve1a = bezier.Curve(nodes1a, degree=2)
       >>> nodes2 = np.asfortranarray([
       ...     [11.25, 0.0],
       ...     [ 9.0 , 4.5],
       ...     [ 2.75, 1.0],
       ... ])
       >>> curve2 = bezier.Curve(nodes2, degree=2)
       >>> s, t = 1.0, 0.375
       >>> curve1a.evaluate(s) == curve2.evaluate(t)
       array([[ True, True]], dtype=bool)
       >>> intersection = Intersection(0, s, 0, t)
       >>> edges1 = (curve1a, None, None)
       >>> edges2 = (curve2, None, None)
       >>> classify_intersection(intersection, edges1, edges2)
       Traceback (most recent call last):
         ...
       ValueError: ('Intersection occurs at the end of an edge',
                    's', 1.0, 't', 0.375)
       >>>
       >>> nodes1b = np.asfortranarray([
       ...     [9.0, 2.25 ],
       ...     [4.5, 2.375],
       ...     [0.0, 2.5  ],
       ... ])
       >>> curve1b = bezier.Curve(nodes1b, degree=2)
       >>> curve1b.evaluate(0.0) == curve2.evaluate(t)
       array([[ True, True]], dtype=bool)
       >>> edges1 = (curve1a, curve1b, None)
       >>> intersection = Intersection(1, 0.0, 0, t)
       >>> edges1 = (curve1a, curve1b, None)
       >>> classify_intersection(intersection, edges1, edges2)
       <IntersectionClassification.FIRST: 0>

    .. testcleanup:: classify-intersection7

       import make_images
       make_images.classify_intersection7(s, curve1a, curve1b, curve2)

    As above, some intersections at the end of an edge are part of
    an actual intersection. However, some surfaces may just "kiss" at a
    corner intersection:

    .. image:: images/classify_intersection8.png
       :align: center

    .. doctest:: classify-intersection8
       :options: +NORMALIZE_WHITESPACE

       >>> nodes1 = np.asfortranarray([
       ...     [0.25 , 1.0  ],
       ...     [0.0  , 0.5  ],
       ...     [0.0  , 0.0  ],
       ...     [0.625, 0.875],
       ...     [0.5  , 0.375],
       ...     [1.0  , 0.75 ],
       ... ])
       >>> surface1 = bezier.Surface(nodes1, degree=2)
       >>> nodes2 = np.asfortranarray([
       ...     [ 0.0625, 0.5  ],
       ...     [-0.25  , 1.0  ],
       ...     [-1.0   , 1.0  ],
       ...     [-0.5   , 0.125],
       ...     [-1.0   , 0.5  ],
       ...     [-1.0   , 0.0  ],
       ... ])
       >>> surface2 = bezier.Surface(nodes2, degree=2)
       >>> edges1 = surface1.edges
       >>> curve1, _, _ = edges1
       >>> edges2 = surface2.edges
       >>> curve2, _, _ = edges2
       >>> s, t = 0.5, 0.0
       >>> curve1.evaluate(s) == curve2.evaluate(t)
       array([[ True, True]], dtype=bool)
       >>> intersection = Intersection(0, s, 0, t)
       >>> classify_intersection(intersection, edges1, edges2)
       <IntersectionClassification.IGNORED_CORNER: 5>

    .. testcleanup:: classify-intersection8

       import make_images
       make_images.classify_intersection8(
           s, curve1, surface1, curve2, surface2)

    .. note::

       This assumes the intersection occurs in :math:`\mathbf{R}^2`
       but doesn't check this.

    .. note::

       This function doesn't allow wiggle room / round-off when checking
       endpoints, nor when checking if the cross product is near zero,
       nor when curvatures are compared. However, the most "correct"
       version of this function likely should allow for some round off.

    Args:
        intersection (.Intersection): An intersection object.
        edges1 (Tuple[~bezier.curve.Curve, ...]): The three edges of the
            first surface being intersected.
        edges2 (Tuple[~bezier.curve.Curve, ...]): The three edges of the
            second surface being intersected.

    Returns:
        _IntersectionClassification: The "inside" curve type, based on
        the classification enum.

    Raises:
        ValueError: If the intersection occurs at the end of either
            curve involved. This is because we want to classify which
            curve to **move forward** on, and we can't move past the
            end of a segment.
    """
    if intersection.s == 1.0 or intersection.t == 1.0:
        raise ValueError('Intersection occurs at the end of an edge',
                         's', intersection.s, 't', intersection.t)

    nodes1 = edges1[intersection.index_first]._nodes
    tangent1 = _curve_helpers.evaluate_hodograph(intersection.s, nodes1)
    nodes2 = edges2[intersection.index_second]._nodes
    tangent2 = _curve_helpers.evaluate_hodograph(intersection.t, nodes2)

    if ignored_corner(intersection, tangent1, tangent2, edges1, edges2):
        return IntersectionClassification.IGNORED_CORNER

    # Take the cross product of tangent vectors to determine which one
    # is more "inside" / "to the left".
    cross_prod = _helpers.cross_product(tangent1, tangent2)
    if cross_prod < 0:
        return IntersectionClassification.FIRST
    elif cross_prod > 0:
        return IntersectionClassification.SECOND
    else:
        return classify_tangent_intersection(
            intersection, nodes1, tangent1, nodes2, tangent2)


def handle_ends(index1, s, index2, t):
    """Updates intersection parameters if it is on the end of an edge.

    .. note::

       This is a helper used only by :meth:`.Surface.intersect`.

    Does nothing if the intersection happens in the middle of two
    edges.

    If the intersection occurs at the end of the first curve,
    moves it to the beginning of the next edge. Similar for the
    second curve.

    This function is used as a pre-processing step before passing
    an intersection to :func:`classify_intersection`. There, only
    corners that **begin** an edge are considered, since that
    function is trying to determine which edge to **move forward** on.

    Args:
        index1 (int): The index (among 0, 1, 2) of the first edge in the
            intersection.
        s (float): The parameter along the first curve of the intersection.
        index2 (int): The index (among 0, 1, 2) of the second edge in the
            intersection.
        t (float): The parameter along the second curve of the intersection.

    Returns:
        Tuple[bool, Tuple[int, float, int, float]]: A pair of:

        * flag indicating if the intersection is at the end of an edge
        * 4-tuple of the "updated" values ``(index1, s, index2, t)``
    """
    edge_end = False
    if s == 1.0:
        s = 0.0
        index1 = (index1 + 1) % 3
        edge_end = True
    if t == 1.0:
        t = 0.0
        index2 = (index2 + 1) % 3
        edge_end = True

    return edge_end, (index1, s, index2, t)


def same_intersection(intersection1, intersection2, wiggle=0.5**40):
    """Check if two intersections are close to machine precision.

    .. note::

       This is a helper used only by :func:`verify_duplicates`, which in turn
       is only used by :meth:`.Surface.intersect`.

    Args:
        intersection1 (.Intersection): The first intersection.
        intersection2 (.Intersection): The second intersection.
        wiggle (Optional[float]): The amount of relative error allowed
            in parameter values.

    Returns:
        bool: Indicates if the two intersections are the same to
        machine precision.
    """
    # pylint: disable=protected-access
    if intersection1.index_first != intersection2.index_first:
        return False
    if intersection1.index_second != intersection2.index_second:
        return False
    # pylint: enable=protected-access

    return np.allclose(
        [intersection1.s, intersection1.t],
        [intersection2.s, intersection2.t],
        atol=0.0, rtol=wiggle)


def verify_duplicates(duplicates, uniques):
    """Verify that a set of intersections had expected duplicates.

    .. note::

       This is a helper used only by :meth:`.Surface.intersect`.

    Args:
        duplicates (List[.Intersection]): List of intersections
            corresponding to duplicates that were filtered out.
        uniques (List[.Intersection]): List of "final" intersections
            with duplicates filtered out.

    Raises:
        ValueError: If the ``uniques`` are not actually all unique.
        ValueError: If one of the ``duplicates`` does not correspond to
            an intersection in ``uniques``.
        ValueError: If a duplicate occurs only once but does not have
            exactly one of ``s`` and ``t`` equal to ``0.0``.
        ValueError: If a duplicate occurs three times but does not have
            exactly both ``s == t == 0.0``.
        ValueError: If a duplicate occurs a number other than one or three
            times.
    """
    for uniq1, uniq2 in itertools.combinations(uniques, 2):
        if same_intersection(uniq1, uniq2):
            raise ValueError('Non-unique intersection')

    counter = collections.Counter()
    for dupe in duplicates:
        matches = []
        for index, uniq in enumerate(uniques):
            if same_intersection(dupe, uniq):
                matches.append(index)

        if len(matches) != 1:
            raise ValueError('Duplicate not among uniques', dupe)

        matched = matches[0]
        counter[matched] += 1

    for index, count in six.iteritems(counter):
        uniq = uniques[index]
        if count == 1:
            if (uniq.s, uniq.t).count(0.0) != 1:
                raise ValueError('Count == 1 should be a single corner', uniq)
        elif count == 3:
            if (uniq.s, uniq.t) != (0.0, 0.0):
                raise ValueError('Count == 3 should be a double corner', uniq)
        else:
            raise ValueError('Unexpected duplicate count', count)


def to_front(intersection, intersections, unused):
    """Rotates a node to the "front".

    .. note::

       This is a helper used only by :func:`basic_interior_combine`, which in
       turn is only used by :func:`combine_intersections`.

    If a node is at the end of a segment, moves it to the beginning
    of the next segment (at the exact same point).

    .. note::

        This method checks for **exact** endpoints, i.e. parameter
        bitwise identical to ``1.0``. But we should probably allow
        some wiggle room.

    Args:
        intersection (.Intersection): The current intersection.
        intersections (List[.Intersection]): List of all detected
            intersections, provided as a reference for potential
            points to arrive at.
        unused (List[.Intersection]): List of nodes that haven't been
            used yet in an intersection curved polygon

    Returns:
        .Intersection: An intersection to (maybe) move to the beginning
        of the next segment(s).
    """
    changed = False
    if intersection.s == 1.0:
        changed = True
        next_index = (intersection.index_first + 1) % 3
        intersection = _intersection_helpers.Intersection(
            next_index, 0.0, intersection.index_second, intersection.t,
            interior_curve=intersection.interior_curve)

    if intersection.t == 1.0:
        changed = True
        next_index = (intersection.index_second + 1) % 3
        intersection = _intersection_helpers.Intersection(
            intersection.index_first, intersection.s, next_index, 0.0,
            interior_curve=intersection.interior_curve)

    if changed:
        # Make sure we haven't accidentally ignored an existing intersection.
        for other_int in intersections:
            if (other_int.s == intersection.s and
                    other_int.index_first == intersection.index_first):
                intersection = other_int
                break

            if (other_int.t == intersection.t and
                    other_int.index_second == intersection.index_second):
                intersection = other_int
                break

    if intersection in unused:
        unused.remove(intersection)
    return intersection


def get_next_first(intersection, intersections):
    """Gets the next node along the current (first) edge.

    .. note::

       This is a helper used only by :func:`get_next`, which in
       turn is only used by :func:`basic_interior_combine`, which itself
       is only used by :func:`combine_intersections`.

    Along with :func:`get_next_second`, this function does the majority of the
    heavy lifting in :func:`get_next`. **Very** similar to
    :func:`get_next_second`, but this works with the first curve while the
    other function works with the second.

    Args:
        intersection (.Intersection): The current intersection.
        intersections (List[.Intersection]): List of all detected
            intersections, provided as a reference for potential
            points to arrive at.

    Returns:
        .Intersection: The "next" point along a surface of intersection.
        This will produce the next intersection along the current (first)
        edge or the end of the same edge.
    """
    along_edge = None
    index_first = intersection.index_first
    s = intersection.s
    for other_int in intersections:
        other_s = other_int.s
        if other_int.index_first == index_first and other_s > s:
            # NOTE: We skip tangent intersections that don't occur
            #       at a corner.
            if (other_s < 1.0 and
                    other_int.interior_curve not in _ACCEPTABLE):
                continue
            if along_edge is None or other_s < along_edge.s:
                along_edge = other_int

    if along_edge is None:
        # If there is no other intersection on the edge, just return
        # the segment end.
        return _intersection_helpers.Intersection(
            index_first, 1.0, None, None,
            interior_curve=IntersectionClassification.FIRST)
    else:
        return along_edge


def get_next_second(intersection, intersections):
    """Gets the next node along the current (second) edge.

    .. note::

       This is a helper used only by :func:`get_next`, which in
       turn is only used by :func:`basic_interior_combine`, which itself
       is only used by :func:`combine_intersections`.

    Along with :func:`get_next_first`, this function does the majority of the
    heavy lifting in :func:`get_next`. **Very** similar to
    :func:`get_next_first`, but this works with the second curve while the
    other function works with the first.

    Args:
        intersection (.Intersection): The current intersection.
        intersections (List[.Intersection]): List of all detected
            intersections, provided as a reference for potential
            points to arrive at.

    Returns:
        .Intersection: The "next" point along a surface of intersection.
        This will produce the next intersection along the current (second)
        edge or the end of the same edge.
    """
    along_edge = None
    index_second = intersection.index_second
    t = intersection.t
    for other_int in intersections:
        other_t = other_int.t
        if other_int.index_second == index_second and other_t > t:
            # NOTE: We skip tangent intersections that don't occur
            #       at a corner.
            if (other_t < 1.0 and
                    other_int.interior_curve not in _ACCEPTABLE):
                continue
            if along_edge is None or other_t < along_edge.t:
                along_edge = other_int

    if along_edge is None:
        # If there is no other intersection on the edge, just return
        # the segment end.
        return _intersection_helpers.Intersection(
            None, None, index_second, 1.0,
            interior_curve=IntersectionClassification.SECOND)
    else:
        return along_edge


def get_next(intersection, intersections, unused):
    """Gets the next node along a given edge.

    .. note::

       This is a helper used only by :func:`basic_interior_combine`, which in
       turn is only used by :func:`combine_intersections`. This function does
       the majority of the heavy lifting for :func:`basic_interior_combine`.

    .. note::

        This function returns :class:`.Intersection` objects even
        when the point isn't strictly an intersection. This is
        "incorrect" in some sense, but for now, we don't bother
        implementing a class similar to, but different from,
        :class:`.Intersection` to satisfy this need.

    Args:
        intersection (.Intersection): The current intersection.
        intersections (List[.Intersection]): List of all detected
            intersections, provided as a reference for potential
            points to arrive at.
        unused (List[.Intersection]): List of nodes that haven't been
            used yet in an intersection curved polygon

    Returns:
        .Intersection: The "next" point along a surface of intersection.
        This will produce the next intersection along the current edge or
        the end of the current edge.

    Raises:
        ValueError: If the intersection is not classified as
            :attr:`~._IntersectionClassification.FIRST` or
            :attr:`~._IntersectionClassification.SECOND`.
    """
    result = None
    if intersection.interior_curve == IntersectionClassification.FIRST:
        result = get_next_first(intersection, intersections)
    elif intersection.interior_curve == IntersectionClassification.SECOND:
        result = get_next_second(intersection, intersections)
    else:
        raise ValueError('Cannot get next node if not starting from '
                         '"first" or "second".')

    if result in unused:
        unused.remove(result)
    return result


def ends_to_curve(start_node, end_node):
    """Convert a "pair" of intersection nodes to a curve segment.

    .. note::

       This is a helper used only by :func:`basic_interior_combine`, which in
       turn is only used by :func:`combine_intersections`.

    .. note::

       This function could specialize to the first or second segment
       attached to ``start_node`` and ``end_node``. We determine
       first / second based on the classification of ``start_node``,
       but the callers of this function could provide that information /
       isolate the base curve and the two parameters for us.

    .. note::

       This only checks the classification of the ``start_node``.

    Args:
        start_node (.Intersection): The beginning of a segment.
        end_node (.Intersection): The end of (the same) segment.

    Returns:
        Tuple[bool, int, float, float]: The 4-tuple of:

        * Flag indicating if the edge comes from the first (:data:`True`)
          or second (:data:`False`) surface
        * The edge index along that surface
        * The start parameter along the edge
        * The end parameter along the edge

    Raises:
        ValueError: If the ``start_node`` and ``end_node`` disagree on
            the first curve when classified as "first" or disagree on
            the second curve when classified as "second".
        ValueError: If the ``start_node`` is not classified as
            :attr:`~._IntersectionClassification.FIRST` or
            :attr:`~._IntersectionClassification.SECOND`.
    """
    if start_node.interior_curve == IntersectionClassification.FIRST:
        if end_node.index_first != start_node.index_first:
            raise ValueError(_WRONG_CURVE)
        return True, start_node.index_first, start_node.s, end_node.s
    elif start_node.interior_curve == IntersectionClassification.SECOND:
        if end_node.index_second != start_node.index_second:
            raise ValueError(_WRONG_CURVE)
        return False, start_node.index_second, start_node.t, end_node.t
    else:
        raise ValueError('Segment start must be classified as '
                         '"FIRST" or "SECOND".')


def no_intersections(surface1, surface2):
    r"""Determine if one surface is in the other.

    Helper for :func:`combine_intersections` that handles the case
    of no points of intersection. In this case, either the surfaces
    are disjoint or one is fully contained in the other.

    To check containment, it's enough to check if one of the corners
    is contained in the other surface.

    Args:
        surface1 (.Surface): First surface in intersection (assumed in
            :math:\mathbf{R}^2`).
        surface2 (.Surface): Second surface in intersection (assumed in
            :math:\mathbf{R}^2`).

    Returns:
        list: Either an empty list if one surface isn't contained
        in the other. Otherwise, the list will have a single
        :class:`.Surface` corresponding to the internal surface.
    """
    # NOTE: We want the nodes to be 1x2 but accessing ``nodes1[[0], :]``
    #       and ``nodes2[[0], :]`` makes a copy while the accesses
    #       below **do not** copy. See
    #       (https://docs.scipy.org/doc/numpy-1.6.0/reference/
    #        arrays.indexing.html#advanced-indexing)
    corner1 = surface1._nodes[0, :].reshape((1, 2), order='F')
    if surface2.locate(corner1, _verify=False) is not None:
        return [surface1]

    corner2 = surface2._nodes[0, :].reshape((1, 2), order='F')
    if surface1.locate(corner2, _verify=False) is not None:
        return [surface2]

    return []


def tangent_only_intersections(intersections, surface1, surface2):
    """Determine intersection in the case of only-tangent intersections.

    If the only intersections are tangencies, then either the surfaces
    are tangent but don't meet ("kissing" edges) or one surface is
    internally tangent to the other.

    Thus we expect every intersection in ``intersections`` to be
    classified as :attr:`~._IntersectionClassification.TANGENT_FIRST`,
    :attr:`~._IntersectionClassification.TANGENT_SECOND` or
    :attr:`~._IntersectionClassification.OPPOSED`.

    What's more, we expect all intersections to be classified the same for
    a given pairing.

    Args:
        intersections (List[.Intersection]): Intersections from each of the
            9 edge-edge pairs from a surface-surface pairing.
        surface1 (.Surface): First surface in intersection.
        surface2 (.Surface): Second surface in intersection.

    Returns:
        list: Either an empty list if one surface isn't contained
        in the other. Otherwise, the list will have a single
        :class:`.Surface` corresponding to the internal surface.

    Raises:
        ValueError: If there are intersections of more than one type among
            :attr:`~._IntersectionClassification.TANGENT_FIRST`,
            :attr:`~._IntersectionClassification.TANGENT_SECOND`,
            :attr:`~._IntersectionClassification.OPPOSED` or
            :attr:`~._IntersectionClassification.IGNORED_CORNER`.
        ValueError: If there is a unique classification, but it isn't one
            of the tangent types.
    """
    all_types = set([intersection.interior_curve
                     for intersection in intersections])
    if len(all_types) != 1:
        raise ValueError('Unexpected value, types should all match',
                         all_types)
    point_type = all_types.pop()
    if point_type == IntersectionClassification.OPPOSED:
        return []
    elif point_type == IntersectionClassification.IGNORED_CORNER:
        return []
    elif point_type == IntersectionClassification.TANGENT_FIRST:
        return [surface1]
    elif point_type == IntersectionClassification.TANGENT_SECOND:
        return [surface2]
    else:
        raise ValueError('Point type not for tangency', point_type)


def make_intersection(edge_info, surface1, edges1, surface2, edges2):
    """Convert a description of edges into a curved polygon.

    .. note::

       This is a helper used only by :func:`basic_interior_combine`, which in
       turn is only used by :func:`combine_intersections`.

    Args:
        edge_info (Tuple[Tuple[bool, int, float, float], ...]): Information
            describing each edge in the curved polygon by indicating which
            surface (first or second?), which edge on the surface and then
            start and end parameters along that edge.
        surface1 (.Surface): First surface in intersection.
        edges1 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the first surface being intersected.
        surface2 (.Surface): Second surface in intersection.
        edges2 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the second surface being intersected.

    Returns:
        Union[.CurvedPolygon, .Surface]: The intersection corresponding to
        ``edge_info``. If ``edge_info`` simply contains the edges of the
        first or second surface, will return ``surface1`` or ``surface2``
        (depending on which is correct) instead of a curved polygon.
    """
    if edge_info in FIRST_SURFACE_INFO:
        return surface1
    elif edge_info in SECOND_SURFACE_INFO:
        return surface2
    else:
        edges = []
        for first, index, start, end in edge_info:
            if first:
                edge = edges1[index].specialize(start, end)
            else:
                edge = edges2[index].specialize(start, end)
            edges.append(edge)

        return curved_polygon.CurvedPolygon(*edges, _verify=False)


def basic_interior_combine(
        intersections, surface1, edges1, surface2, edges2, max_edges=10):
    """Combine intersections that don't involve tangencies.

    .. note::

       This is a helper used only by :func:`combine_intersections`.

    .. note::

       This helper assumes ``intersections`` isn't empty, but doesn't
       enforce it.

    Args:
        intersections (List[.Intersection]): Intersections from each of the
            9 edge-edge pairs from a surface-surface pairing.
        surface1 (.Surface): First surface in intersection.
        edges1 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the first surface being intersected.
        surface2 (.Surface): Second surface in intersection.
        edges2 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the second surface being intersected.
        max_edges (Optional[int]): The maximum number of allowed / expected
            edges per intersection. This is to avoid infinite loops.

    Returns:
        List[Union[.CurvedPolygon, .Surface]]: All of the intersections
        encountered. Assumes, but does not check, that if a surface is
        returned, there must be exactly one intersection.

    Raises:
        RuntimeError: If the number of edges in a curved polygon
            exceeds ``max_edges``. This is interpreted as a sign
            that the algorithm failed.
    """
    unused = [intersection for intersection in intersections
              if intersection.interior_curve in _ACCEPTABLE]
    result = []
    while unused:
        start = unused.pop()
        curr_node = start
        next_node = get_next(start, intersections, unused)
        edge_ends = [(curr_node, next_node)]
        while next_node is not start:
            curr_node = to_front(next_node, intersections, unused)
            # NOTE: We also check to break when moving a corner node
            #       to the front. This is because ``intersections``
            #       de-duplicates corners by selecting the one
            #       (of 2 or 4 choices) at the front of segment(s).
            if curr_node is start:
                break
            next_node = get_next(curr_node, intersections, unused)
            edge_ends.append((curr_node, next_node))
            if len(edge_ends) > max_edges:
                raise RuntimeError(
                    'Unexpected number of edges', len(edge_ends))

        edge_info = tuple(
            ends_to_curve(start_node, end_node)
            for start_node, end_node in edge_ends
        )
        result.append(
            make_intersection(edge_info, surface1, edges1, surface2, edges2))

    return result


def combine_intersections(intersections, surface1, edges1, surface2, edges2):
    """Combine curve-curve intersections into curved polygon(s).

    .. note::

       This is a helper used only by :meth:`.Surface.intersect`.

    Does so assuming each intersection lies on an edge of one of
    two :class:`.Surface`-s.

    .. note ::

       This assumes that each ``intersection`` has been classified via
       :func:`classify_intersection`.

    Args:
        intersections (List[.Intersection]): Intersections from each of the
            9 edge-edge pairs from a surface-surface pairing.
        surface1 (.Surface): First surface in intersection.
        edges1 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the first surface being intersected.
        surface2 (.Surface): Second surface in intersection.
        edges2 (Tuple[.Curve, .Curve, .Curve]): The three edges
            of the second surface being intersected.

    Returns:
        List[Union[~bezier.curved_polygon.CurvedPolygon, \
        ~bezier.surface.Surface]]: A list of curved polygons (or surfaces)
        that compose the intersected objects.
    """
    if not intersections:
        return no_intersections(surface1, surface2)

    result = basic_interior_combine(
        intersections, surface1, edges1, surface2, edges2)
    if result:
        return result

    return tangent_only_intersections(intersections, surface1, surface2)


def _evaluate_barycentric(nodes, degree, lambda1, lambda2, lambda3):
    r"""Compute a point on a surface.

    Evaluates :math:`B\left(\lambda_1, \lambda_2, \lambda_3\right)` for a
    B |eacute| zier surface / triangle defined by ``nodes``.

    .. note::

       There is also a Fortran implementation of this function, which
       will be used if it can be built.

    Args:
        nodes (numpy.ndarray): Control point nodes that define the surface.
        degree (int): The degree of the surface define by ``nodes``.
        lambda1 (float): Parameter along the reference triangle.
        lambda2 (float): Parameter along the reference triangle.
        lambda3 (float): Parameter along the reference triangle.

    Returns:
        numpy.ndarray: The evaluated point as a ``1xD`` array (where ``D``
        is the ambient dimension where ``nodes`` reside).
    """
    num_nodes, dimension = nodes.shape

    binom_val = 1.0
    result = np.zeros((1, dimension), order='F')
    index = num_nodes - 1
    result += nodes[index, :]

    # curve evaluate_multi_barycentric() takes arrays.
    lambda1 = np.asfortranarray([lambda1])
    lambda2 = np.asfortranarray([lambda2])
    for k in six.moves.xrange(degree - 1, -1, -1):
        # We want to go from (d C (k + 1)) to (d C k).
        binom_val = (binom_val * (k + 1)) / (degree - k)
        index -= 1  # Step to last element in row.
        #     k = d - 1, d - 2, ...
        # d - k =     1,     2, ...
        # We know row k has (d - k + 1) elements.
        new_index = index - degree + k  # First element in row.

        row_nodes = nodes[new_index:index + 1, :]
        row_nodes = np.asfortranarray(row_nodes)
        row_result = _curve_helpers.evaluate_multi_barycentric(
            row_nodes, lambda1, lambda2)

        result *= lambda3
        result += binom_val * row_result
        # Update index for next iteration.
        index = new_index

    return result


def _evaluate_barycentric_multi(nodes, degree, param_vals, dimension):
    r"""Compute multiple points on the surface.

    .. note::

       There is also a Fortran implementation of this function, which
       will be used if it can be built.

    Args:
        nodes (numpy.ndarray): Control point nodes that define the surface.
        degree (int): The degree of the surface define by ``nodes``.
        param_vals (numpy.ndarray): Array of parameter values (as a
            ``Nx3`` array).
        dimension (int): The dimension the surface lives in.

    Returns:
        numpy.ndarray: The evaluated points, where rows correspond to
        rows of ``param_vals`` and the columns to the dimension of the
        underlying surface.
    """
    num_vals, _ = param_vals.shape
    result = np.empty((num_vals, dimension), order='F')
    for index, (lambda1, lambda2, lambda3) in enumerate(param_vals):
        result[index, :] = evaluate_barycentric(
            nodes, degree, lambda1, lambda2, lambda3)
    return result


def _evaluate_cartesian_multi(nodes, degree, param_vals, dimension):
    r"""Compute multiple points on the surface.

    .. note::

       There is also a Fortran implementation of this function, which
       will be used if it can be built.

    Args:
        nodes (numpy.ndarray): Control point nodes that define the surface.
        degree (int): The degree of the surface define by ``nodes``.
        param_vals (numpy.ndarray): Array of parameter values (as a
            ``Nx2`` array).
        dimension (int): The dimension the surface lives in.

    Returns:
        numpy.ndarray: The evaluated points, where rows correspond to
        rows of ``param_vals`` and the columns to the dimension of the
        underlying surface.
    """
    num_vals, _ = param_vals.shape
    result = np.empty((num_vals, dimension), order='F')
    for index, (s, t) in enumerate(param_vals):
        result[index, :] = evaluate_barycentric(
            nodes, degree, 1.0 - s - t, s, t)
    return result


def _compute_edge_nodes(nodes, degree):
    """Compute the nodes of each edges of a surface.

    .. note::

       There is also a Fortran implementation of this function, which
       will be used if it can be built.

    Args:
        nodes (numpy.ndarray): Control point nodes that define the surface.
        degree (int): The degree of the surface define by ``nodes``.

    Returns:
        Tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray]: The nodes in
        the edges of the surface.
    """
    _, dimension = np.shape(nodes)
    nodes1 = np.empty((degree + 1, dimension), order='F')
    nodes2 = np.empty((degree + 1, dimension), order='F')
    nodes3 = np.empty((degree + 1, dimension), order='F')

    curr2 = degree
    curr3 = -1
    for i in six.moves.xrange(degree + 1):
        nodes1[i, :] = nodes[i, :]
        nodes2[i, :] = nodes[curr2, :]
        nodes3[i, :] = nodes[curr3, :]
        # Update the indices.
        curr2 += degree - i
        curr3 -= i + 2

    return nodes1, nodes2, nodes3


class _IntersectionClassification(enum.Enum):
    """Enum classifying the "interior" curve in an intersection.

    Provided as the output values for :func:`.classify_intersection`.

    .. note::

       There is also a Cython implementation of this enum, which
       will be used if it can be built. If the Cython type is **not**
       available, this type will be aliased within the module as
       ``IntersectionClassification`` (i.e. it will be made public).
    """

    FIRST = 0
    """The first curve is on the interior."""
    SECOND = 1
    """The second curve is on the interior."""
    OPPOSED = 2
    """Tangent intersection with opposed interiors."""
    TANGENT_FIRST = 3
    """Tangent intersection, first curve is on the interior."""
    TANGENT_SECOND = 4
    """Tangent intersection, second curve is on the interior."""
    IGNORED_CORNER = 5
    """Intersection at a corner, interiors don't intersect."""


# pylint: disable=invalid-name
if _surface_speedup is None:  # pragma: NO COVER
    de_casteljau_one_round = _de_casteljau_one_round
    specialize_surface = _specialize_surface
    subdivide_nodes = _subdivide_nodes
    jacobian_both = _jacobian_both
    jacobian_det = _jacobian_det
    evaluate_barycentric = _evaluate_barycentric
    evaluate_barycentric_multi = _evaluate_barycentric_multi
    evaluate_cartesian_multi = _evaluate_cartesian_multi
    compute_edge_nodes = _compute_edge_nodes
    IntersectionClassification = _IntersectionClassification
else:
    de_casteljau_one_round = _surface_speedup.de_casteljau_one_round
    specialize_surface = _surface_speedup.specialize_surface
    subdivide_nodes = _surface_speedup.subdivide_nodes
    jacobian_both = _surface_speedup.jacobian_both
    jacobian_det = _surface_speedup.jacobian_det
    evaluate_barycentric = _surface_speedup.evaluate_barycentric
    evaluate_barycentric_multi = _surface_speedup.evaluate_barycentric_multi
    evaluate_cartesian_multi = _surface_speedup.evaluate_cartesian_multi
    compute_edge_nodes = _surface_speedup.compute_edge_nodes
    IntersectionClassification = _surface_speedup.IntersectionClassification
# pylint: enable=invalid-name

# NOTE: These constants must be defined **after** the intersection
#       classification enum is, hence we can't define it at the top with
#       the other constants.
_ACCEPTABLE = (
    IntersectionClassification.FIRST,
    IntersectionClassification.SECOND,
)
