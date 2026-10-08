"""Face-normal direction must follow geometry, placement and face orientation."""
import cadquery as cq
import pytest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepGProp import BRepGProp_Face
from OCP.Geom import Geom_Plane
from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Vec


def native_normal(face):
    u0, u1, v0, v1 = face.uvBounds()
    point, normal = gp_Pnt(), gp_Vec()
    BRepGProp_Face(face.wrapped).Normal((u0 + u1) / 2, (v0 + v1) / 2, point, normal)
    return cq.Vector(normal).normalized()


@pytest.mark.parametrize("indirect", [False, True])
@pytest.mark.parametrize("reversed_face", [False, True])
@pytest.mark.parametrize("placed", [False, True])
def test_planar_normal_handedness_orientation_and_location(indirect, reversed_face, placed):
    axes = gp_Ax3(gp_Pnt(1, 2, 3), gp_Dir(1, 2, 3))
    if indirect:
        axes.XReverse()
    surface = Geom_Plane(axes)
    face = cq.Face(BRepBuilderAPI_MakeFace(surface, -2, 2, -3, 3, 1e-7).Face())
    if reversed_face:
        face = face.reverse()
    if placed:
        face = face.moved(cq.Location((5, -3, 9), (2, 1, 3), 41))
    expected = native_normal(face).toTuple()
    assert face.normalAt().toTuple() == pytest.approx(expected, abs=1e-12)
    assert face.normalAt().Length == pytest.approx(1, abs=1e-12)
    # Repeated queries must not mutate a borrowed native plane direction.
    assert face.normalAt().toTuple() == pytest.approx(expected, abs=1e-12)
    assert native_normal(face).toTuple() == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("mirror", [None, "XY", "YZ", "XZ"])
def test_perforated_face_normals_and_explicit_point_queries(mirror):
    shape = (cq.Workplane().box(24, 24, 3).faces(">Z").workplane()
             .rarray(6, 6, 3, 3).hole(3).val())
    if mirror:
        shape = shape.mirror(mirror)
    for face in shape.Faces():
        assert face.normalAt().toTuple() == pytest.approx(native_normal(face).toTuple(), abs=1e-12)
        if face.geomType() == "PLANE":
            u0, u1, v0, v1 = face.uvBounds()
            normal, position = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            assert face.normalAt(position).toTuple() == pytest.approx(normal.toTuple(), abs=1e-12)


def test_planar_normal_observes_mutated_native_surface():
    surface = Geom_Plane(gp_Ax3(gp_Pnt(), gp_Dir(0, 0, 1)))
    face = cq.Face(BRepBuilderAPI_MakeFace(surface, -1, 1, -1, 1, 1e-7).Face())
    assert face.normalAt().toTuple() == pytest.approx((0, 0, 1))
    surface.UReverse()
    assert face.normalAt().toTuple() == pytest.approx((0, 0, -1))
