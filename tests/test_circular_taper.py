"""Exact frustum geometry, legacy parity, and small tapered-circle regression."""

from math import cos, pi, radians, tan

import cadquery as cq
import pytest
from OCP.LocOpe import LocOpe_DPrism
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box


PLANES = [
    cq.Plane.XY(),
    cq.Plane.XZ(),
    cq.Plane(origin=(7, -3, 2), xDir=(1, 2, 0), normal=(2, -1, 3)),
]


def bounds(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, False)
    return (*box.CornerMin().Coord(), *box.CornerMax().Coord())


@pytest.mark.parametrize("plane", PLANES)
@pytest.mark.parametrize("height", [-4, 4])
@pytest.mark.parametrize("taper", [-20, -1, 1, 20])
def test_circular_taper_matches_legacy(plane, height, taper):
    face = cq.Face.makeFromWires(cq.Workplane(plane).circle(3).val())
    normal = face.normalAt()
    direction = normal * height
    sign = 1 if height > 0 else -1
    expected = cq.Solid(
        LocOpe_DPrism(
            face.wrapped, height / cos(radians(taper)), sign * radians(taper)
        ).Shape()
    ).clean()
    actual = cq.Workplane(plane).circle(3).extrude(height, taper=taper).val()
    assert actual.isValid() and expected.isValid()
    assert len(actual.Solids()) == 1
    assert len(actual.Faces()) == len(expected.Faces()) == 3
    assert sorted(f.geomType() for f in actual.Faces()) == sorted(
        f.geomType() for f in expected.Faces()
    )
    assert actual.Volume() == pytest.approx(expected.Volume(), rel=1e-10)
    assert actual.Area() == pytest.approx(expected.Area(), rel=1e-10)
    assert actual.Center().toTuple() == pytest.approx(
        expected.Center().toTuple(), abs=1e-9
    )
    assert bounds(actual) == pytest.approx(bounds(expected), abs=1e-9)
    for part in (actual.cut(expected), expected.cut(actual)):
        assert part.isValid()
        assert abs(part.Volume()) < 1e-8


@pytest.mark.parametrize("radius", [0.00035912, 0.0035912, 0.035912, 1.0, 1000.0])
@pytest.mark.parametrize("direction", [-1, 1])
@pytest.mark.parametrize("taper", [-1, 1])
def test_small_and_large_tapers_have_analytic_geometry(radius, direction, taper):
    height = 4 * radius
    end_radius = radius - height * tan(radians(taper))
    result = (
        cq.Workplane().circle(radius).extrude(direction * height, taper=taper).val()
    )
    expected_volume = (
        pi * height * (radius**2 + radius * end_radius + end_radius**2) / 3
    )
    assert result.isValid()
    assert len(result.Solids()) == 1
    assert result.Volume(1e-12) == pytest.approx(expected_volume, rel=1e-10, abs=1e-24)
    z = (
        height
        * (radius**2 + 2 * radius * end_radius + 3 * end_radius**2)
        / (4 * (radius**2 + radius * end_radius + end_radius**2))
    )
    assert result.Center().toTuple() == pytest.approx(
        (0, 0, direction * z), abs=1e-8 * radius
    )
    # Both caps remain selectable and use the requested radii.
    caps = sorted(f.Area() for f in result.Faces() if f.geomType() == "PLANE")
    assert caps == pytest.approx(
        sorted([pi * radius**2, pi * end_radius**2]), rel=1e-10, abs=1e-24
    )


def test_rotated_location_and_downstream_boolean():
    wire = cq.Workplane().circle(3).val().moved(cq.Location((7, -4, 2), (1, 2, 3), 47))
    face = cq.Face.makeFromWires(wire)
    result = (
        cq.Workplane(cq.Plane(face.Center(), normal=face.normalAt()))
        .add(face)
        .extrude(4, taper=-5)
        .val()
    )
    tool = cq.Solid.makeCylinder(
        0.5, 8, face.Center() - face.normalAt() * 2, face.normalAt()
    )
    cut = result.cut(tool)
    assert cut.isValid()
    assert cut.Volume() == pytest.approx(result.Volume() - pi * 0.5**2 * 4, rel=1e-9)


@pytest.mark.parametrize(
    "kind", ["rectangle", "ellipse", "semicircle", "annulus", "reversed"]
)
def test_other_profiles_use_legacy_builder(monkeypatch, kind):
    import cadquery.occ_impl.shapes as shapes

    if kind == "rectangle":
        face = cq.Face.makeFromWires(cq.Workplane().rect(6, 4).val())
    elif kind == "ellipse":
        face = cq.Face.makeFromWires(cq.Workplane().ellipse(3, 2).val())
    elif kind == "semicircle":
        face = cq.Face.makeFromWires(
            cq.Workplane().moveTo(-3, 0).threePointArc((0, 3), (3, 0)).close().val()
        )
    elif kind == "annulus":
        face = cq.Face.makeFromWires(
            cq.Workplane().circle(3).val(), [cq.Workplane().circle(1).val()]
        )
    else:
        face = cq.Face(
            cq.Face.makeFromWires(cq.Workplane().circle(3).val()).wrapped.Reversed()
        )
    seen = []

    class StopHere(Exception):
        pass

    def legacy(*args):
        seen.append(args)
        raise StopHere

    monkeypatch.setattr(shapes, "LocOpe_DPrism", legacy)
    if kind == "annulus":
        assert cq.Solid._extrudeCircular(face, cq.Vector(0, 0, 4), 5) is None
        with pytest.raises(ValueError, match="Inner wires"):
            cq.Workplane().add(face).extrude(4, taper=5)
        assert not seen
        return
    with pytest.raises(StopHere):
        cq.Workplane().add(face).extrude(4, taper=5)
    assert len(seen) == 1


def test_uncleaned_and_low_level_extrusions_keep_split_faces():
    result = cq.Workplane().circle(3).extrude(4, taper=5, clean=False).val()
    face = cq.Face.makeFromWires(cq.Workplane().circle(3).val())
    low_level = cq.Solid.extrudeLinear(face, (0, 0, 4), 5)
    assert len(result.Faces()) == len(low_level.Faces()) == 5
    assert result.isValid() and low_level.isValid()
