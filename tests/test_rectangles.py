"""Rectangle placement, construction flags and extrusion geometry."""
import cadquery as cq
import pytest


@pytest.mark.parametrize("dimensions", [(2, 3), (-2, 3), (2, -3), (-2, -3)])
@pytest.mark.parametrize("centered", [True, False, (False, True)])
def test_rectangle_arrays_preserve_profile_and_extrusion(dimensions, centered):
    plane = cq.Plane(origin=(7, -3, 2), xDir=(1, 2, 0), normal=(2, -1, 3))
    points = [(0, 0), (10, 0), (0, 10)]
    x, y = dimensions
    flags = (centered, centered) if isinstance(centered, bool) else centered
    profile = cq.Workplane(plane).pushPoints(points).rect(x, y, centered=centered)
    assert len(profile.vals()) == len(profile.ctx.pendingWires) == 3
    for wire, (px, py) in zip(profile.vals(), points):
        assert wire.isValid() and wire.IsClosed()
        assert len(wire.Edges()) == len(wire.Vertices()) == 4
        assert wire.Length() == pytest.approx(2 * (abs(x) + abs(y)))
        local_center = plane.toLocalCoords(wire.Center())
        assert local_center.toTuple() == pytest.approx((
            px + (0 if flags[0] else x / 2),
            py + (0 if flags[1] else y / 2), 0), abs=1e-9)
    solids = profile.extrude(4, combine=False).solids().vals()
    assert len(solids) == 3
    for solid in solids:
        assert solid.isValid()
        assert len(solid.Faces()) == 6
        assert solid.Volume() == pytest.approx(abs(x * y) * 4)


def test_construction_rectangles_remain_construction_geometry():
    profile = cq.Workplane().rarray(10, 20, 2, 3).rect(2, 3, forConstruction=True)
    assert len(profile.vals()) == 6
    assert not profile.ctx.pendingWires
    assert all(wire.forConstruction for wire in profile.vals())
    # Construction vertices can still locate a later hole pattern.
    rings = profile.vertices().circle(.2).extrude(1, combine=False).solids().vals()
    assert len(rings) == 24
    assert all(solid.isValid() for solid in rings)


@pytest.mark.parametrize("dimensions", [(2e-7, 2), (1e8, 1e-6), (1e-6, 1e8)])
def test_small_and_unequal_dimensions_keep_four_edges(dimensions):
    profile = cq.Workplane("XZ").rect(*dimensions)
    wire = profile.val()
    assert len(wire.Edges()) == len(wire.Vertices()) == 4
    assert wire.IsClosed()
    assert wire.Length() == pytest.approx(2 * sum(dimensions))


def test_array_placements_are_independent():
    wires = cq.Workplane().pushPoints([(0, 0), (10, 0)]).rect(2, 3).vals()
    second = wires[1].Center().toTuple()
    wires[0].move(cq.Location(100, 0, 0))
    assert wires[1].Center().toTuple() == second
    assert wires[0].Center().toTuple() == pytest.approx((100, 0, 0))
