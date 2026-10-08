"""Symmetric cleaned prisms agree with the original two-prism union."""

import cadquery as cq
import pytest

PLANES = [
    cq.Plane.XY(),
    cq.Plane.XZ(),
    cq.Plane(origin=(7, -3, 2), xDir=(1, 2, 0), normal=(2, -1, 3)),
]


def profile(plane, kind):
    wp = cq.Workplane(plane)
    if kind == "rectangle":
        return wp.rect(6, 4)
    if kind == "circle":
        return wp.circle(3)
    if kind == "ellipse":
        return wp.ellipse(3, 2)
    if kind == "annulus":
        return wp.circle(3).circle(1)
    if kind == "rectangular_ring":
        return wp.rect(6, 4).rect(2, 1)
    return wp.polyline([(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]).close()


@pytest.mark.parametrize(
    "kind", ["rectangle", "circle", "ellipse", "annulus", "rectangular_ring", "concave"]
)
@pytest.mark.parametrize("plane", PLANES)
@pytest.mark.parametrize("distance", [-4, 4])
def test_symmetric_prism_matches_opposite_union(kind, plane, distance):
    original = profile(plane, kind)._getFaces()[0]
    original_center = original.Center().toTuple()
    direction = plane.zDir * distance
    expected = (
        cq.Solid.extrudeLinear(original, direction)
        .fuse(cq.Solid.extrudeLinear(original, -direction), glue=True)
        .clean()
    )
    actual = profile(plane, kind).extrude(distance, both=True).val()
    assert actual.isValid() and expected.isValid()
    assert len(actual.Solids()) == len(expected.Solids()) == 1
    assert len(actual.Faces()) == len(expected.Faces())
    assert actual.Volume() == pytest.approx(expected.Volume(), rel=1e-10)
    assert actual.Area() == pytest.approx(expected.Area(), rel=1e-10)
    assert actual.Center().toTuple() == pytest.approx(
        expected.Center().toTuple(), abs=1e-9
    )
    assert original.Center().toTuple() == original_center
    for difference in (actual.cut(expected), expected.cut(actual)):
        assert difference.isValid()
        assert abs(difference.Volume()) < 1e-8


def test_symmetric_uncleaned_prism_keeps_middle_edges():
    face = profile(cq.Plane.XY(), "rectangle")._getFaces()[0]
    expected = cq.Solid.extrudeLinear(face, (0, 0, 4)).fuse(
        cq.Solid.extrudeLinear(face, (0, 0, -4)), glue=True
    )
    actual = (
        profile(cq.Plane.XY(), "rectangle").extrude(4, both=True, clean=False).val()
    )
    assert actual.isValid()
    assert len(actual.Faces()) == len(expected.Faces())
    assert len(actual.Edges()) == len(expected.Edges())


def test_symmetric_cut_and_disconnected_profiles():
    cut = (
        cq.Workplane()
        .box(10, 10, 10)
        .workplane()
        .rect(2, 3)
        .cutBlind(2, both=True)
        .val()
    )
    assert cut.isValid()
    assert cut.Volume() == pytest.approx(1000 - 2 * 3 * 4)
    array = (
        cq.Workplane()
        .rarray(10, 10, 3, 2)
        .circle(2)
        .extrude(3, both=True, combine=False)
    )
    assert len(array.solids().vals()) == 6
    assert all(s.isValid() for s in array.solids().vals())


def test_symmetric_prism_supports_later_edge_and_face_features():
    face = profile(cq.Plane.XY(), "rectangle")._getFaces()[0]
    expected = (
        cq.Solid.extrudeLinear(face, (0, 0, 4))
        .fuse(cq.Solid.extrudeLinear(face, (0, 0, -4)), glue=True)
        .clean()
    )
    actual = profile(cq.Plane.XY(), "rectangle").extrude(4, both=True)

    def finish(wp):
        return wp.edges("|Z").fillet(0.25).faces(">Z").workplane().hole(1).val()

    left, right = finish(actual), finish(cq.Workplane().add(expected))
    assert left.isValid() and right.isValid()
    assert len(left.Faces()) == len(right.Faces())
    assert left.Volume() == pytest.approx(right.Volume(), rel=1e-10)
    for difference in (left.cut(right), right.cut(left)):
        assert difference.isValid()
        assert abs(difference.Volume()) < 1e-8
