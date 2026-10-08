"""Classification and mass properties for all three-dimensional shape types."""
import pytest
import cadquery as cq
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from cadquery.occ_impl.shapes import CompSolid
from OCP.TopoDS import TopoDS_Shape


def adjacent_prisms():
    face = cq.Face.makePlane(1, 2)
    shell = cq.Shell.makeShell([face, face.translate((1, 0, 0))])
    return cq.Shape.cast(BRepPrimAPI_MakePrism(shell.wrapped, cq.Vector(0, 0, 3).wrapped).Shape())


def test_solid_is_not_classified_as_compsolid():
    solid = cq.Solid.makeBox(1, 2, 3)
    assert solid.geomType() == 'Solid'
    assert solid.outerShell().geomType() == 'Shell'
    assert cq.Compound.makeCompound([solid]).geomType() == 'Compound'


def test_compsolid_classification():
    part = adjacent_prisms()
    assert isinstance(part, CompSolid)
    assert part.isValid()
    assert len(part.Solids()) == 2
    assert part.geomType() == 'CompSolid'


def test_compsolid_volume_and_center():
    part = adjacent_prisms()
    assert part.Volume() == pytest.approx(12)
    center = cq.Shape.centerOfMass(part)
    expected = cq.Shape.CombinedCenter(part.Solids())
    assert center.toTuple() == pytest.approx(expected.toTuple())
    # Mass dispatch must also work through nested compound wrappers.
    nested = cq.Compound.makeCompound([cq.Compound.makeCompound([part])])
    assert nested.Volume() == pytest.approx(12)
    assert nested.Center().toTuple() == pytest.approx(center.toTuple())
    moved = part.translate((5, -2, 7))
    assert cq.Shape.CombinedCenter([part, moved]).toTuple() == pytest.approx(
        (center + cq.Vector(2.5, -1, 3.5)).toTuple())


def test_cast_preserves_wrappers_location_orientation_and_construction_flag():
    solid = cq.Solid.makeBox(1, 2, 3)
    shapes = [solid.Vertices()[0], solid.Edges()[0], solid.Wires()[0],
              solid.Faces()[0], solid.outerShell(), solid, adjacent_prisms(),
              cq.Compound.makeCompound([solid])]
    loc = cq.Location((4, -7, 2), (1, 2, 3), 37)
    for shape in shapes:
        placed = shape.moved(loc).reverse()
        # Oriented returns the general TopoDS_Shape used by native algorithms.
        raw = placed.wrapped.Oriented(placed.wrapped.Orientation())
        assert type(raw) is TopoDS_Shape
        result = cq.Shape.cast(raw, forConstruction=True)
        assert type(result) is type(shape)
        assert result.wrapped.IsEqual(raw)
        assert result.forConstruction is True
        if isinstance(result, cq.Vertex):
            assert (result.X, result.Y, result.Z) == pytest.approx(placed.toTuple())
    with pytest.raises(ValueError, match='Null TopoDS_Shape'):
        cq.Shape.cast(TopoDS_Shape())
