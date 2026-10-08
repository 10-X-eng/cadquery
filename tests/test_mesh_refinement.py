"""Requested angular precision must not depend on an earlier coarse export."""
import math
import struct

import cadquery as cq
import numpy as np
import pytest
from OCP.BRep import BRep_Builder
from OCP.Poly import Poly_Triangle, Poly_Triangulation
from OCP.TopoDS import TopoDS_Face
from OCP.gp import gp_Pnt


def signed_volume(vertices, triangles):
    points = np.asarray(vertices)
    indices = np.asarray(triangles)
    a, b, c = (points[indices[:, i]] for i in range(3))
    return np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6


def test_finer_angular_tolerance_refines_existing_mesh():
    sphere = cq.Workplane().sphere(5).val()
    coarse = sphere.tessellate(0.1, 1.0)
    vertices, triangles = sphere.tessellate(0.1, 0.05)
    assert len(triangles) > len(coarse[1]) * 20
    assert signed_volume([v.toTuple() for v in vertices], triangles) == pytest.approx(
        4 * math.pi * 125 / 3, rel=0.001)
    # A later coarser request may reuse the already satisfactory fine mesh.
    assert len(sphere.tessellate(0.1, 0.8)[1]) == len(triangles)


@pytest.mark.parametrize("relative", [False, True])
def test_stl_refines_a_previously_coarse_mesh(tmp_path, relative):
    sphere = cq.Workplane().sphere(5).val()
    coarse = sphere.tessellate(0.1, 1.0)
    path = tmp_path / "fine.stl"
    assert sphere.exportStl(str(path), 0.1, 0.05, relative=relative, parallel=False)
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    assert count > len(coarse[1]) * 20
    points = [struct.unpack_from("<3f", data, 84 + i * 50 + 12 + j * 12)
              for i in range(count) for j in range(3)]
    assert signed_volume(points, np.arange(count * 3).reshape(-1, 3)) == pytest.approx(
        4 * math.pi * 125 / 3, rel=0.001)


def mesh_only_face():
    triangulation = Poly_Triangulation(3, 1, False)
    for index, point in enumerate(((0, 0, 0), (1, 0, 0), (0, 1, 0)), 1):
        triangulation.SetNode(index, gp_Pnt(*point))
    triangulation.SetTriangle(1, Poly_Triangle(1, 2, 3))
    face = TopoDS_Face()
    BRep_Builder().MakeFace(face, triangulation)
    return cq.Face(face)


def test_refinement_preserves_faces_without_surface_geometry(tmp_path):
    face = mesh_only_face()
    vertices, triangles = face.tessellate(0.01, 0.01)
    assert len(vertices) == 3 and len(triangles) == 1
    path = tmp_path / "triangle.stl"
    assert face.exportStl(str(path), 0.01, 0.01, parallel=False)
    assert struct.unpack_from("<I", path.read_bytes(), 80)[0] == 1


def test_refinement_of_mixed_geometry_preserves_mesh_only_face():
    face = mesh_only_face()
    sphere = cq.Workplane().sphere(5).val()
    coarse = sphere.tessellate(0.1, 1.0)
    combined = cq.Compound.makeCompound([sphere, face])
    assert len(combined.tessellate(0.1, 0.05)[1]) > len(coarse[1]) * 20
    vertices, triangles = face.tessellate(0.1, 0.05)
    assert [v.toTuple() for v in vertices] == [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    assert triangles == [(0, 1, 2)]
