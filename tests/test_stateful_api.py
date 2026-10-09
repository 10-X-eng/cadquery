"""Stateful callback, wire closure, zero-angle and assembly name contracts."""

import math
from unittest.mock import patch

import cadquery as cq
import pytest

from .test_failure_recovery import snapshot, unchanged


@pytest.mark.parametrize("method", ["each", "eachpoint"])
@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("mode", [False, True, "a", "cut", "s"])
@pytest.mark.parametrize("has_base", [False, True])
def test_all_none_callback_results_are_omitted(method, local, mode, has_base):
    wp = cq.Workplane().box(10, 10, 4) if has_base else cq.Workplane()
    wp = wp.pushPoints([(0, 0), (3, 0)])
    before = snapshot(wp)
    result = getattr(wp, method)(
        lambda value: None, useLocalCoordinates=local, combine=mode
    )
    assert None not in result.vals()
    if has_base and mode:
        assert result.val().isValid()
        assert result.val().Volume() == pytest.approx(400)
    else:
        assert result.vals() == []
    unchanged(wp, before)


@pytest.mark.parametrize("method", ["each", "eachpoint"])
@pytest.mark.parametrize("local", [False, True])
def test_mixed_none_and_shape_results_keep_locations(method, local):
    plane = cq.Plane((7, -3, 5), (0, 1, 0), (0, 0, 1))
    points = [(0, 0), (3, 0), (6, 0)]
    wp = cq.Workplane(plane).pushPoints(points)
    calls = []

    def callback(value):
        calls.append(value)
        if len(calls) == 2:
            return None
        shape = cq.Solid.makeSphere(0.5, angleDegrees1=-90)
        if method == "eachpoint":
            return shape.moved(value)
        return shape.translate(value)

    result = getattr(wp, method)(callback, useLocalCoordinates=local, combine=False)
    assert len(result.vals()) == 2
    for shape, point in zip(result.vals(), (points[0], points[2])):
        assert shape.isValid()
        assert shape.Center().toTuple() == pytest.approx(
            plane.toWorldCoords(point).toTuple()
        )
        assert shape.Volume() == pytest.approx(math.pi / 6)


@pytest.mark.parametrize("method", ["each", "eachpoint"])
@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("callback_edits", [False, True])
def test_callback_failure_restores_pending_geometry_and_allows_retry(
    method, local, callback_edits
):
    wp = cq.Workplane().rect(2, 2).pushPoints([(0, 0), (4, 0)])
    before = snapshot(wp)
    calls = []

    def fail(value):
        calls.append(value)
        if callback_edits:
            # Real modeling APIs in a callback share the surrounding context.
            wp.circle(0.25)
        if len(calls) == 2:
            raise ValueError("callback failed midway")
        return cq.Wire.makeCircle(1, (0, 0, 0), (0, 0, 1))

    with pytest.raises(ValueError, match="callback failed midway"):
        getattr(wp, method)(fail, useLocalCoordinates=local, combine=False)
    unchanged(wp, before)
    wp.ctx.popPendingWires()

    def good(value):
        wire = cq.Wire.makeCircle(1, (0, 0, 0), (0, 0, 1))
        return wire.moved(value) if method == "eachpoint" else wire.translate(value)

    result = getattr(wp, method)(
        good, useLocalCoordinates=local, combine=False
    ).extrude(3, combine=False)
    assert len(result.solids().vals()) == 2
    assert all(shape.isValid() for shape in result.vals())
    assert sum(s.Volume() for s in result.solids().vals()) == pytest.approx(6 * math.pi)


@pytest.mark.parametrize("method", ["each", "eachpoint"])
@pytest.mark.parametrize("mode", ["invalid", 2, None])
def test_invalid_combine_mode_raises_clear_error_without_leaving_wires(method, mode):
    wp = cq.Workplane().pushPoints([(0, 0), (4, 0)])
    before = snapshot(wp)
    with pytest.raises(ValueError, match="Unsupported combine mode"):
        getattr(wp, method)(
            lambda value: cq.Wire.makeCircle(1, (0, 0, 0), (0, 0, 1)), combine=mode
        )
    unchanged(wp, before)


def test_local_eachpoint_does_not_mutate_reused_callback_shape():
    wp = cq.Workplane(cq.Plane((7, -3, 5), (0, 1, 0), (0, 0, 1))).pushPoints(
        [(0, 0), (4, 0)]
    )
    shared = cq.Wire.makeCircle(1, (0, 0, 0), (0, 0, 1))
    result = wp.eachpoint(lambda location: shared, useLocalCoordinates=True)
    assert shared.Center().toTuple() == pytest.approx((0, 0, 0))
    assert result.vals()[0] is not result.vals()[1]
    assert all(w.Center().toTuple() == pytest.approx((7, -3, 5)) for w in result.vals())
    result.vals()[0].move(cq.Location((100, 0, 0)))
    assert result.vals()[1].Center().toTuple() == pytest.approx((7, -3, 5))
    assert shared.Center().toTuple() == pytest.approx((0, 0, 0))


@pytest.mark.parametrize("error", [ValueError, KeyboardInterrupt])
@pytest.mark.parametrize("already_closed", [False, True])
def test_failed_close_restores_edges_and_cursor(error, already_closed):
    wp = cq.Workplane().moveTo(0, 0).lineTo(4, 0).lineTo(4, 3)
    if already_closed:
        wp = wp.lineTo(0, 0)
    before = snapshot(wp)
    with patch.object(cq.Wire, "assembleEdges", side_effect=error("closure failed")):
        for _ in range(2):
            with pytest.raises(error):
                wp.close()
            unchanged(wp, before)
    result = wp.close().extrude(2)
    assert result.val().isValid()
    assert result.val().Volume() == pytest.approx(12)
    assert not wp.ctx.pendingEdges and not wp.ctx.pendingWires
    assert wp.ctx.firstPoint is None


@pytest.mark.parametrize("plane", ["XY", "XZ", "YZ"])
@pytest.mark.parametrize("height", [4, -4])
@pytest.mark.parametrize("profile", ["rect", "ring", "circle"])
@pytest.mark.parametrize("clean", [False, True])
def test_zero_angle_twist_matches_linear_extrusion(plane, height, profile, clean):
    def make():
        wp = cq.Workplane(plane)
        if profile == "circle":
            return wp.circle(2)
        wp = wp.rect(6, 4)
        return wp.rect(2, 1) if profile == "ring" else wp

    actual = make().twistExtrude(height, 0, clean=clean).val()
    expected = make().extrude(height, clean=clean).val()
    assert actual.isValid()
    assert actual.Volume() == pytest.approx(expected.Volume())
    assert actual.Area() == pytest.approx(expected.Area())
    assert actual.Center().toTuple() == pytest.approx(expected.Center().toTuple())
    assert len(actual.Faces()) == len(expected.Faces())
    assert abs(actual.cut(expected).Volume()) < 1e-8
    assert abs(expected.cut(actual).Volume()) < 1e-8


def test_raw_zero_angle_twist_overloads_and_follow_on_features():
    wire = cq.Workplane().rect(6, 4).val()
    face = cq.Face.makeFromWires(wire)
    for args in [
        (face, (10, 0, 0), (0, 0, 4), 0),
        (wire, [], (10, 0, 0), (0, 0, 4), 0),
    ]:
        result = cq.Solid.extrudeLinearWithRotation(*args)
        assert result.isValid()
        assert result.Volume() == pytest.approx(96)
    result = (
        cq.Workplane()
        .rect(6, 4)
        .twistExtrude(4, 0)
        .edges("|Z")
        .fillet(0.3)
        .faces(">Z")
        .workplane()
        .hole(1)
    )
    assert result.val().isValid()
    assert result.val().Volume() < 96


def indexes(assembly):
    return [
        (node, node.children[:], node.objects.copy(), node.parent)
        for _, node in assembly.traverse()
    ]


def assert_indexes_unchanged(before):
    for node, children, objects, parent in before:
        assert node.children == children
        assert node.objects == objects
        assert node.parent is parent


@pytest.mark.parametrize("order", ["literal_first", "nested_first"])
def test_assembly_path_collisions_are_rejected_atomically(order):
    shape = cq.Solid.makeBox(1, 2, 3)
    root = cq.Assembly(name="root")
    sub = cq.Assembly(name="sub").add(shape, name="part")
    if order == "literal_first":
        root.add(shape, name="sub/part")
        operation = lambda: root.add(sub)
    else:
        root.add(sub)
        operation = lambda: root.add(shape, name="sub/part")
    before = indexes(root)
    with pytest.raises(ValueError, match="Unique (path|name)"):
        operation()
    assert_indexes_unchanged(before)
    root.add(shape, name="safe")
    assert root.toCompound().isValid()
    assert root.toCompound().Volume() == pytest.approx(12)


def test_owned_subassembly_add_checks_all_ancestor_paths():
    shape = cq.Solid.makeBox(1, 2, 3)
    root = cq.Assembly(name="root").add(shape, name="sub/new/part")
    root.add(cq.Assembly(name="sub"))
    owner = root.objects["sub"]
    child = cq.Assembly(name="new").add(shape, name="part")
    before = indexes(root)
    with pytest.raises(ValueError, match="Unique path"):
        owner.add(child)
    assert_indexes_unchanged(before)
    assert child.parent is None
    owner.add(shape, name="safe")
    assert root.objects["sub/safe"] is owner.objects["safe"]
    assert root.objects["sub/new/part"].parent is root


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("kind", ["shape", "workplane", "callback"])
@pytest.mark.parametrize(
    "axis", ["Vector", "Vertex", "Face", "Sketch", "Location", "empty"]
)
def test_eachpoint_composes_rotated_plane_before_local_placement(local, kind, axis):
    plane = cq.Plane((7, -3, 5), (0, 1, 0), (0, 0, 1))
    target = plane.toWorldCoords((4, 2, 0))
    if axis == "Vector":
        objects = [target]
    elif axis == "Vertex":
        objects = [cq.Vertex.makeVertex(*target.toTuple())]
    elif axis == "Face":
        objects = [cq.Face.makePlane(2, 2).translate(target)]
    elif axis == "Sketch":
        objects = [cq.Sketch().rect(2, 2).moved(target.toTuple())]
    elif axis == "Location":
        objects = [cq.Location((4, 2, 0), (0, 0, 1), 30)]
    else:
        objects = []
        target = plane.origin
    wp = cq.Workplane(plane).newObject(objects)
    prototype = cq.Solid.makeBox(1, 2, 3).translate((-0.5, -1, -1.5))
    if kind == "shape":
        arg = prototype
    elif kind == "workplane":
        arg = cq.Workplane().newObject([prototype])
    else:
        arg = lambda location: prototype.moved(location)
    result = wp.eachpoint(arg, useLocalCoordinates=local)
    assert result.val().isValid()
    assert result.val().Center().toTuple() == pytest.approx(target.toTuple())
    assert result.val().Volume() == pytest.approx(6)
    angle = math.radians(120 if axis == "Location" else 90)
    bounds = result.val().BoundingBox()
    assert (bounds.xlen, bounds.ylen, bounds.zlen) == pytest.approx(
        (
            abs(math.cos(angle)) + 2 * abs(math.sin(angle)),
            abs(math.sin(angle)) + 2 * abs(math.cos(angle)),
            3,
        )
    )
    assert prototype.Center().toTuple() == pytest.approx((0, 0, 0))
