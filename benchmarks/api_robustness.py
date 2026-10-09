"""Deterministic public-API workflows, each isolated from native crashes/hangs.

Run with the intended Python environment, e.g. python api_robustness.py
--output results.json. --source selects a source checkout; omit it to exercise
an installed package. This is correctness testing, never a speed benchmark.
Visited API members include incidental calls; they are not an exhaustive proof.
"""

import argparse
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import random
import resource
import subprocess
import sys
import tempfile
import traceback

CLASSES = (
    "Workplane",
    "Sketch",
    "Assembly",
    "Shape",
    "Vertex",
    "Edge",
    "Wire",
    "Face",
    "Shell",
    "Solid",
    "Compound",
    "Vector",
    "Matrix",
    "Plane",
    "Location",
    "BoundBox",
    "Color",
    "Material",
)
FAMILIES = ("profiles", "boolean", "sketch", "assembly", "roundtrip", "transform")
EDGE_CASES = (
    "retry_taper",
    "retry_loft",
    "retry_axis",
    "iterable_stack",
    "empty_combine",
    "invalid_selector",
    "box_nan",
    "box_inf",
    "circle_nan",
    "circle_inf",
    "extrude_nan",
    "extrude_inf",
    "callback_none",
    "callback_retry",
    "callback_prototype",
    "close_retry",
    "zero_twist",
    "assembly_collision",
    "free_functions",
    "operators",
)
# Coverage expansion (ROBUSTNESS.rst): coordinates and axes, offsets, spline and
# Bezier inputs, copy ownership and serialization failures.
COVERAGE_CASES = (
    "plane_frames",
    "location_axes",
    "offsets",
    "splines",
    "copy_ownership",
    "serialization_failures",
)

OPERATORS = {
    "__init__",
    "__iter__",
    "__getitem__",
    "__len__",
    "__bool__",
    "__add__",
    "__sub__",
    "__mul__",
    "__rmul__",
    "__truediv__",
    "__and__",
    "__or__",
    "__invert__",
    "__neg__",
    "__abs__",
    "__eq__",
    "__ne__",
    "__call__",
    "__getstate__",
    "__setstate__",
}


def member_info(value):
    try:
        signature = str(inspect.signature(value))
    except (TypeError, ValueError):
        signature = None
    info = {
        "signature": signature,
        "kind": "property" if isinstance(value, property) else "callable",
    }
    dispatcher = getattr(value, "__func__", value)
    if isinstance(dispatcher, dict):
        # Dispatchers expose implementations separately; a single signature
        # otherwise hides legitimate wire/face and tuple/vector overloads.
        overloads = set()
        for function in dispatcher.values():
            if callable(function):
                try:
                    overloads.add(str(inspect.signature(function)))
                except (TypeError, ValueError):
                    pass
        info["overloads"] = sorted(overloads)
    return info


def inventory(cq):
    result = {}
    for name in CLASSES:
        cls = getattr(cq, name)
        members = {}
        for member, value in inspect.getmembers(cls):
            if (member.startswith("_") and member not in OPERATORS) or not (
                callable(value) or isinstance(value, property)
            ):
                continue
            if member in OPERATORS and not getattr(value, "__module__", "").startswith(
                "cadquery"
            ):
                continue
            members[member] = member_info(value)
        result[name] = members
    from cadquery import func, cqgi

    for module in (cq.selectors, cq.exporters, cq.importers, func, cqgi):
        result[module.__name__] = {
            name: member_info(value)
            for name, value in inspect.getmembers(module)
            if not name.startswith("_")
            and callable(value)
            and getattr(value, "__module__", "").startswith("cadquery")
        }
    return result


def check(shape):
    if hasattr(shape, "toCompound"):
        shape = shape.toCompound()
    elif hasattr(shape, "findSolid"):
        shape = shape.findSolid()
    assert shape.isValid(), "invalid BRep"
    assert math.isfinite(shape.Volume()), "nonfinite mass"
    assert math.isfinite(shape.Area()), "nonfinite area"
    assert all(math.isfinite(v) for v in shape.Center().toTuple()), "nonfinite centroid"
    return shape


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-7), (a, b)


def workflow(cq, family, seed):
    rng = random.Random(seed)
    length, width, height = [rng.uniform(8, 16) for _ in range(3)]
    plane = rng.choice(["XY", "XZ", "YZ"])
    if family == "profiles":
        w = cq.Workplane(plane).rect(length, width).rect(length / 3, width / 3)
        both = rng.choice([True, False])
        direction = rng.choice([1, -1])
        r = check(w.extrude(direction * height, both=both))
        close(r.Volume(), length * width * 8 / 9 * height * (2 if both else 1))
        return
    if family == "boolean":
        base = cq.Workplane(plane).box(length, width, height).tag("base")
        result = (
            base.faces(">Z" if plane == "XY" else (">Y" if plane == "XZ" else ">X"))
            .workplane()
            .hole(2)
        )
        r = check(result)
        close(base.val().Volume(), length * width * height)
        assert r.Volume() < base.val().Volume()
        assert base._getTagged("base") is base
        # Reusing a parent must retain an independent geometric result.
        check(base.edges().fillet(0.2))
        check(base.faces().shell(0.2))
        return
    if family == "sketch":
        sketch = (
            cq.Sketch()
            .rect(length, width)
            .vertices()
            .fillet(0.5)
            .reset()
            .circle(1, mode="s")
        )
        result = cq.Workplane(plane).placeSketch(sketch).extrude(height)
        check(result)
        check(cq.Workplane(plane).placeSketch(sketch).extrude(-height))
        return
    if family == "assembly":
        part = cq.Workplane().box(length, width, height)
        source = cq.Assembly(name="group").add(part, name="part")
        root = cq.Assembly(name="root")
        for i in range(6):
            root.add(
                source, name=f"instance{i}", loc=cq.Location((i * length * 2, 0, 0))
            )
        child = root.objects["instance2"]
        child.add(part, name="extra", loc=cq.Location((0, width * 2, 0)))
        assert root.objects["instance2/extra"] is child.objects["extra"]
        root.remove("instance2/part")
        assert "part" not in child.objects
        assert "instance2/part" not in root.objects
        assert "part" in source.objects
        close(check(root).Volume(), 6 * length * width * height)
        copied = root._copy()
        copied.remove("instance0")
        close(check(copied).Volume(), 5 * length * width * height)
        assert "instance0" in root.objects
        return
    if family == "roundtrip":
        shape = check(
            cq.Workplane(plane).box(length, width, height).edges().chamfer(0.2)
        )
        with tempfile.TemporaryDirectory() as directory:
            for ext in ("step", "brep"):
                path = str(Path(directory) / f"part.{ext}")
                cq.exporters.export(shape, path)
                loaded = (
                    cq.importers.importStep(path)
                    if ext == "step"
                    else cq.importers.importBrep(path)
                )
                close(check(loaded).Volume(), shape.Volume())
                close(check(loaded).Area(), shape.Area())
            vertices, triangles = shape.tessellate(0.1, 0.2)
            assert vertices and triangles
            assert all(0 <= i < len(vertices) for tri in triangles for i in tri)
        return
    shape = check(cq.Workplane().box(length, width, height))
    location = cq.Location(
        (rng.uniform(-1e4, 1e4), 7, -3), (1, 2, 3), rng.uniform(-720, 720)
    )
    moved = shape.moved(location).moved(location.inverse)
    close(check(moved).Volume(), shape.Volume())
    delta = moved.cut(shape).Volume() + shape.cut(moved).Volume()
    assert abs(delta) < 1e-6, delta
    close(shape.Volume(), length * width * height)


def _near(a, b, tol=1e-9):
    a, b = tuple(a), tuple(b)
    assert len(a) == len(b) and all(
        math.isclose(x, y, abs_tol=tol) for x, y in zip(a, b)
    ), (a, b)


def _raises(call, kinds=(ValueError, TypeError)):
    try:
        call()
    except kinds:
        return
    except Exception as exc:
        # Native validation also counts as a clean refusal; a crash cannot reach here.
        if type(exc).__module__.startswith("OCP."):
            return
        raise
    raise AssertionError("invalid input unexpectedly accepted")


def coverage_case(cq, name):
    rng = random.Random(name)
    if name == "plane_frames":
        names = (
            "XY",
            "YZ",
            "ZX",
            "XZ",
            "YX",
            "ZY",
            "front",
            "back",
            "left",
            "right",
            "top",
            "bottom",
        )
        for stdName in names:
            origin = tuple(rng.uniform(-1e3, 1e3) for _ in range(3))
            p = cq.Plane.named(stdName, origin)
            q = getattr(cq.Plane, stdName)(origin)
            assert p == q, stdName
            assert math.isclose(p.xDir.dot(p.zDir), 0, abs_tol=1e-12)
            assert math.isclose(p.yDir.dot(p.zDir), 0, abs_tol=1e-12)
            _near(p.xDir.cross(p.yDir).toTuple(), p.zDir.toTuple(), 1e-12)
            _near(p.toWorldCoords((0, 0)).toTuple(), origin, 1e-9)
            for _ in range(8):
                point = cq.Vector(*(rng.uniform(-1e4, 1e4) for _ in range(3)))
                local = p.toLocalCoords(point)
                _near(p.toWorldCoords(local.toTuple()).toTuple(), point.toTuple(), 1e-7)
            # A named plane's own default x direction, given explicitly, is the same plane.
            assert getattr(cq.Plane, stdName)(origin, p.xDir) == p
            # Every other perpendicular x direction keeps the normal.
            turned = getattr(cq.Plane, stdName)(origin, p.yDir)
            _near(turned.zDir.toTuple(), p.zDir.toTuple(), 1e-12)
            _near(turned.xDir.toTuple(), p.yDir.toTuple(), 1e-12)
            # Plane objects are independent: changing one never moves another.
            p.origin = (1, 2, 3)
            _near(q.origin.toTuple(), origin, 1e-12)
        _raises(lambda: cq.Plane.named("diagonal"))
        _raises(lambda: cq.Plane((0, 0, 0), (1, 0, 0), (0, 0, 0)))
        _raises(lambda: cq.Plane((0, 0, 0), (0, 0, 1), (0, 0, 1)))
        _raises(lambda: cq.Plane.XY(xDir=(0, 0, 1)))
        rotated = cq.Plane.XY((5, 6, 7)).rotated((90, 0, 0))
        _near(rotated.zDir.toTuple(), (0, -1, 0), 1e-12)
        _near(rotated.origin.toTuple(), (5, 6, 7), 1e-12)
        return
    if name == "location_axes":
        for _ in range(12):
            t = tuple(rng.uniform(-1e3, 1e3) for _ in range(3))
            axis = tuple(rng.uniform(-1, 1) for _ in range(3))
            angle = rng.uniform(-720, 720)
            a = cq.Location(t, axis, angle)
            b = cq.Location(
                tuple(rng.uniform(-50, 50) for _ in range(3)),
                (rng.uniform(-90, 90), rng.uniform(-90, 90), rng.uniform(-90, 90)),
            )
            identity = (a * a.inverse).toTuple()
            _near(identity[0], (0, 0, 0), 1e-8)
            _near(identity[1], (0, 0, 0), 1e-9)
            point = cq.Vertex.makeVertex(*(rng.uniform(-10, 10) for _ in range(3)))
            # Composition order: (a * b) applies b first, then a.
            once = point.moved(a * b).Center()
            twice = point.moved(b).moved(a).Center()
            _near(once.toTuple(), twice.toTuple(), 1e-7)
            _near((a ** 2).toTuple()[0], (a * a).toTuple()[0], 1e-7)
            # A location from a plane maps local points like the plane does.
            plane = cq.Plane(
                t, (1, 0, 0), axis if any(abs(v) > 1e-3 for v in axis) else (0, 0, 1)
            )
            local = cq.Vector(
                rng.uniform(-5, 5), rng.uniform(-5, 5), rng.uniform(-5, 5)
            )
            _near(
                cq.Vertex.makeVertex(*local.toTuple())
                .moved(cq.Location(plane))
                .Center()
                .toTuple(),
                plane.toWorldCoords(local.toTuple()).toTuple(),
                1e-7,
            )
        # Workplane points on an offset, rotated plane are world points of that plane.
        plane = cq.Plane((7, -3, 5), (0, 1, 0), (1, 0, 0)).rotated((0, 0, 30))
        pts = [(1, 2), (-3, 4), (0, 0)]
        wp = cq.Workplane(plane).pushPoints(pts)
        for loc, (x, y) in zip(wp.vals(), pts):
            got = cq.Vertex.makeVertex(0, 0, 0).moved(loc).Center()
            _near(got.toTuple(), plane.toWorldCoords((x, y)).toTuple(), 1e-9)
        placed = (
            cq.Workplane(plane)
            .pushPoints(pts)
            .eachpoint(lambda l: cq.Vertex.makeVertex(0, 0, 0).moved(l), True)
        )
        for v, (x, y) in zip(placed.vals(), pts):
            _near(v.Center().toTuple(), plane.toWorldCoords((x, y)).toTuple(), 1e-9)
        # Affine matrices transform points (w=1), including non-uniform scale.
        m = cq.Matrix([[2, 0, 0, 1], [0, 3, 0, -2], [0, 0, 0.5, 4]])
        _near(cq.Vector(1, 1, 1).transform(m).toTuple(), (3, 1, 4.5), 1e-12)
        _near(
            cq.Vector(1, 1, 1).transform(m.inverse()).transform(m).toTuple(),
            (1, 1, 1),
            1e-12,
        )
        # Axis-based features: revolve about an arbitrary in-plane axis.
        ring = (
            cq.Workplane("XZ")
            .center(10, 0)
            .rect(2, 4)
            .revolve(360, (-10, -1), (-10, 1))
        )
        close(check(ring).Volume(), 2 * math.pi * 10 * 8)
        _raises(lambda: cq.Location((0, 0, 0), (0, 0, 0), 30))
        return
    if name == "offsets":
        # Planar wire offsets: an outward arc offset of a square adds a strip plus quarter circles.
        sq = cq.Wire.makePolygon(
            [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], close=True
        )
        out = sq.offset2D(1, "arc")
        assert len(out) == 1
        close(cq.Face.makeFromWires(out[0]).Area(), 100 + 40 + math.pi)
        sharp = sq.offset2D(1, "intersection")
        close(cq.Face.makeFromWires(sharp[0]).Area(), 144)
        inner = sq.offset2D(-2)
        close(cq.Face.makeFromWires(inner[0]).Area(), 36)
        # Offsetting a square inward past its half width leaves nothing (or raises), never a bogus wire.
        try:
            gone = sq.offset2D(-6)
        except Exception as exc:
            assert isinstance(exc, (ValueError,)) or type(exc).__module__.startswith(
                "OCP."
            ), exc
        else:
            assert all(cq.Face.makeFromWires(w).Area() < 1e-6 for w in gone) or not gone
        circle = cq.Wire.makeCircle(5, cq.Vector(), cq.Vector(0, 0, 1))
        close(cq.Face.makeFromWires(circle.offset2D(2)[0]).Area(), math.pi * 49)
        wp = cq.Workplane().rect(10, 10).offset2D(1, "intersection").extrude(2)
        close(check(wp).Volume(), 144 * 2)
        # Solid shells: inward and outward, with and without removed faces, and on located shapes.
        box = cq.Solid.makeBox(10, 10, 10)
        top = box.faces(">Z")
        close(check(box.hollow([top], -1)).Volume(), 1000 - 8 * 8 * 9)
        close(check(box.hollow([], -1)).Volume(), 1000 - 512)
        close(
            check(cq.Workplane().box(10, 10, 10).faces(">Z").shell(-1)).Volume(),
            1000 - 8 * 8 * 9,
        )
        outward = check(
            cq.Workplane().box(10, 10, 10).faces(">Z").shell(1, kind="intersection")
        ).Volume()
        close(outward, 12 * 12 * 11 - 1000)
        loc = cq.Location((3, -4, 5), (1, 1, 0), 37)
        moved = box.moved(loc)
        reference = box.hollow([top], -1)
        moved_top = [
            f
            for f in moved.Faces()
            if (f.Center() - top.moved(loc).Center()).Length < 1e-9
        ]
        assert len(moved_top) == 1
        shelled = check(moved.hollow(moved_top, -1))
        close(shelled.Volume(), reference.Volume())
        _near(shelled.Center().toTuple(), reference.moved(loc).Center().toTuple(), 1e-7)
        sphere = cq.Solid.makeSphere(5, angleDegrees1=-90, angleDegrees2=90)
        close(check(sphere.hollow([], -1)).Volume(), 4 / 3 * math.pi * (125 - 64))
        close(
            check(sphere.moved(loc).hollow([], -1)).Volume(),
            4 / 3 * math.pi * (125 - 64),
        )
        face = cq.Face.makePlane(4, 5)
        close(check(face.thicken(2)).Volume(), 40)
        _raises(lambda: box.hollow([top], float("nan")))
        return
    if name == "splines":
        pts = [
            cq.Vector(0, 0, 0),
            cq.Vector(3, 4, 0),
            cq.Vector(6, -1, 2),
            cq.Vector(10, 2, 1),
        ]
        e = cq.Edge.makeSpline(pts)
        for u, p in ((0, pts[0]), (1, pts[-1])):
            _near(e.positionAt(u).toTuple(), p.toTuple(), 1e-9)
        # Interpolation passes through every point.
        for p in pts:
            assert e.distance(cq.Vertex.makeVertex(*p.toTuple())) < 1e-6
        tangent = cq.Edge.makeSpline(
            pts, tangents=[cq.Vector(1, 0, 0), cq.Vector(0, 1, 0)]
        )
        _near(tangent.tangentAt(0).toTuple(), (1, 0, 0), 1e-9)
        _near(tangent.tangentAt(1).toTuple(), (0, 1, 0), 1e-9)
        periodic = cq.Edge.makeSpline(pts, periodic=True)
        assert periodic.IsClosed()
        params = cq.Edge.makeSpline(pts, parameters=[0, 1, 2, 3])
        _near(params.positionAt(0).toTuple(), pts[0].toTuple(), 1e-9)
        # Approximation stays within tolerance of the samples.
        samples = [cq.Vector(x / 4, math.sin(x / 4), 0) for x in range(40)]
        approx = cq.Edge.makeSplineApprox(samples, tol=1e-4)
        assert (
            max(approx.distance(cq.Vertex.makeVertex(*s.toTuple())) for s in samples)
            < 1e-3
        )
        smooth = cq.Edge.makeSplineApprox(samples, tol=1e-4, smoothing=(1, 1, 1))
        assert smooth.isValid()
        # Bézier: passes through its end points; control points shape the inside.
        bez = cq.Edge.makeBezier(
            [
                cq.Vector(0, 0, 0),
                cq.Vector(1, 2, 0),
                cq.Vector(3, 2, 0),
                cq.Vector(4, 0, 0),
            ]
        )
        _near(bez.positionAt(0).toTuple(), (0, 0, 0), 1e-12)
        _near(bez.positionAt(1).toTuple(), (4, 0, 0), 1e-12)
        _near(bez.positionAt(0.5, "parameter").toTuple(), (2, 1.5, 0), 1e-12)
        # Workplane/Sketch splines make solids.
        closed = (
            cq.Workplane()
            .spline([(0, 0), (4, 3), (8, 0), (4, -3)], periodic=True)
            .close()
        )
        assert check(closed.extrude(1)).Volume() > 0
        profile = (
            cq.Workplane()
            .moveTo(0, 0)
            .spline([(5, 2), (10, 0)], includeCurrent=True)
            .lineTo(10, -3)
            .lineTo(0, -3)
            .close()
        )
        check(profile.extrude(2))
        sk = (
            cq.Sketch()
            .segment((0, 0), (10, 0))
            .bezier([(10, 0), (12, 5), (-2, 5), (0, 0)])
            .assemble()
        )
        check(cq.Workplane().placeSketch(sk).extrude(1))
        # Invalid inputs are refused cleanly.
        _raises(lambda: cq.Edge.makeSpline([cq.Vector(0, 0, 0)]))
        _raises(
            lambda: cq.Edge.makeSpline(
                [cq.Vector(0, 0, 0), cq.Vector(float("nan"), 1, 0), cq.Vector(2, 0, 0)]
            )
        )
        _raises(lambda: cq.Edge.makeSpline(pts, parameters=[0, 1]))
        _raises(
            lambda: cq.Edge.makeSpline(
                [cq.Vector(0, 0, 0), cq.Vector(0, 0, 0), cq.Vector(0, 0, 0)]
            )
        )
        _raises(lambda: cq.Edge.makeBezier([cq.Vector(0, 0, 0)]))
        return
    if name == "copy_ownership":
        box = cq.Solid.makeBox(1, 2, 3)
        copy = box.copy()
        copy.move(cq.Location((10, 0, 0)))
        _near(box.Center().toTuple(), (0.5, 1, 1.5), 1e-12)
        _near(copy.Center().toTuple(), (10.5, 1, 1.5), 1e-12)
        moved = box.moved(cq.Location((0, 5, 0)))
        _near(box.Center().toTuple(), (0.5, 1, 1.5), 1e-12)
        _near(moved.Center().toTuple(), (0.5, 6, 1.5), 1e-12)
        # Vector results never alias their inputs.
        a, b = cq.Vector(1, 2, 3), cq.Vector(4, 5, 6)
        results = [
            a + b,
            a - b,
            a * 2,
            a.cross(b),
            a.normalized(),
            -a,
            a.multiply(1),
            cq.Vector(a),
        ]
        for r in results:
            assert r.wrapped is not a.wrapped and r.wrapped is not b.wrapped
        before = [r.toTuple() for r in results]
        a.x = 100
        b.wrapped.SetX(-7)
        assert [r.toTuple() for r in results] == before
        # Tuples are values.
        t = a.toTuple()
        a.y = 99
        assert t[1] == 2
        # Locations and planes copy by value through their public constructors.
        loc = cq.Location((1, 2, 3))
        loc2 = cq.Location(loc.wrapped)
        _near(loc2.toTuple()[0], (1, 2, 3), 1e-12)
        # Workplane(plane) keeps the caller's Plane object (upstream behavior);
        # every derived workplane holds its own copy.
        plane = cq.Plane.XY()
        derived = cq.Workplane(plane).rect(1, 1)
        plane.origin = (9, 9, 9)
        _near(derived.plane.origin.toTuple(), (0, 0, 0), 1e-12)
        # Workplane stacks are copied; the pending-profile context is shared by design.
        base = cq.Workplane().box(2, 2, 2)
        top = base.faces(">Z")
        assert base.vals() != top.vals() and len(base.vals()) == 1
        close(check(top.workplane().rect(1, 1).cutBlind(-1)).Volume(), 7)
        close(check(base).Volume(), 8)
        # Sketch and Assembly copies are independent.
        sk = cq.Sketch().rect(4, 4)
        sk2 = sk.copy().moved(cq.Location((10, 0, 0)))
        _near(sk._faces.Center().toTuple(), (0, 0, 0), 1e-12)
        assy = cq.Assembly(box, name="root")
        other = assy._copy()
        other.loc = cq.Location((5, 5, 5))
        _near(assy.loc.toTuple()[0], (0, 0, 0), 1e-12)
        # Pickled shapes and geometry come back equal and independent.
        import pickle

        for obj in (
            box,
            cq.Vector(1, 2, 3),
            cq.Location((1, 2, 3), (0, 0, 1), 30),
            cq.Plane.XZ((1, 2, 3)),
            cq.Matrix([[1, 0, 0, 1], [0, 1, 0, 2], [0, 0, 1, 3]]),
        ):
            back = pickle.loads(pickle.dumps(obj))
            if isinstance(obj, cq.Shape):
                close(back.Volume(), obj.Volume())
                assert back.wrapped.TShape() is not None
            elif isinstance(obj, cq.Location):
                _near(back.toTuple()[0], obj.toTuple()[0], 1e-12)
                _near(back.toTuple()[1], obj.toTuple()[1], 1e-12)
            elif isinstance(obj, cq.Matrix):
                assert back.__getstate__() == obj.__getstate__()
            else:
                assert back == obj
        return
    if name == "serialization_failures":
        import io
        import pickle

        box = cq.Solid.makeBox(1, 2, 3)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            missing = folder / "no-such-dir" / "part"
            for ext in ("step", "stl", "brep", "svg", "dxf", "vrml", "glb"):
                try:
                    cq.exporters.export(box, str(missing) + "." + ext)
                except Exception:
                    pass
                assert not missing.parent.exists()
            _raises(
                lambda: cq.exporters.export(box, str(folder / "part.unknown")),
                (ValueError, TypeError, KeyError),
            )
            for content in (b"", b"not a step file\n", b"ISO-10303-21;\nHEADER;\n"):
                bad = folder / "bad.step"
                bad.write_bytes(content)
                _raises(
                    lambda: cq.importers.importStep(str(bad)),
                    (ValueError, RuntimeError, OSError),
                )
            _raises(
                lambda: cq.importers.importStep(str(folder / "missing.step")),
                (ValueError, RuntimeError, OSError),
            )
            bad = folder / "bad.brep"
            bad.write_bytes(b"garbage")
            _raises(
                lambda: cq.Shape.importBrep(str(bad)),
                (ValueError, RuntimeError, OSError),
            )
            _raises(
                lambda: cq.Shape.importBrep(io.BytesIO(b"garbage")),
                (ValueError, RuntimeError, OSError),
            )
            _raises(
                lambda: cq.Shape.importBin(io.BytesIO(b"garbage")),
                (ValueError, RuntimeError, OSError),
            )
            _raises(lambda: pickle.loads(pickle.dumps(box)[:20]), (Exception,))
            # Round trips through memory and files keep the shape.
            for exporter, importer in (
                ("exportBrep", "importBrep"),
                ("exportBin", "importBin"),
            ):
                buf = io.BytesIO()
                getattr(box, exporter)(buf)
                buf.seek(0)
                close(check(getattr(cq.Shape, importer)(buf)).Volume(), 6)
            # A failed export leaves no partial file that later reads as a valid part.
            assy = cq.Assembly(box, name="part")
            try:
                assy.export(str(missing) + ".step")
            except Exception:
                pass
            assert not missing.parent.exists()
            good = folder / "ok.step"
            assy.export(str(good))
            close(check(cq.importers.importStep(str(good))).Volume(), 6)
            # Empty and nonsolid shapes export without crashing or raise cleanly.
            empty = cq.Compound.makeCompound([])
            try:
                cq.exporters.export(empty, str(folder / "empty.step"))
            except Exception as exc:
                assert isinstance(exc, (ValueError, RuntimeError)) or type(
                    exc
                ).__module__.startswith("OCP."), exc
        return
    raise AssertionError(f"unknown coverage case {name}")


def edge_case(cq, name):
    if name in COVERAGE_CASES:
        return coverage_case(cq, name)
    if name == "callback_none":
        for method in ("each", "eachpoint"):
            for local in (False, True):
                wp = cq.Workplane().pushPoints([(0, 0), (4, 0)])
                assert getattr(wp, method)(lambda v: None, local).vals() == []
        return
    if name == "callback_retry":
        wp = cq.Workplane().pushPoints([(0, 0), (4, 0)])
        calls = []

        def fail(point):
            calls.append(point)
            if len(calls) == 2:
                raise ValueError("callback failure")
            return cq.Wire.makeCircle(1, point, (0, 0, 1))

        try:
            wp.each(fail, combine=False)
        except ValueError:
            assert not wp.ctx.pendingWires
        else:
            raise AssertionError("callback did not fail")
        result = wp.each(
            lambda p: cq.Wire.makeCircle(1, p, (0, 0, 1)), combine=False
        ).extrude(3)
        close(check(result).Volume(), 6 * math.pi)
        return
    if name == "callback_prototype":
        wp = cq.Workplane(origin=(7, -3, 5)).pushPoints([(0, 0), (4, 0)])
        shared = cq.Wire.makeCircle(1, (0, 0, 0), (0, 0, 1))
        result = wp.eachpoint(lambda l: shared, True)
        assert all(math.isclose(v, 0, abs_tol=1e-10) for v in shared.Center().toTuple())
        assert all(
            all(
                math.isclose(a, b, abs_tol=1e-10)
                for a, b in zip(w.Center().toTuple(), (7, -3, 5))
            )
            for w in result.vals()
        )
        return
    if name == "close_retry":
        from unittest.mock import patch

        wp = cq.Workplane().lineTo(4, 0).lineTo(4, 3)
        before = wp.ctx.pendingEdges[:]
        with patch.object(cq.Wire, "assembleEdges", side_effect=ValueError("failure")):
            try:
                wp.close()
            except ValueError:
                assert wp.ctx.pendingEdges == before and wp.ctx.firstPoint is not None
            else:
                raise AssertionError("wire assembly did not fail")
        close(check(wp.close().extrude(2)).Volume(), 12)
        return
    if name == "zero_twist":
        close(
            check(cq.Workplane().rect(6, 4).rect(2, 1).twistExtrude(4, 0)).Volume(), 88
        )
        return
    if name == "assembly_collision":
        shape = cq.Solid.makeBox(1, 2, 3)
        root = cq.Assembly(name="root").add(shape, name="sub/part")
        original = root.objects.copy()
        try:
            root.add(cq.Assembly(name="sub").add(shape, name="part"))
        except ValueError:
            assert root.objects == original and len(root.children) == 1
        else:
            raise AssertionError("assembly path silently overwritten")
        close(check(root).Volume(), 6)
        return
    if name == "free_functions":
        from cadquery import func

        shape = func.extrude(func.face(func.rect(6, 4)), (0, 0, 4))
        close(check(shape).Volume(), 96)
        check(func.fillet(shape, shape.edges("|Z"), 0.3))
        close(check(func.cut(shape, func.cylinder(2, 4))).Volume(), 96 - 4 * math.pi)
        return
    if name == "operators":
        a, b = cq.Vector(2, -3, 6), cq.Vector(-1, 4, 2)
        assert (a + b).toTuple() == (1, 1, 8)
        assert (2 * a - b).toTuple() == (5, -10, 10)
        assert (-a).toTuple() == (-2, 3, -6)
        box = cq.Workplane().box(4, 4, 4)
        sphere = cq.Workplane().sphere(1)
        close(check(box - sphere).Volume(), 64 - 4 * math.pi / 3)
        close(check(box * sphere).Volume(), 4 * math.pi / 3)
        check(box + sphere)
        assert len(box.faces()[[0, -1]].vals()) == 2
        assert len(list(box)) == 1
        return
    if name.startswith("retry_"):
        if name == "retry_taper":
            w = cq.Workplane().rect(6, 6).rect(2, 2)
            operation, retry = lambda: w.extrude(3, taper=5), lambda: w.extrude(3)
        elif name == "retry_loft":
            w = cq.Workplane().circle(2)
            operation, retry = w.loft, lambda: w.workplane(offset=4).circle(1).loft()
        else:
            w = cq.Workplane().moveTo(3, 0).circle(1)
            operation = lambda: w.revolve(axisStart=(0, 0), axisEnd=(0, 0))
            retry = lambda: w.revolve(axisStart=(0, 0), axisEnd=(0, 1))
        saved = w.ctx.pendingWires[:]
        try:
            operation()
        except Exception:
            assert w.ctx.pendingWires == saved, "failed feature consumed its profiles"
        else:
            raise AssertionError("invalid operation unexpectedly accepted")
        check(retry())
        return
    if name == "iterable_stack":
        s = cq.Solid.makeBox(2, 3, 4)
        w = cq.Workplane().newObject([]).add(x for x in [s])
        assert w.vals() == [s], "generator stored on stack instead of its shapes"
        check(w)
        return
    if name == "empty_combine":
        w = cq.Workplane().newObject([])
        try:
            w.combine()
        except ValueError:
            pass
        else:
            raise AssertionError("empty combine must raise ValueError")
        check(w.add(cq.Solid.makeBox(2, 3, 4)).combine())
        return
    if name == "invalid_selector":
        w = cq.Workplane().box(2, 3, 4)
        try:
            w.faces(">Z junk trailing")
        except Exception:
            pass
        else:
            raise AssertionError("selector accepted trailing garbage")
        close(check(w).Volume(), 24)
        return
    kind, value = name.split("_")
    value = float(value)
    try:
        if kind == "box":
            result = cq.Workplane().box(value, 3, 4)
        elif kind == "circle":
            result = cq.Workplane().circle(value).extrude(3)
        else:
            result = cq.Workplane().rect(2, 3).extrude(value)
    except (ValueError, TypeError):
        return
    except Exception as exc:
        if type(exc).__module__.startswith("OCP."):
            return
        raise
    check(result)
    raise AssertionError("nonfinite dimension was accepted")


def worker(name, source):
    if source:
        sys.path.insert(0, str(Path(source).resolve()))
    import cadquery as cq
    from cadquery.occ_impl.shapes import setThreads

    setThreads(1)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Imports have completed; cap runaway geometry allocations without making
    # numpy/casadi address-space reservations determine the test outcome.
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    visited = set()

    def trace(frame, event, arg):
        if event == "call":
            module = frame.f_globals.get("__name__", "")
            if module.startswith("cadquery"):
                visited.add(module + ":" + frame.f_code.co_qualname)

    sys.setprofile(trace)
    error = None
    try:
        if ":" in name:
            family, seed = name.split(":")
            workflow(cq, family, int(seed))
        else:
            edge_case(cq, name)
    except Exception:
        error = traceback.format_exc()
    finally:
        sys.setprofile(None)
    print(
        "RESULT"
        + json.dumps(
            {
                "passed": error is None,
                "error": error,
                "visited_python_members": sorted(visited),
                "cadquery_file": cq.__file__,
            }
        ),
        flush=True,
    )
    raise SystemExit(1 if error else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker")
    parser.add_argument("--seeds", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--only", nargs="+")
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.source)
        return
    if args.output is None:
        parser.error("--output is required")
    if args.source:
        sys.path.insert(0, str(args.source.resolve()))
    import cadquery as cq

    cases = args.only or [
        f"{family}:{seed}" for family in FAMILIES for seed in range(args.seeds)
    ] + list(EDGE_CASES) + list(COVERAGE_CASES)
    report = {
        "complete": False,
        "cadquery_file": cq.__file__,
        "suite_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "api_inventory": inventory(cq),
        "method": "one fresh Python process per deterministic scenario; one native thread; 8 GiB address-space limit after import",
        "scope": "Public Python API inventory plus selected stateful scenarios. Visited methods are not exhaustive contract coverage.",
        "timeout_s": args.timeout,
        "cases": {},
    }
    env = dict(
        os.environ,
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        NUMBA_CACHE_DIR="/tmp/numba-cache",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name in cases:
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", name]
        if args.source:
            command += ["--source", str(args.source.resolve())]
        try:
            proc = subprocess.run(
                command, capture_output=True, text=True, timeout=args.timeout, env=env
            )
            payloads = [
                line[6:]
                for line in proc.stdout.splitlines()
                if line.startswith("RESULT")
            ]
            result = (
                json.loads(payloads[-1])
                if payloads
                else {
                    "passed": False,
                    "error": proc.stdout[-2000:] + proc.stderr[-4000:],
                }
            )
            result["returncode"] = proc.returncode
            result["passed"] = result["passed"] and proc.returncode == 0
        except subprocess.TimeoutExpired:
            result = {"passed": False, "timeout": True}
        report["cases"][name] = result
        print(name, "PASS" if result["passed"] else "FAIL", flush=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    report["complete"] = True
    report["passed"] = all(c["passed"] for c in report["cases"].values())
    report["visited_python_members"] = sorted(
        {
            member
            for case in report["cases"].values()
            for member in case.get("visited_python_members", [])
        }
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
