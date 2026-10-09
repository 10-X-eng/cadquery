"""cadquery.occ_compat: OCP 7.x names on top of OCP 8.

enable() changes the OCP modules for the whole process, so every test that calls it
runs in a forked child: the rest of the suite keeps seeing plain OCP 8.

testdata/occ_compat_fclass2d.json.gz is the reference for the BRepTopAdaptor_FClass2d
stand-in: 46 faces (BRep text) of varied cadquery 2.8.0 solids, points over and around
each face's (u, v) domain, and the states OCP 7.9.3's real BRepTopAdaptor_FClass2d
returned for them (Perform with and without periodic recentring, TestOnRestriction at
three tolerances, PerformInfinitePoint; face tolerances 1e-7 and 1e-4).
"""

import gzip
import io
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import cadquery as cq
from cadquery import occ_compat

TESTDATA = Path(__file__).parent / "testdata"

# Old names production designs use (counted across users' designs; no code was read).
PRODUCTION_STATICS = [
    ("TopoDS", "TopoDS", "Shell_s"),
    ("TopoDS", "TopoDS", "Edge_s"),
    ("BRep", "BRep_Tool", "Surface_s"),
    ("ShapeCustom", "ShapeCustom", "ConvertToBSpline_s"),
    ("BRepGProp", "BRepGProp", "VolumeProperties_s"),
]
PRODUCTION_TYPEDEFS = [
    ("TColStd", "TColStd_Array1OfInteger", "Array1_int"),
    ("TColStd", "TColStd_Array1OfReal", "Array1_double"),
    ("TColStd", "TColStd_Array2OfReal", "Array2_double"),
    ("TColgp", "TColgp_Array1OfPnt", "Array1_gp_Pnt"),
    ("TColgp", "TColgp_Array2OfPnt", "Array2_gp_Pnt"),
]
PRODUCTION_MODULES = (
    "gp BRepAdaptor BRepBuilderAPI BRepOffsetAPI BRepFilletAPI BRepAlgoAPI TColgp BRepPrimAPI "
    "Geom GeomAbs ShapeCustom TColStd TopoDS TopAbs GeomLProp TopExp ShapeFix BRepCheck "
    "BRepExtrema BRepGProp GProp BRep GeomAPI"
).split()


_ISOLATED = {}


def isolated(fn):
    """Run the test in a fresh interpreter, so enable() never leaks into other tests
    (a forked child could deadlock on locks held by OCCT's threads)."""

    _ISOLATED[fn.__name__] = fn

    def wrapper():
        root = str(Path(__file__).resolve().parents[1])
        code = (
            f"import sys; sys.path.insert(0, {root!r}); "
            f"from tests import test_occ_compat as t; t._ISOLATED[{fn.__name__!r}]()"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=900
        )
        if proc.returncode:
            pytest.fail(proc.stdout + proc.stderr, pytrace=False)

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def ocp_module(name):
    import OCP.OCP as ocp

    return getattr(ocp, name)


def snapshot():
    """Every name OCP 8 defines (modules, classes, namespaces) and what it is bound to."""

    import OCP.OCP as ocp

    names = {}
    for mod_name, mod in vars(ocp).items():
        if type(mod).__name__ != "module" or mod.__name__ != "OCP.OCP." + mod_name:
            continue
        for name, value in vars(mod).items():
            names[f"{mod_name}.{name}"] = value
            if isinstance(value, type) or type(value).__name__ == "module":
                for attr, raw in list(vars(value).items()):
                    names[f"{mod_name}.{name}.{attr}"] = raw
    return names


def test_nothing_happens_on_import():
    assert "cadquery.occ_compat" in sys.modules  # imported above, with cadquery
    assert not occ_compat.enabled()
    assert occ_compat.restored() == {}
    from OCP.TopoDS import TopoDS
    import OCP.TColStd

    assert not hasattr(TopoDS, "Face_s")
    assert not hasattr(OCP.TColStd, "TColStd_Array1OfReal")
    assert not hasattr(ocp_module("BRepTopAdaptor"), "BRepTopAdaptor_FClass2d")


@isolated
def test_production_names():
    occ_compat.enable()

    for mod_name, owner, name in PRODUCTION_STATICS:
        cls = getattr(ocp_module(mod_name), owner)
        assert callable(getattr(cls, name))
        if mod_name == "TopoDS":  # the one OCP 8 binds without _s
            assert getattr(cls, name) is getattr(cls, name[:-2])
    import OCP.collections

    for mod_name, old, new in PRODUCTION_TYPEDEFS:
        module = __import__("OCP." + mod_name, fromlist=[old])
        assert getattr(module, old) is getattr(OCP.collections, new)
    for mod_name in PRODUCTION_MODULES:
        __import__("OCP." + mod_name)

    # The names in use, the way a design written for OCP 7 uses them.
    namespace = {}
    exec(
        """
import cadquery as cq
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.ShapeCustom import ShapeCustom
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal, TColStd_Array2OfReal
from OCP.TColgp import TColgp_Array1OfPnt, TColgp_Array2OfPnt
from OCP.Geom import Geom_BSplineCurve, Geom_BSplineSurface
from OCP.gp import gp_Pnt

box = cq.Workplane().box(10, 20, 30).val()
props = GProp_GProps()
BRepGProp.VolumeProperties_s(box.wrapped, props)
volume = props.Mass()
shell = TopoDS.Shell_s(box.Shells()[0].wrapped)
edge = TopoDS.Edge_s(box.Edges()[0].wrapped)
surface = BRep_Tool.Surface_s(box.Faces()[0].wrapped)
bspline = ShapeCustom.ConvertToBSpline_s(box.wrapped, True, True, True)

poles = TColgp_Array1OfPnt(1, 4)
for i in range(1, 5):
    poles.SetValue(i, gp_Pnt(i, i * i, 0))
knots = TColStd_Array1OfReal(1, 2)
knots.SetValue(1, 0.0)
knots.SetValue(2, 1.0)
mults = TColStd_Array1OfInteger(1, 2)
mults.SetValue(1, 4)
mults.SetValue(2, 4)
curve = Geom_BSplineCurve(poles, knots, mults, 3)

grid = TColgp_Array2OfPnt(1, 2, 1, 2)
weights = TColStd_Array2OfReal(1, 2, 1, 2)
for i in (1, 2):
    for j in (1, 2):
        grid.SetValue(i, j, gp_Pnt(i, j, i * j))
        weights.SetValue(i, j, 1.0)
uknots, umults = TColStd_Array1OfReal(1, 2), TColStd_Array1OfInteger(1, 2)
for k, (value, mult) in enumerate(((0.0, 2), (1.0, 2)), 1):
    uknots.SetValue(k, value)
    umults.SetValue(k, mult)
patch = Geom_BSplineSurface(grid, weights, uknots, uknots, umults, umults, 1, 1)
""",
        namespace,
    )
    assert namespace["volume"] == pytest.approx(6000)
    assert namespace["shell"].ShapeType().name == "TopAbs_SHELL"
    assert namespace["edge"].ShapeType().name == "TopAbs_EDGE"
    assert namespace["surface"] is not None
    assert cq.Shape.cast(namespace["bspline"]).Volume() == pytest.approx(6000)
    assert namespace["curve"].EndPoint().Y() == pytest.approx(16)
    assert namespace["patch"].NbUPoles() == 2


@isolated
def test_static_sweep():
    """Every static method and namespace function Foo has Foo_s, the very same callable."""

    restored = occ_compat.enable()
    statics = [key for key, kind in restored.items() if kind == "static"]
    assert {f"TopoDS.{kind}_s" for kind in ("Vertex", "Edge", "Wire", "Face")} <= set(
        statics
    )

    import OCP.OCP as ocp

    checked = 0
    for mod_name, mod in vars(ocp).items():
        if type(mod).__name__ != "module" or mod.__name__ != "OCP.OCP." + mod_name:
            continue
        for owner in vars(mod).values():
            if isinstance(owner, type):
                for name, raw in list(vars(owner).items()):
                    if isinstance(raw, staticmethod) and not name.startswith("_"):
                        checked += 1
                        if not name.endswith("_s"):
                            assert getattr(owner, name + "_s") is getattr(owner, name)
            elif type(owner).__name__ == "module" and owner.__name__.startswith("OCP."):
                for name, func in list(vars(owner).items()):
                    if (
                        callable(func)
                        and not isinstance(func, type)
                        and not name.startswith("_")
                    ):
                        checked += 1
                        if not name.endswith("_s"):
                            assert getattr(owner, name + "_s") is getattr(owner, name)
    assert checked > 8000
    from OCP.TopoDS import TopoDS

    shape = cq.Workplane().box(1, 1, 1).val()
    assert TopoDS.Face_s(shape.Faces()[0].wrapped).IsSame(shape.Faces()[0].wrapped)


@isolated
def test_renamed_and_enum_values():
    occ_compat.enable()
    from OCP.TopTools import (
        TopTools_ListOfShape,
        TopTools_IndexedMapOfShape,
        TopTools_IndexedDataMapOfShapeListOfShape,
    )
    from OCP.TDF import TDF_LabelSequence
    from OCP.GCE2d import GCE2d_MakeSegment
    from OCP.TopExp import TopExp
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.gp import gp_Pnt2d
    import OCP.collections as c
    import OCP.AIS

    assert TopTools_ListOfShape is c.List_TopoDS_Shape
    assert TDF_LabelSequence is c.Sequence_TDF_Label
    box = cq.Workplane().box(1, 2, 3).val()
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(box.wrapped, TopAbs_FACE, faces)
    assert faces.Extent() == 6
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(box.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
    assert ancestors.Extent() == 12
    assert ancestors.FindFromIndex(1).Size() == 2
    segment = GCE2d_MakeSegment(gp_Pnt2d(0, 0), gp_Pnt2d(3, 4)).Value()
    assert segment.LastParameter() - segment.FirstParameter() == pytest.approx(5)
    # OCP 7 exported nested enum values into the class.
    assert (
        OCP.AIS.AIS_PointCloud.DM_Points
        is OCP.AIS.AIS_PointCloud.DisplayMode_e.DM_Points
    )


@isolated
def test_star_import_and_late_import():
    """Old names reach `from OCP.X import *` and packages imported after enable()."""

    late = [m for m in occ_compat._RENAMED if "OCP." + m not in sys.modules]
    assert late, "every module is already imported"
    occ_compat.enable()
    module, (old, new) = late[0], next(iter(occ_compat._RENAMED[late[0]].items()))
    namespace = {}
    exec(f"from OCP.{module} import *", namespace)
    assert old in namespace
    exec("from OCP.TColgp import *", namespace)
    assert (
        namespace["TColgp_Array1OfPnt"]
        is __import__("OCP.collections").collections.Array1_gp_Pnt
    )


@isolated
def test_bnd_box_get():
    from OCP.Bnd import Bnd_Box, Bnd_Box2d
    from OCP.gp import gp_Pnt
    from OCP.Standard import Standard_ConstructionError

    box = Bnd_Box(gp_Pnt(1, 2, 3), gp_Pnt(4, 5, 6))
    with pytest.raises(
        TypeError
    ):  # OCP 8.0.1's own binding cannot return Bnd_Box::Limits
        box.Get()

    assert occ_compat.enable()["Bnd_Box.Get"] == "patched"
    limits = box.Get()
    xmin, ymin, zmin, xmax, ymax, zmax = limits  # OCP 7's order
    assert (xmin, ymin, zmin, xmax, ymax, zmax) == (1, 2, 3, 4, 5, 6)
    assert (
        limits.Xmin,
        limits.Xmax,
        limits.Ymin,
        limits.Ymax,
        limits.Zmin,
        limits.Zmax,
    ) == (
        1,
        4,
        2,
        5,
        3,
        6,
    )  # OCCT 8's Limits fields
    assert len(limits) == 6 and isinstance(limits, tuple)

    box.SetGap(0.5)
    assert box.Get() == (0.5, 1.5, 2.5, 4.5, 5.5, 6.5)
    box.OpenXmin()
    box.OpenZmax()
    assert box.Get()[0] == -1e100 and box.Get()[5] == 1e100
    with pytest.raises(Standard_ConstructionError):
        Bnd_Box().Get()

    shape = cq.Workplane().box(2, 4, 6).val()
    from OCP.BRepBndLib import BRepBndLib

    tight = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, tight, False, False)
    assert tight.Get() == pytest.approx((-1, -2, -3, 1, 2, 3))

    flat = Bnd_Box2d()
    flat.Update(1.0, 2.0, 3.0, 4.0)
    xmin, ymin, xmax, ymax = flat.Get()
    assert (xmin, ymin, xmax, ymax) == (1, 2, 3, 4)
    assert (flat.Get().Xmax, flat.Get().Ymin) == (3, 2)
    with pytest.raises(Standard_ConstructionError):
        Bnd_Box2d().Get()
    assert occ_compat.calls()["Bnd_Box.Get"] >= 6


def _fclass2d_reference():
    with gzip.open(TESTDATA / "occ_compat_fclass2d.json.gz", "rt") as f:
        return json.load(f)["faces"]


@isolated
def test_fclass2d_matches_ocp79():
    occ_compat.enable()
    from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
    from OCP.gp import gp_Pnt2d

    faces = _fclass2d_reference()
    assert len(faces) == 46
    compared = 0
    mismatches = []
    for record in faces:
        face = cq.Shape.importBrep(io.BytesIO(record["brep"].encode())).wrapped
        for tol, expected in zip((1e-7, 1e-4), record["states"]):
            k = BRepTopAdaptor_FClass2d(face, tol)
            got = [str(int(k.PerformInfinitePoint()))]
            for u, v in record["points"]:
                p = gp_Pnt2d(u, v)
                got.append(
                    "%d%d%d%d%d"
                    % (
                        int(k.Perform(p)),
                        int(k.Perform(p, False)),
                        int(k.TestOnRestriction(p, 1e-7)),
                        int(k.TestOnRestriction(p, 1e-4)),
                        int(k.TestOnRestriction(p, 1e-2, False)),
                    )
                )
            got = "".join(got)
            compared += len(expected)
            if got != expected:
                mismatches.append((record["name"], tol))
    assert compared > 90000
    assert mismatches == []


@isolated
def test_fclass2d_surface():
    occ_compat.enable()
    from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
    from OCP.TopAbs import TopAbs_IN, TopAbs_OUT, TopAbs_ON
    from OCP.gp import gp_Pnt2d

    plate = cq.Workplane().rect(10, 10).extrude(1).faces(">Z").workplane().hole(4)
    face = plate.faces(">Z").val()
    umin, umax, vmin, vmax = face._uvBounds()
    u, v = (umin + umax) / 2, (vmin + vmax) / 2  # the hole's centre
    k = BRepTopAdaptor_FClass2d(face.wrapped, 1e-7)
    assert k.Perform(gp_Pnt2d(u + 4, v + 4)) == TopAbs_IN
    assert k.Perform(gp_Pnt2d(u, v)) == TopAbs_OUT  # in the hole
    assert k.Perform(Puv=gp_Pnt2d(u + 20, v), RecadreOnPeriodic=False) == TopAbs_OUT
    assert k.TestOnRestriction(gp_Pnt2d(u + 2, v), 1e-3) == TopAbs_ON
    assert k.PerformInfinitePoint() == TopAbs_OUT
    k.Destroy()


@isolated
def test_idempotent_and_thread_safe():
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(occ_compat.enable()))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 8 and all(r == results[0] for r in results)
    assert len(results[0]) > 800
    from OCP.TopoDS import TopoDS
    from OCP.Bnd import Bnd_Box

    face_s, get = TopoDS.Face_s, Bnd_Box.Get
    assert occ_compat.enable() == results[0]
    assert TopoDS.Face_s is face_s and Bnd_Box.Get is get
    assert occ_compat.enabled()


@isolated
def test_new_names_unaffected():
    """enable() only adds names: everything OCP 8 binds keeps its object, except the
    Get() methods whose OCP 8 binding cannot return."""

    before = snapshot()
    restored = occ_compat.enable()
    after = snapshot()
    changed = sorted(k for k, v in before.items() if after.get(k) is not v)
    assert changed == ["Bnd.Bnd_Box.Get", "Bnd.Bnd_Box2d.Get"]
    patched = sorted(k for k, kind in restored.items() if kind == "patched")
    assert patched == ["Bnd_Box.Get", "Bnd_Box2d.Get"]
    # An alias of a class lists that class's own attributes too; those are not names enable() set.
    added = {
        k
        for k in set(after) - set(before)
        if k.count(".") == 1 or k.rsplit(".", 1)[0] in before
    }
    assert added and all(k in restored or k.split(".", 1)[1] in restored for k in added)
    from OCP.TopoDS import TopoDS

    shape = cq.Workplane().box(1, 1, 1).val()
    assert TopoDS.Face(shape.Faces()[0].wrapped).IsSame(shape.Faces()[0].wrapped)
