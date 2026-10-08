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
)


def inventory(cq):
    result = {}
    for name in CLASSES:
        cls = getattr(cq, name)
        members = {}
        for member, value in inspect.getmembers(cls):
            if member.startswith("_") or not (
                callable(value) or isinstance(value, property)
            ):
                continue
            try:
                signature = str(inspect.signature(value))
            except (TypeError, ValueError):
                signature = None
            members[member] = {
                "signature": signature,
                "kind": "property" if isinstance(value, property) else "callable",
            }
        result[name] = members
    for module in (cq.selectors, cq.exporters, cq.importers):
        result[module.__name__] = {
            name: {"kind": "callable"}
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


def edge_case(cq, name):
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
    ] + list(EDGE_CASES)
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
