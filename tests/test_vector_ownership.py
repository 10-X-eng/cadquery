"""Value and ownership contracts for native vector conversion fast paths."""
import gc
import math
import pickle

import pytest

import cadquery as cq
from OCP.gp import gp_Dir, gp_Pnt, gp_Vec, gp_XYZ


@pytest.mark.parametrize(
    "operation, expected",
    [
        (lambda a, b: a + b, (1, 1, 8)),
        (lambda a, b: a - b, (3, -7, 4)),
        (lambda a, b: a.cross(b), (-30, -10, 5)),
        (lambda a, b: a * 2, (4, -6, 12)),
        (lambda a, b: 2 * a, (4, -6, 12)),
        (lambda a, b: a / 2, (1, -1.5, 3)),
        (lambda a, b: -a, (-2, 3, -6)),
        (lambda a, b: a.normalized(), (2 / 7, -3 / 7, 6 / 7)),
    ],
)
def test_arithmetic_results_are_independent_values(operation, expected):
    left, right = cq.Vector(2, -3, 6), cq.Vector(-1, 4, 2)
    result = operation(left, right)
    assert result.toTuple() == pytest.approx(expected)
    assert type(result) is cq.Vector
    result.wrapped.SetX(123)
    assert left.toTuple() == (2, -3, 6)
    assert right.toTuple() == (-1, 4, 2)
    left.y = right.y = 456
    assert result.y == pytest.approx(expected[1])
    del left, right
    gc.collect()
    assert result.toTuple() == pytest.approx((123, expected[1], expected[2]))


@pytest.mark.parametrize("native_type", [gp_Vec, gp_Pnt, gp_Dir, gp_XYZ])
def test_public_constructor_keeps_copy_semantics(native_type):
    native = native_type(2, -3, 6)
    original = native.Coord()
    vector = cq.Vector(native)
    assert vector.toTuple() == original
    vector.x = 9
    assert native.Coord() == original
    native.SetY(.25)
    assert vector.y == original[1]


@pytest.mark.parametrize(
    "matrix, expected",
    [
        ([[0, -1, 0, 8], [1, 0, 0, -2], [0, 0, 1, 4]], (11, 0, 10)),
        ([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], (-2, -3, 6)),
        ([[2, 0, 0, 0], [0, 2, 0, 0], [0, 0, 2, 0]], (4, -6, 12)),
        ([[2, 0, 0, 1], [0, 3, 0, 2], [0, 0, 4, 3]], (5, -7, 27)),
        ([[1, 2, 0, 1], [0, 1, -.5, 2], [0, 0, 1, 3]], (-3, -4, 9)),
        ([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0]], (2, -3, 0)),
    ],
)
def test_point_transform_value_and_ownership(matrix, expected):
    source = cq.Vector(2, -3, 6)
    transformed = source.transform(cq.Matrix(matrix))
    assert transformed.toTuple() == pytest.approx(expected)
    transformed.z = 100
    assert source.toTuple() == (2, -3, 6)


def test_matrix_multiply_issue_283_and_general_affine_inverse():
    # https://github.com/CadQuery/cadquery/issues/283: decimal input need not
    # describe a perfectly orthogonal matrix to transform points correctly.
    rows = [
        [-.146655, -.271161, -.951296, .0376659],
        [-.676234, .729359, -.103649, .615421],
        [.721942, .628098, -.290333, -.451955],
        [0, 0, 0, 1],
    ]
    matrix = cq.Matrix(rows)
    for values in ((0, 0, 0), (1, -2, 3), (1e9, -2e9, 3e9), (1e-9, -2e-9, 3e-9)):
        point = cq.Vector(values)
        expected = tuple(sum(row[i] * values[i] for i in range(3)) + row[3] for row in rows[:3])
        result = matrix.multiply(point)
        assert result.toTuple() == pytest.approx(expected, rel=1e-14, abs=1e-14)
        assert point.toTuple() == values
        assert matrix.inverse().multiply(result).toTuple() == pytest.approx(values, rel=1e-14, abs=1e-14)


def test_transform_preserves_subclass_point_conversion():
    class Custom(cq.Vector):
        def toPnt(self):
            return gp_Pnt(10, 20, 30)

    source = Custom(2, -3, 6)
    assert source.transform(cq.Matrix()).toTuple() == (10, 20, 30)
    assert source.toTuple() == (2, -3, 6)


def test_coordinate_conversion_preserves_values_and_subclass_properties():
    vector = cq.Vector(-0.0, float("inf"), float("nan"))
    for values in (vector.toTuple(), tuple(vector), pickle.loads(pickle.dumps(vector)).toTuple()):
        assert math.copysign(1, values[0]) == -1
        assert values[1] == float("inf")
        assert math.isnan(values[2])

    class Custom(cq.Vector):
        @property
        def x(self):
            return super().x + 100

    custom = Custom(2, -3, 6)
    assert custom.toTuple() == tuple(custom) == (102, -3, 6)
    assert type(custom + cq.Vector()) is cq.Vector

    class CustomTuple(Custom):
        def toTuple(self):
            return (999, 999, 999)

    assert tuple(CustomTuple(2, -3, 6)) == (102, -3, 6)


def test_mesh_vectors_do_not_alias_native_triangulation():
    shape = cq.Solid.makeBox(2, 3, 4).moved(cq.Location((5, 6, 7), (1, 2, 3), 40))
    vertices, triangles = shape.tessellate(.05)
    expected = [vertex.toTuple() for vertex in vertices]
    for vertex in vertices:
        vertex.x = 999
    actual, actual_triangles = shape.tessellate(.05)
    assert [vertex.toTuple() for vertex in actual] == expected
    assert actual_triangles == triangles
