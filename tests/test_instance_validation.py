"""Instance validation must retain native geometry and topology checks."""
import cadquery as cq
import pytest
from OCP.BRep import BRep_Builder
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopoDS import TopoDS_CompSolid
from OCP.gp import gp_Pnt


def native(shape):
    return BRepCheck_Analyzer(shape.wrapped).IsValid()


def grid(shape, shift=0):
    return cq.Compound.makeCompound([
        shape.moved(cq.Location((shift + i * 12, 7 * i, -3 * i), (1, 2, 3), 17 * i))
        for i in range(8)
    ])


@pytest.mark.parametrize("kind", ["box", "sphere", "torus", "loft", "shell"])
@pytest.mark.parametrize("shift", [0, 1e9])
@pytest.mark.parametrize("reverse", [False, True])
def test_repeated_solid_geometry_matches_native(kind, shift, reverse):
    if kind == "box":
        shape = cq.Workplane().box(4, 6, 8).val()
    elif kind == "sphere":
        shape = cq.Workplane().sphere(5).val()
    elif kind == "torus":
        shape = cq.Solid.makeTorus(8, 2)
    elif kind == "loft":
        shape = cq.Workplane().circle(4).workplane(offset=7).ellipse(5, 3).loft().val()
    else:
        shape = cq.Workplane().box(12, 10, 8).faces(">Z").shell(-1).val()
    if reverse:
        shape = shape.reverse()
    compound = grid(shape, shift)
    assert compound.isValid() == native(compound)


def test_nested_locations_and_orientations():
    part = cq.Workplane().box(2, 3, 4).val()
    nested = cq.Compound.makeCompound([grid(part), grid(part.reverse(), 20)])
    result = cq.Compound.makeCompound([nested,
        nested.moved(cq.Location((5, 3, -8), (1, 0, 0), 73)),
        cq.Compound.makeCompound([])])
    location, orientation = result.wrapped.Location(), result.wrapped.Orientation()
    assert result.isValid() == native(result)
    assert result.wrapped.Location().IsEqual(location)
    assert result.wrapped.Orientation() == orientation


def test_native_mutations_are_rechecked_for_every_call():
    part = cq.Workplane().box(2, 3, 4).val()
    compound = grid(part)
    assert compound.isValid() and native(compound)
    vertex = part.Vertices()[0]
    original = vertex.toTuple()
    builder = BRep_Builder()
    builder.UpdateVertex(vertex.wrapped, gp_Pnt(100, 100, 100), 1e-7)
    assert not native(compound)
    assert not compound.isValid()
    builder.UpdateVertex(vertex.wrapped, gp_Pnt(*original), 1e-7)
    assert native(compound) and compound.isValid()


def test_unique_invalid_body_is_not_hidden_by_repeated_valid_ones():
    part = cq.Workplane().sphere(3).val()
    broken = cq.Workplane().box(2, 3, 4).val()
    BRep_Builder().UpdateVertex(broken.Vertices()[0].wrapped, gp_Pnt(100, 100, 100), 1e-7)
    compound = cq.Compound.makeCompound([grid(part), broken])
    assert not native(compound)
    assert not compound.isValid()


def test_mesh_consistency_is_still_checked():
    part = cq.Workplane().box(2, 3, 4).val()
    part.mesh(0.1)
    compound = grid(part)
    assert compound.isValid() == native(compound)
    # Moving a BRep vertex breaks its relation to the edge and its mesh.
    BRep_Builder().UpdateVertex(part.Vertices()[0].wrapped, gp_Pnt(20, 20, 20), 1e-7)
    assert not native(compound)
    assert not compound.isValid()


@pytest.mark.parametrize("extra", ["edge", "face", "compsolid", "unique", "empty"])
def test_other_compounds_retain_native_analysis(extra):
    part = cq.Workplane().box(2, 3, 4).val()
    if extra == "edge":
        item = cq.Edge.makeLine((0, 0, 0), (2, 1, 0))
    elif extra == "face":
        item = cq.Face.makePlane(2, 3)
    elif extra == "compsolid":
        builder, raw = BRep_Builder(), TopoDS_CompSolid()
        builder.MakeCompSolid(raw)
        builder.Add(raw, part.wrapped)
        item = cq.Shape(raw)
    elif extra == "unique":
        item = cq.Workplane().sphere(5).val()
    else:
        item = cq.Compound.makeCompound([])
    result = cq.Compound.makeCompound([part, item])
    assert result.isValid() == native(result)
