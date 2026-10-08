"""Fast native-list traversal must preserve headers, order and ownership."""
import gc

import cadquery as cq
import pytest
from cadquery.occ_impl.shapes import (
    TopTools_ListOfShape, TopTools_IndexedDataMapOfShapeListOfShape,
    _shape_list_values,
)
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS_Shape


@pytest.mark.parametrize("count", [0, 1, 2, 3, 6, 31, 32, 33, 64])
def test_shape_list_preserves_duplicates_headers_and_lifetime(count):
    faces = cq.Workplane().box(2, 3, 4).faces().vals()
    shapes = [f.wrapped for f in faces]
    shapes += [faces[0].wrapped, faces[1].reverse().wrapped,
               faces[2].moved(cq.Location((5, -3, 2))).wrapped, TopoDS_Shape()]
    expected = [shapes[i % len(shapes)] for i in range(count)]
    values = TopTools_ListOfShape()
    for shape in expected:
        values.Append(shape)
    result = list(_shape_list_values(values))
    assert values.Size() == count
    assert len(result) == count
    assert all(a.IsEqual(b) for a, b in zip(expected, values))
    values.Clear()
    del values
    gc.collect()
    assert all(a.IsEqual(b) for a, b in zip(expected, result))
    assert all(a.IsNull() == b.IsNull() for a, b in zip(expected, result))
    # Changing a returned header must not change a surviving input header.
    if result:
        result[0].Reverse()
        assert result[0].Orientation() != expected[0].Orientation()


@pytest.mark.parametrize("child,kind", [("Edge", TopAbs_EDGE), ("Vertex", TopAbs_VERTEX)])
@pytest.mark.parametrize("geometry", ["box", "sphere", "mixed", "empty"])
def test_entities_from_keeps_native_occurrence_order_and_duplicates(child, kind, geometry):
    if geometry == "box":
        shape = cq.Workplane().box(2, 3, 4).val()
    elif geometry == "sphere":
        shape = cq.Workplane().sphere(3).val()
    elif geometry == "empty":
        shape = cq.Compound.makeCompound([])
    else:
        face = cq.Workplane().box(2, 3, 4).faces().val()
        shape = cq.Compound.makeCompound([face, face.reverse(),
            face.moved(cq.Location((7, 5, -2))),
            cq.Edge.makeLine((10, 0, 0), (11, 0, 0)), cq.Vertex.makeVertex(12, 0, 0)])
    native = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape.wrapped, kind, TopAbs_FACE, native)
    actual = shape._entitiesFrom(child, "Face")
    assert len(actual) == native.Extent()
    for index, (key, parents) in enumerate(actual.items(), 1):
        expected = list(native.FindFromIndex(index))
        assert key.wrapped.IsEqual(native.FindKey(index))
        assert len(parents) == len(expected)
        assert all(a.wrapped.IsEqual(b) for a, b in zip(parents, expected))
