"""Affine transforms must carry honest mesh-error and geometry-tolerance bounds."""
import math

import cadquery as cq
import numpy as np
import pytest
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.Poly import Poly_Polygon3D
from OCP.TopLoc import TopLoc_Location
from cadquery.occ_impl.shapes import TColgp_Array1OfPnt
from OCP.gp import gp_Pnt

from test_native_affine_normals import mesh_only_face, triangulation


ROTATION = np.array([[2, -1, 2], [2, 2, -1], [-1, 2, 2]]) / 3
LINEAR = {
    "rotation": ROTATION,
    "scaled_rotation": 4 * ROTATION,
    "shear": np.array([[1, 1, 0], [0, 1, 0], [0, 0, 1]]),
    "mixed_scale": ROTATION @ np.diag([2, 3, 5]),
}


def matrix(linear):
    return cq.Matrix([list(row) + [0] for row in linear])


@pytest.mark.parametrize("linear", LINEAR.values(), ids=LINEAR)
@pytest.mark.parametrize("kind", ["triangulation", "polygon", "vertex"])
def test_error_bounds_follow_maximum_stretch(linear, kind):
    tolerance = 0.25
    if kind == "triangulation":
        shape = mesh_only_face()
        original, _ = triangulation(shape)
        original.Deflection(tolerance)
        result = shape.transformGeometry(matrix(linear))
        transformed, _ = triangulation(result)
        actual = transformed.Deflection()
        assert original.Deflection() == tolerance
    elif kind == "polygon":
        shape = cq.Edge.makeLine((0, 0, 0), (1, 2, 3))
        nodes = TColgp_Array1OfPnt(1, 2)
        nodes.SetValue(1, gp_Pnt(0, 0, 0))
        nodes.SetValue(2, gp_Pnt(1, 2, 3))
        original = Poly_Polygon3D(nodes)
        original.Deflection(tolerance)
        BRep_Builder().UpdateEdge(shape.wrapped, original)
        result = shape.transformGeometry(matrix(linear))
        transformed = BRep_Tool.Polygon3D_s(result.wrapped, TopLoc_Location())
        assert transformed is not None
        actual = transformed.Deflection()
        assert original.Deflection() == tolerance
    else:
        shape = cq.Vertex.makeVertex(1, 2, 3)
        BRep_Builder().UpdateVertex(shape.wrapped, tolerance)
        result = shape.transformGeometry(matrix(linear))
        actual = BRep_Tool.Tolerance_s(result.wrapped)
        assert BRep_Tool.Tolerance_s(shape.wrapped) == tolerance
    # Independent NumPy SVD oracle: the largest singular value, not an entry
    # norm, bounds Euclidean displacement in every direction.
    expected = tolerance * np.linalg.svd(linear, compute_uv=False)[0]
    assert actual == pytest.approx(expected, rel=2e-14, abs=0)


@pytest.mark.parametrize("scale", [1e-100, 1e100])
def test_stretch_bound_avoids_overflow_and_underflow(scale):
    shape = mesh_only_face()
    original, _ = triangulation(shape)
    original.Deflection(0.25)
    result = shape.transformGeometry(matrix(scale * ROTATION))
    transformed, _ = triangulation(result)
    assert transformed.Deflection() == pytest.approx(0.25 * scale, rel=2e-14, abs=0)


def test_anisotropic_deformation_does_not_keep_an_unjustified_angle_claim():
    shape = cq.Workplane().sphere(3).val()
    shape.mesh(5, 0.3)
    original, _ = triangulation(shape.Faces()[0])
    original_angle = original.Parameters().Angle()
    result = shape.transformGeometry(matrix(np.diag([10, 1, 1])))
    transformed, _ = triangulation(result.Faces()[0])
    parameters = transformed.Parameters()
    # Tangent/normal angles can expand by the map's condition number. Retain
    # either an honest upper bound or unknown precision, never the old claim.
    expanded = 2 * math.atan(10 * math.tan(original_angle / 2))
    assert parameters is None or not parameters.HasAngle() or parameters.Angle() >= expanded
    assert original.Parameters().Angle() == original_angle


def test_meshing_before_deformation_does_not_change_later_requested_mesh():
    meshes = []
    for cached in (False, True):
        shape = cq.Workplane().sphere(3).val()
        if cached:
            shape.mesh(5, 0.3)
        result = shape.transformGeometry(matrix(np.diag([10, 1, 1])))
        assert result.isValid()
        vertices, triangles = result.tessellate(5, 0.3)
        meshes.append(([v.toTuple() for v in vertices], triangles))
    # Same geometry and request, independently generated from an unmeshed
    # source. Stale parameters must not bypass the required regeneration.
    assert meshes[0][1] == meshes[1][1]
    np.testing.assert_allclose(meshes[0][0], meshes[1][0], atol=1e-9, rtol=1e-12)
