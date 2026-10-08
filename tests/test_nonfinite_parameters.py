"""Reject nonfinite dimensions before native builders can hang or corrupt a BRep."""

import math
import cadquery as cq
import pytest


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize(
    "kind,parameters",
    [
        ("makeBox", dict(length=2, width=3, height=4)),
        ("makeCone", dict(radius1=2, radius2=1, height=4, angleDegrees=360)),
        ("makeCylinder", dict(radius=2, height=4, angleDegrees=360)),
        (
            "makeSphere",
            dict(radius=2, angleDegrees1=-90, angleDegrees2=90, angleDegrees3=360),
        ),
        ("makeTorus", dict(radius1=3, radius2=1, angleDegrees1=0, angleDegrees2=360)),
        ("makeWedge", dict(dx=2, dy=3, dz=4, xmin=0, zmin=0, xmax=1, zmax=2)),
        ("makeCircle", dict(radius=2, angle1=0, angle2=90)),
    ],
)
def test_native_primitive_dimensions_are_checked_before_building(kind, parameters, bad):
    cls = cq.Edge if kind == "makeCircle" else cq.Solid
    for parameter in parameters:
        with pytest.raises(ValueError, match=f"{parameter} must be finite"):
            getattr(cls, kind)(**{**parameters, parameter: bad})
    assert getattr(cls, kind)(**parameters).isValid()


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize(
    "method,parameters",
    [
        ("box", dict(length=2, width=3, height=4)),
        ("cylinder", dict(height=4, radius=2, angle=360)),
        ("sphere", dict(radius=2, angle1=-90, angle2=90, angle3=360)),
        ("circle", dict(radius=2)),
    ],
)
def test_workplane_primitive_rejection_keeps_context_usable(method, parameters, bad):
    wp = cq.Workplane()
    for parameter in parameters:
        with pytest.raises(ValueError, match="must be finite"):
            getattr(wp, method)(**{**parameters, parameter: bad})
        assert not wp.ctx.pendingWires and not wp.ctx.pendingEdges
    result = getattr(wp, method)(**parameters)
    assert result.val().isValid()


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize(
    "method,parameter",
    [
        ("extrude", "until"),
        ("extrude", "taper"),
        ("cutBlind", "until"),
        ("cutBlind", "taper"),
        ("twistExtrude", "distance"),
        ("twistExtrude", "angleDegrees"),
        ("revolve", "angleDegrees"),
    ],
)
def test_nonfinite_feature_parameter_raises_and_preserves_profile(
    method, parameter, bad
):
    wp = cq.Workplane().box(10, 10, 4).faces(">Z").workplane().circle(1)
    wires = wp.ctx.pendingWires[:]
    params = {
        "extrude": {"until": 3},
        "cutBlind": {"until": -3},
        "twistExtrude": {"distance": 3, "angleDegrees": 15},
        "revolve": {"angleDegrees": 90, "axisStart": (3, 0), "axisEnd": (3, 1)},
    }[method]
    with pytest.raises(ValueError, match="must be finite"):
        getattr(wp, method)(**{**params, parameter: bad})
    assert wp.ctx.pendingWires == wires
    assert getattr(wp, method)(**params).val().isValid()


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("wire_overload", [False, True])
def test_raw_extrusion_rejects_nonfinite_vectors(bad, axis, wire_overload):
    wire = cq.Workplane().rect(2, 3).val()
    vector = [0, 0, 4]
    vector[axis] = bad
    vector = tuple(vector)
    with pytest.raises(ValueError, match=f'vecNormal_{"xyz"[axis]} must be finite'):
        if wire_overload:
            cq.Solid.extrudeLinear(wire, [], vector)
        else:
            cq.Solid.extrudeLinear(cq.Face.makeFromWires(wire), vector)


@pytest.mark.parametrize("dimensions", [(2, 3, 4), (2e-4, 3e-4, 4e-4), (2e6, 3e6, 4e6)])
def test_finite_dimensions_keep_existing_geometry(dimensions):
    shape = cq.Solid.makeBox(*dimensions)
    assert shape.isValid()
    assert shape.Volume() == pytest.approx(abs(math.prod(dimensions)))
