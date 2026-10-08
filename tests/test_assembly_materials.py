"""Shared geometry must retain each instance's physical material on export."""
import cadquery as cq
import pytest


@pytest.mark.parametrize("kind", ["step", "xml", "xbf"])
@pytest.mark.parametrize("reverse", [False, True])
def test_shared_geometry_keeps_distinct_and_missing_materials(tmp_path, kind, reverse):
    part = cq.Workplane().box(2, 3, 4)
    specifications = [
        ("bare", None),
        ("copper", cq.Material("copper", description="Copper alloy", density=8.9)),
        ("aluminum", cq.Material("aluminum", description="Aluminum alloy", density=2.7)),
        ("copper_again", cq.Material("copper", description="Copper alloy", density=8.9)),
    ]
    specifications.append(("copper_variant", cq.Material(
        "copper", description="Different copper alloy", density=8.1)))
    if reverse:
        specifications.reverse()
    assembly = cq.Assembly(name="root")
    for index, (name, material) in enumerate(specifications):
        assembly.add(part, name=name, material=material,
                     color=cq.Color("red"), loc=cq.Location(10 * index, 0, 0))
    path = tmp_path / f"materials.{kind}"
    assembly.export(str(path))
    loaded = cq.Assembly.load(str(path))
    for index, (name, expected) in enumerate(specifications):
        actual = loaded.objects[name]
        if expected is None:
            assert actual.material is None
        else:
            assert actual.material is not None
            assert actual.material.name == expected.name
            assert actual.material.description == expected.description
            assert actual.material.density == pytest.approx(expected.density)
            assert actual.material.densityUnit == expected.densityUnit
        assert actual.color.toTuple() == pytest.approx(cq.Color("red").toTuple())
        assert actual.loc.toTuple()[0] == pytest.approx((10 * index, 0, 0))
        assert actual.obj.Volume() == pytest.approx(24)
