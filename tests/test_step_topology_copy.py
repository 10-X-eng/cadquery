"""STEP geometry sharing must preserve styles, placement, and input geometry."""
from io import BytesIO
import re

import cadquery as cq
import pytest


def serialized(shape):
    stream = BytesIO()
    # Adding the source to an export compound clears its native ownership
    # (Free) flag. Compare the complete geometry/topology with that flag
    # normalized; do not discard tolerances, locations, curves or surfaces.
    free = shape.wrapped.Free()
    try:
        shape.wrapped.Free(False)
        shape.exportBrep(stream)
    finally:
        shape.wrapped.Free(free)
    return stream.getvalue()


@pytest.mark.parametrize("spline", [False, True])
def test_step_colored_copies_preserve_source_and_roundtrip(tmp_path, spline):
    if spline:
        shape = cq.Workplane().rect(12, 2).twistExtrude(30, 90).val()
    else:
        shape = cq.Workplane().box(12, 8, 4).edges('|Z').fillet(2).val()
    shape = shape.moved(cq.Location((7, -3, 2), (1, 2, 3), 23))
    before = serialized(shape)
    assembly = cq.Assembly(name="root")
    colors = ["red", "blue", "green"]
    for i, color in enumerate(colors):
        assembly.add(shape, name=color, color=cq.Color(color), loc=cq.Location(50*i, 0, 0))
    path = tmp_path / 'colored.step'
    assembly.export(str(path))
    assert serialized(shape) == before
    loaded = cq.Assembly.load(str(path))
    assert len(loaded.children) == 3
    for i, color in enumerate(colors):
        part = loaded.objects[color]
        assert part.color.toTuple() == pytest.approx(cq.Color(color).toTuple())
        assert part.loc.toTuple()[0] == pytest.approx((50*i, 0, 0))
        assert part.obj.isValid()
        assert part.obj.Volume() == pytest.approx(shape.Volume(), rel=1e-6)
        assert part.obj.Center().toTuple() == pytest.approx(shape.Center().toTuple(), abs=1e-6)


def test_geometric_face_name_does_not_spread_to_unannotated_copy(tmp_path):
    shape = cq.Workplane().box(2, 3, 4)
    assembly = cq.Assembly(name="root")
    assembly.add(shape, name="named", color=cq.Color("red"))
    assembly.objects['named'].addSubshape(shape.faces('>Z').val(), name="named_top")
    assembly.add(shape, name="plain", color=cq.Color("blue"), loc=cq.Location(10, 0, 0))
    path = tmp_path / 'names.step'
    assembly.export(str(path), name_geometries=True)
    source = path.read_text()
    assert len(re.findall(r"PLANE\('named_top'", source)) == 1
    assert len(re.findall(r"PLANE\(", source)) == 12
