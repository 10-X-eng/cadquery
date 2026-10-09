"""Affine mesh normals must follow the transformed surface and tangent plane.

Run explicitly against stock OCCT and the isolated native correction. These
checks do not imply that the experimental override is installed in Steve.
"""
import math

import cadquery as cq
import numpy as np
import pytest
from cadquery.occ_impl.shapes import TColgp_Array1OfPnt
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.BRepLib import BRepLib_ToolTriangulatedShape
from OCP.GProp import GProp_GProps
from OCP.Poly import Poly_Polygon3D, Poly_Triangle, Poly_Triangulation
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Face
from OCP.gp import gp_Dir, gp_Pnt, gp_Vec


C = math.sqrt(.5)
MATRICES = {
    "rotation": [[C, -C, 0, 10], [C, C, 0, 20], [0, 0, 1, 30]],
    "shear": [[1, .5, 0, 10], [0, 1, .3, 20], [0, 0, 1, 30]],
    "scale": [[2, 0, 0, 0], [0, 3, 0, 0], [0, 0, .7, 0]],
    "reflection": [[-1, .2, 0, 10], [0, 1, .3, 20], [0, 0, 1, 30]],
}


def triangulation(face):
    location = TopLoc_Location()
    mesh = BRep_Tool.Triangulation_s(face.wrapped, location)
    return mesh, location.Transformation()


def mesh_snapshot(shape):
    result = []
    for face in shape.Faces():
        mesh, _ = triangulation(face)
        result.append((
            [mesh.Node(i).Coord() for i in range(1, mesh.NbNodes() + 1)],
            [mesh.Normal(i).Coord() for i in range(1, mesh.NbNodes() + 1)],
            [mesh.Triangle(i).Get() for i in range(1, mesh.NbTriangles() + 1)],
        ))
    return result


@pytest.mark.parametrize("matrix", MATRICES.values(), ids=MATRICES)
@pytest.mark.parametrize("kind", ["box", "sphere"])
@pytest.mark.parametrize("located", [False, True])
def test_transformed_normals_agree_with_surface_tangents(matrix, kind, located):
    shape = cq.Solid.makeBox(2, 3, 4) if kind == "box" else cq.Solid.makeSphere(3, angleDegrees1=-90)
    # Location belongs to the face's triangulation, independently of the new
    # general affine transform. Nonuniform scale must handle this rotation too.
    if located:
        shape = shape.moved(cq.Location((7, -4, 2), (1, 2, 3), 23))
    shape.mesh(.05, .3)
    for face in shape.Faces():
        mesh, _ = triangulation(face)
        BRepLib_ToolTriangulatedShape.ComputeNormals_s(face.wrapped, mesh)
    before = mesh_snapshot(shape)
    result = shape.transformGeometry(cq.Matrix(matrix))
    assert result.isValid()
    # Use span-aware Gauss-Kronrod integration for the analytic volume oracle.
    # Default quadrature and ordinary adaptive integration can miss rational
    # spline spans and understate their numerical error on this ellipsoid.
    props = GProp_GProps()
    error = BRepGProp.VolumePropertiesGK_s(result.wrapped, props, 1e-10, False, True)
    assert 0 <= error < 1e-8
    assert props.Mass() == pytest.approx(
        shape.Volume() * abs(np.linalg.det(np.asarray(matrix)[:, :3])), rel=1e-8)
    assert mesh_snapshot(shape) == before
    checked = 0
    for face in result.Faces():
        mesh, placement = triangulation(face)
        assert mesh is not None and mesh.HasNormals() and mesh.HasUVNodes()
        surface = BRepAdaptor_Surface(face.wrapped)
        for i in range(1, mesh.NbNodes() + 1):
            uv = mesh.UVNode(i)
            point, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
            surface.D1(uv.X(), uv.Y(), point, du, dv)
            cross = du.Crossed(dv)
            if cross.Magnitude() < 1e-7:
                continue  # Sphere poles have no regular UV tangent basis.
            actual = mesh.Normal(i).Transformed(placement)
            expected = gp_Dir(cross)
            assert actual.Dot(expected) > 1 - 1e-6
            checked += 1
    assert checked >= 20


def mesh_only_face():
    mesh = Poly_Triangulation(3, 1, False)
    for i, point in enumerate(((0, 0, 0), (2, 0, 1), (0, 3, 1)), 1):
        mesh.SetNode(i, gp_Pnt(*point))
    mesh.SetTriangle(1, Poly_Triangle(1, 2, 3))
    mesh.AddNormals()
    # Deliberately authored normals, distinct from the facet normal. Recomputing
    # normals from a surface or from triangles would silently discard these.
    for i, direction in enumerate(((1, 2, 3), (3, 1, 2), (2, 3, 1)), 1):
        mesh.SetNormal(i, gp_Dir(*direction))
    face = TopoDS_Face()
    BRep_Builder().MakeFace(face, mesh)
    return cq.Face(face)


@pytest.mark.parametrize("matrix", MATRICES.values(), ids=MATRICES)
@pytest.mark.parametrize("located", [False, True])
def test_authored_mesh_only_normals_and_nodes_are_preserved(matrix, located):
    face = mesh_only_face()
    if located:
        face = face.moved(cq.Location((7, -4, 2), (1, 2, 3), 23))
    before = mesh_snapshot(face)
    _, original_placement = triangulation(face)
    result = face.transformGeometry(cq.Matrix(matrix))
    mesh, placement = triangulation(result)
    linear = np.asarray(matrix)[:, :3]
    normal_transform = np.linalg.det(linear) * np.linalg.inv(linear).T
    for i, normal in enumerate(before[0][1], 1):
        normal = gp_Dir(*normal).Transformed(original_placement).Coord()
        expected = normal_transform @ normal
        expected /= np.linalg.norm(expected)
        np.testing.assert_allclose(mesh.Normal(i).Transformed(placement).Coord(), expected, atol=1e-6)
    for i, point in enumerate(before[0][0], 1):
        point = gp_Pnt(*point).Transformed(original_placement).Coord()
        expected = linear @ point + np.asarray(matrix)[:, 3]
        np.testing.assert_allclose(mesh.Node(i).Transformed(placement).Coord(), expected, atol=1e-9)
    assert [mesh.Triangle(i).Get() for i in range(1, mesh.NbTriangles() + 1)] == before[0][2]
    assert mesh_snapshot(face) == before


def test_unmeshed_transform_does_not_create_a_triangulation():
    result = cq.Solid.makeBox(2, 3, 4).transformGeometry(cq.Matrix(MATRICES["shear"]))
    assert result.isValid()
    assert all(triangulation(face)[0] is None for face in result.Faces())


@pytest.mark.parametrize("located", [False, True])
def test_edge_polygon_uses_the_result_edge_local_frame(located):
    points = [(0, 0, 0), (1, 1.5, 2), (2, 3, 4)]
    nodes = TColgp_Array1OfPnt(1, 3)
    for i, point in enumerate(points, 1):
        nodes.SetValue(i, gp_Pnt(*point))
    edge = cq.Edge.makeLine(points[0], points[-1])
    BRep_Builder().UpdateEdge(edge.wrapped, Poly_Polygon3D(nodes))
    if located:
        edge = edge.moved(cq.Location((7, -4, 2), (1, 2, 3), 23))
    before_loc = TopLoc_Location()
    before_poly = BRep_Tool.Polygon3D_s(edge.wrapped, before_loc)
    before = [before_poly.Nodes().Value(i).Coord() for i in range(1, 4)]
    matrix = MATRICES["shear"]
    result = edge.transformGeometry(cq.Matrix(matrix))
    loc = TopLoc_Location()
    polygon = BRep_Tool.Polygon3D_s(result.wrapped, loc)
    assert polygon is not None and polygon.NbNodes() == 3
    for i, point in enumerate(before, 1):
        world = gp_Pnt(*point).Transformed(before_loc.Transformation()).Coord()
        expected = np.asarray(matrix)[:, :3] @ world + np.asarray(matrix)[:, 3]
        np.testing.assert_allclose(polygon.Nodes().Value(i).Transformed(loc.Transformation()).Coord(), expected, atol=1e-9)
    assert [before_poly.Nodes().Value(i).Coord() for i in range(1, 4)] == before


@pytest.mark.parametrize("scale", [1e100, 1e-100])
def test_uniform_mesh_scaling_does_not_overflow_normal_calculation(scale):
    face = mesh_only_face()
    before = mesh_snapshot(face)
    result = face.transformGeometry(cq.Matrix([
        [scale, 0, 0, 0], [0, scale, 0, 0], [0, 0, scale, 0]]))
    mesh, _ = triangulation(result)
    for i, normal in enumerate(before[0][1], 1):
        np.testing.assert_allclose(mesh.Normal(i).Coord(), normal, atol=1e-6)
