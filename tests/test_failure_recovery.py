"""Users must be able to correct a failed feature and retry its profiles."""

import inspect
import math
import sys

import cadquery as cq
import pytest
from OCP.Standard import Standard_ConstructionError
from multimethod import DispatchError


def snapshot(wp):
    ctx = wp.ctx
    return (
        ctx.pendingWires,
        ctx.pendingWires[:],
        ctx.pendingEdges,
        ctx.pendingEdges[:],
        ctx.firstPoint,
    )


def unchanged(wp, before):
    wires, saved_wires, edges, saved_edges, first_point = before
    assert wp.ctx.pendingWires is wires
    assert wp.ctx.pendingEdges is edges
    assert wp.ctx.pendingWires == saved_wires
    assert wp.ctx.pendingEdges == saved_edges
    assert wp.ctx.firstPoint is first_point


@pytest.mark.parametrize(
    "scenario", ["tapered_ring", "single_loft", "zero_extrude", "zero_axis"]
)
def test_native_and_validation_failures_can_be_corrected(scenario):
    if scenario == "tapered_ring":
        wp = cq.Workplane().rect(6, 6).rect(2, 2)
        bad = lambda: wp.extrude(3, taper=5)
        good = lambda: wp.extrude(3)
        expected = 96
        error = ValueError
    elif scenario == "single_loft":
        wp = cq.Workplane().circle(2)
        bad = wp.loft
        good = lambda: wp.workplane(offset=4).circle(1).loft()
        expected = math.pi * 28 / 3
        error = ValueError
    elif scenario == "zero_extrude":
        wp = cq.Workplane().rect(2, 3)
        bad = lambda: wp.extrude(0)
        good = lambda: wp.extrude(4)
        expected = 24
        error = Standard_ConstructionError
    else:
        wp = cq.Workplane().moveTo(3, 0).circle(1)
        bad = lambda: wp.revolve(axisStart=(0, 0), axisEnd=(0, 0))
        good = lambda: wp.revolve(axisStart=(0, 0), axisEnd=(0, 1))
        expected = 6 * math.pi**2
        error = Standard_ConstructionError
    before = snapshot(wp)
    for _ in range(2):
        with pytest.raises(error):
            bad()
        unchanged(wp, before)
    result = good()
    assert result.val().isValid()
    assert result.val().Volume() == pytest.approx(expected)
    assert not wp.ctx.pendingWires


@pytest.mark.parametrize("keyword_path", [False, True])
def test_sweep_failure_restores_profile_and_path_contexts(keyword_path):
    profile = cq.Workplane().circle(1)
    path = cq.Workplane("XZ").moveTo(0, 0).lineTo(0, 4)
    before_profile, before_path = snapshot(profile), snapshot(path)
    with pytest.raises(DispatchError):
        if keyword_path:
            profile.sweep(path=path, transition="misspelled")
        else:
            profile.sweep(path, transition="misspelled")
    unchanged(profile, before_profile)
    unchanged(path, before_path)
    result = profile.sweep(path)
    assert result.val().isValid()
    assert result.val().Volume() == pytest.approx(4 * math.pi)
    assert not profile.ctx.pendingWires
    assert not path.ctx.pendingEdges


@pytest.mark.parametrize(
    "method",
    ["extrude", "twistExtrude", "revolve", "sweep", "loft", "cutBlind", "cutThruAll"],
)
@pytest.mark.parametrize("stage", ["boolean", "clean"])
def test_failures_after_profile_consumption_restore_shared_context(
    monkeypatch, method, stage
):
    # Force a failure after the native feature has succeeded, rather than
    # testing just a Python argument error before consuming the profiles.
    base = cq.Workplane().box(10, 10, 4)
    wp = base.faces(">Z").workplane().circle(1)
    if method == "loft":
        wp = wp.workplane(offset=3).circle(0.5)
    before = snapshot(wp)
    original = (
        cq.Shape.clean
        if stage == "clean"
        else (cq.Shape.cut if method.startswith("cut") else cq.Shape.fuse)
    )

    class Failure(Exception):
        pass

    def fail(*args, **kwargs):
        raise Failure("post-feature failure")

    if stage == "clean":
        monkeypatch.setattr(cq.Shape, "clean", fail)
    else:
        if method == "cutThruAll":
            # dprism combines internally rather than calling Shape.cut.
            original = cq.Solid.dprism

            def fail_dprism(*args, **kwargs):
                original(*args, **kwargs)
                raise Failure("post-feature failure")

            monkeypatch.setattr(cq.Solid, "dprism", fail_dprism)
        else:
            monkeypatch.setattr(
                cq.Shape, "cut" if method.startswith("cut") else "fuse", fail
            )

    def operation():
        if method == "extrude":
            return wp.extrude(3)
        if method == "twistExtrude":
            return wp.twistExtrude(3, 15)
        if method == "revolve":
            return wp.revolve(90, axisStart=(3, 0), axisEnd=(3, 1))
        if method == "sweep":
            return wp.sweep(cq.Edge.makeLine((0, 0, 2), (0, 0, 5)))
        if method == "loft":
            return wp.loft()
        if method == "cutBlind":
            return wp.cutBlind(-3)
        return wp.cutThruAll()

    with pytest.raises(Failure):
        operation()
    unchanged(wp, before)
    assert base.ctx is wp.ctx
    assert base.val().isValid()
    assert base.val().Volume() == pytest.approx(400)
    monkeypatch.undo()
    result = operation()
    assert result.val().isValid()
    assert not wp.ctx.pendingWires


def test_wire_failure_and_interrupt_restore_edges_and_cursor(monkeypatch):
    wp = cq.Workplane().moveTo(1, 2).lineTo(3, 2).lineTo(3, 4)
    before = snapshot(wp)

    def fail(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(cq.Wire, "assembleEdges", fail)
    with pytest.raises(KeyboardInterrupt):
        wp.wire()
    unchanged(wp, before)
    monkeypatch.undo()
    assert len(wp.wire().val().Edges()) == 2
    assert not wp.ctx.pendingEdges


def test_decorated_api_keeps_signatures_and_workplane_subclasses():
    class CustomWorkplane(cq.Workplane):
        pass

    assert "until" in inspect.signature(cq.Workplane.extrude).parameters
    assert cq.Workplane.extrude.__doc__.startswith("\n        Use all un-extruded")
    wp = CustomWorkplane().rect(2, 3)
    with pytest.raises(Standard_ConstructionError):
        wp.extrude(0)
    assert isinstance(wp.extrude(4), CustomWorkplane)


def _top_rect():
    return cq.Workplane().box(4, 4, 4).faces(">Z").workplane().rect(1, 1)


@pytest.mark.parametrize(
    "name, operation",
    [
        ("wire", lambda: cq.Workplane().moveTo(1, 0).lineTo(2, 0).lineTo(2, 1).wire()),
        ("each", lambda: cq.Workplane().rect(2, 2).vertices().each(lambda v: None)),
        (
            "eachpoint",
            lambda: cq.Workplane().rect(2, 2).vertices().eachpoint(lambda l: None),
        ),
        ("close", lambda: cq.Workplane().lineTo(1, 0).lineTo(1, 1).close()),
        ("twistExtrude", lambda: cq.Workplane().rect(2, 2).twistExtrude(3, 10)),
        ("extrude", lambda: cq.Workplane().rect(2, 2).extrude(3)),
        (
            "revolve",
            lambda: cq.Workplane().moveTo(3, 0).rect(1, 1).revolve(90, (0, 0), (0, 1)),
        ),
        (
            "sweep",
            lambda: cq.Workplane().circle(1).sweep(cq.Workplane("XZ").lineTo(0, 5)),
        ),
        ("cutBlind", lambda: _top_rect().cutBlind(-1)),
        ("cutThruAll", lambda: _top_rect().cutThruAll()),
        (
            "loft",
            lambda: cq.Workplane().rect(2, 2).workplane(offset=2).circle(1).loft(),
        ),
    ],
)
def test_guarded_operations_run_in_their_own_frame(name, operation):
    # Tracers, profilers and history recorders identify an operation by the
    # frame its call site enters: its code, name and bound arguments. A
    # wrapper frame in between hides all three.
    call_site = operation.__code__
    frame = None

    def profile(f, event, arg):
        nonlocal frame
        if (
            event == "call"
            and frame is None
            and f.f_back is not None
            and f.f_back.f_code is call_site
            and f.f_globals.get("__name__") == "cadquery.cq"
            and f.f_code.co_name in (name, "wrapped")
        ):
            frame = f

    previous = sys.getprofile()
    sys.setprofile(profile)
    try:
        operation()
    finally:
        sys.setprofile(previous)
    assert frame is not None, f"{name} was not entered from its call site"
    code = frame.f_code
    assert code.co_name == name
    # The entered frame binds the documented parameters by name.
    bound = code.co_varnames[: code.co_argcount + code.co_kwonlyargcount]
    assert list(bound) == list(
        inspect.signature(getattr(cq.Workplane, name)).parameters
    )
    assert frame.f_locals["self"].__class__ is cq.Workplane


@pytest.mark.parametrize("container", [tuple, iter, lambda xs: (x for x in xs)])
def test_add_accepts_its_documented_iterable_input(container):
    solids = [cq.Solid.makeBox(1, 2, 3), cq.Solid.makeSphere(2)]
    wp = cq.Workplane().newObject([]).add(container(solids))
    assert wp.vals() == solids
    assert len(wp.solids().vals()) == 2


@pytest.mark.parametrize("kind", ["vector", "wire", "compound", "sketch", "location"])
def test_add_does_not_expand_single_iterable_cad_objects(kind):
    objects = {
        "vector": cq.Vector(1, 2, 3),
        "wire": cq.Wire.makeCircle(2, (0, 0, 0), (0, 0, 1)),
        "compound": cq.Compound.makeCompound([cq.Solid.makeBox(1, 2, 3)]),
        "sketch": cq.Sketch().rect(2, 3),
        "location": cq.Location((1, 2, 3)),
    }
    obj = objects[kind]
    assert cq.Workplane().newObject([]).add(obj).vals() == [obj]


def test_generator_failure_does_not_partially_change_stack():
    solid = cq.Solid.makeBox(1, 2, 3)
    wp = cq.Workplane().newObject([solid])

    def broken():
        yield cq.Solid.makeSphere(1)
        raise ValueError("iterator failed")

    with pytest.raises(ValueError, match="iterator failed"):
        wp.add(broken())
    assert wp.vals() == [solid]


def test_empty_combine_raises_documented_exception_and_can_be_reused():
    wp = cq.Workplane().newObject([])
    with pytest.raises(ValueError, match="No shapes"):
        wp.combine()
    assert wp.add(cq.Solid.makeBox(1, 2, 3)).combine().val().Volume() == pytest.approx(
        6
    )
