"""Geometric checks for the mesher, independent of its triangle ordering."""
from collections import Counter
import struct

import cadquery as cq
import numpy as np
import pytest


def mesh_properties(points, triangles):
    points = np.asarray(points)
    triangles = np.asarray(triangles)
    assert np.isfinite(points).all()
    # Face triangulations duplicate their boundary vertices. Weld only for this
    # topological check, leaving the exported geometry unmodified.
    _, vertex_ids = np.unique(points.round(6), axis=0, return_inverse=True)
    welded = vertex_ids[triangles]
    # OCCT emits collapsed facets at sphere/cone poles with both meshers.
    # They have no area; inspect the actual surface after welding those poles.
    live = ((welded[:, 0] != welded[:, 1]) & (welded[:, 1] != welded[:, 2])
            & (welded[:, 2] != welded[:, 0]))
    a, b, c = (points[triangles[live, i]] for i in range(3))
    assert (np.linalg.norm(np.cross(b - a, c - a), axis=1) > 1e-12).all()
    volume = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6
    welded = welded[live]
    directed = Counter((int(t[i]), int(t[(i + 1) % 3])) for t in welded for i in range(3))
    for (a, b), count in directed.items():
        assert a != b
        assert count == directed[(b, a)] == 1
    euler = len(set(welded.flat)) - len(directed) // 2 + len(welded)
    return volume, euler


def fixtures():
    return {
        "holes": (cq.Workplane().box(24, 24, 3).faces(">Z").workplane()
                  .rarray(6, 6, 3, 3).hole(3).val(), 2 - 2 * 9),
        "sphere": (cq.Workplane().sphere(5).val(), 2),
        "torus": (cq.Solid.makeTorus(8, 2), 0),
        "cone": (cq.Solid.makeCone(5, 0, 8), 2),
        "loft": (cq.Workplane().circle(4).workplane(offset=5).ellipse(5, 3)
                 .workplane(offset=5).circle(3).loft().val(), 2),
        "sweep": (cq.Workplane().circle(0.6).sweep(
            cq.Workplane("XZ").spline([(0, 0), (3, 4), (-1, 8), (0, 12)])).val(), 2),
        "shell": (cq.Workplane().box(12, 10, 8).edges("|Z").fillet(1)
                  .faces(">Z").shell(-0.6).val(), 2),
    }


@pytest.fixture(scope="module")
def shapes():
    return fixtures()


@pytest.mark.parametrize("name", ["holes", "sphere", "torus", "cone", "loft", "sweep", "shell"])
def test_closed_mesh_preserves_volume_winding_and_holes(shapes, name):
    shape, expected_euler = shapes[name]
    vertices, triangles = shape.tessellate(0.0005, 0.1)
    volume, euler = mesh_properties([v.toTuple() for v in vertices], triangles)
    assert euler == expected_euler
    assert volume == pytest.approx(shape.Volume(), rel=0.005)


@pytest.mark.parametrize("relative", [False, True])
@pytest.mark.parametrize("parallel", [False, True])
def test_binary_stl_quality_and_placement(tmp_path, relative, parallel):
    shape = cq.Workplane().box(24, 24, 3).faces(">Z").workplane().hole(5).val()
    shape = shape.moved(cq.Location((5, -3, 9), (1, 2, 3), 31))
    path = tmp_path / "part.stl"
    assert shape.exportStl(str(path), 0.005, 0.1, relative=relative, parallel=parallel)
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    assert len(data) == 84 + count * 50
    points = [struct.unpack_from("<3f", data, 84 + i * 50 + 12 + v * 12)
              for i in range(count) for v in range(3)]
    volume, euler = mesh_properties(points, np.arange(count * 3).reshape(-1, 3))
    assert euler == 0
    assert volume == pytest.approx(shape.Volume(), rel=0.005)
    bbox = shape.BoundingBox()
    assert np.min(points, axis=0) == pytest.approx((bbox.xmin, bbox.ymin, bbox.zmin), abs=1e-5)
    assert np.max(points, axis=0) == pytest.approx((bbox.xmax, bbox.ymax, bbox.zmax), abs=1e-5)


@pytest.mark.parametrize("size", [(1e-9, 1e-9), (1e-9, 1), (1, 1e-9)])
@pytest.mark.parametrize("compound", [False, True])
def test_faces_collapsed_at_kernel_tolerance_do_not_crash(size, compound):
    face = cq.Face.makePlane(*size).moved(cq.Location((3, 4, 5), (1, 2, 3), 37))
    shape = cq.Compound.makeCompound([cq.Solid.makeBox(1, 2, 3), face]) if compound else face
    vertices, triangles = shape.tessellate(0.001)
    assert all(np.isfinite(v.toTuple()).all() for v in vertices)
    assert all(0 <= index < len(vertices) for triangle in triangles for index in triangle)
    if compound:
        assert len(triangles) >= 12
