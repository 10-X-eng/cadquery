"""Equivalent native and explicit-matrix scale transforms must agree."""
import math

import cadquery as cq
import numpy as np
import pytest
from OCP.BRepGProp import BRepGProp
from OCP.BRepLib import BRepLib_ToolTriangulatedShape
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt, gp_Trsf

from test_native_affine_normals import triangulation


@pytest.mark.parametrize("scale", [2, -2])
@pytest.mark.parametrize("kind", ["box", "sphere"])
@pytest.mark.parametrize("state", ["unmeshed", "meshed", "normals"])
def test_native_scale_keeps_its_scale_factor(scale, kind, state):
    shape = cq.Solid.makeBox(2, 3, 4) if kind == "box" else cq.Solid.makeSphere(3, angleDegrees1=-90)
    original_volume = 24 if kind == "box" else 36 * math.pi
    original_center = np.array([1, 1.5, 2] if kind == "box" else [0, 0, 0])
    if state != "unmeshed":
        shape.mesh(0.05, 0.3)
    if state == "normals":
        for face in shape.Faces():
            mesh, _ = triangulation(face)
            BRepLib_ToolTriangulatedShape.ComputeNormals_s(face.wrapped, mesh)
    pivot = np.array([5, -2, 1])
    transform = gp_Trsf()
    transform.SetScale(gp_Pnt(*pivot), scale)
    explicit = np.column_stack([np.eye(3) * scale, (1 - scale) * pivot]).tolist()
    results = [shape.transformGeometry(cq.Matrix(value)) for value in (transform, explicit)]
    for result in results:
        assert result.isValid()
        props = GProp_GProps()
        error = BRepGProp.VolumePropertiesGK_s(result.wrapped, props, 1e-10, False, True)
        assert 0 <= error < 1e-8
        assert props.Mass() == pytest.approx(original_volume * abs(scale)**3, rel=1e-8)
        np.testing.assert_allclose(props.CentreOfMass().Coord(),
                                   original_center * scale + (1 - scale) * pivot,
                                   atol=1e-8, rtol=1e-10)
    for native_face, explicit_face in zip(results[0].Faces(), results[1].Faces()):
        native_mesh, native_loc = triangulation(native_face)
        explicit_mesh, explicit_loc = triangulation(explicit_face)
        if state == "unmeshed":
            assert native_mesh is None and explicit_mesh is None
            continue
        assert native_mesh.NbNodes() == explicit_mesh.NbNodes()
        for i in range(1, native_mesh.NbNodes() + 1):
            np.testing.assert_allclose(native_mesh.Node(i).Transformed(native_loc).Coord(),
                                       explicit_mesh.Node(i).Transformed(explicit_loc).Coord(),
                                       atol=1e-9, rtol=1e-12)
            if state == "normals":
                assert native_mesh.Normal(i).Transformed(native_loc).Dot(
                    explicit_mesh.Normal(i).Transformed(explicit_loc)) > 1 - 1e-6
    assert shape.Volume() == pytest.approx(original_volume, rel=1e-12)
