"""Foreign XCAF/STEP documents may legally reuse component display names."""
import pytest

import cadquery as cq
from cadquery.occ_impl.importers.assembly import _importDoc, _get_name, TDF_LabelSequence
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorSurf


def document(names, nested):
    doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    shapes.SetAutoNaming_s(False)
    root = shapes.NewShape()
    TDataStd_Name.Set_s(root, TCollection_ExtendedString("vehicle"))
    box = cq.Solid.makeBox(1, 2, 3)
    part = shapes.AddShape(box.wrapped, False)
    TDataStd_Name.Set_s(part, TCollection_ExtendedString("part_definition"))
    top = shapes.AddSubShape(part, box.faces(">Z").wrapped)
    TDataStd_Name.Set_s(top, TCollection_ExtendedString("top_face"))
    definitions = {}
    for index, name in enumerate(names):
        definition = part
        if nested:
            if name not in definitions:
                definition = shapes.NewShape()
                TDataStd_Name.Set_s(definition, TCollection_ExtendedString(name))
                child = shapes.AddComponent(definition, part, cq.Location(0, 0, 3).wrapped)
                TDataStd_Name.Set_s(child, TCollection_ExtendedString("tire"))
                definitions[name] = definition
            definition = definitions[name]
        component = shapes.AddComponent(root, definition, cq.Location(5 * index, 0, 0).wrapped)
        TDataStd_Name.Set_s(component, TCollection_ExtendedString(name))
        colors.SetColor(component, cq.Color(index / len(names), .3, .7).wrapped, XCAFDoc_ColorSurf)
    shapes.UpdateAssemblies()
    return doc


def load(doc, kind, path):
    if kind == "document":
        result = cq.Assembly()
        _importDoc(doc, result)
        return result
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetColorMode(True)
    Interface_Static.SetIVal_s("write.stepcaf.subshapes.name", 1)
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    assert writer.Transfer(doc, STEPControl_AsIs)
    assert writer.Write(str(path)) == IFSelect_RetDone
    return cq.Assembly.load(str(path))


def source_names(doc):
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots, components = TDF_LabelSequence(), TDF_LabelSequence()
    shapes.GetFreeShapes(roots)
    shapes.GetComponents_s(roots.Value(1), components)
    return [_get_name(components.Value(i)) for i in range(1, components.Length() + 1)]


@pytest.mark.parametrize("kind", ["document", "step"])
@pytest.mark.parametrize("nested", [False, True])
def test_repeated_names_preserve_all_instances_and_explicit_suffixes(tmp_path, kind, nested):
    # Repeated subassemblies reference the SAME native definition, as in #1962.
    names = ["wheel", "wheel", "wheel_1", "wheel", "wheel_2"]
    expected = ["wheel", "wheel_3", "wheel_1", "wheel_4", "wheel_2"]
    doc = document(names, nested)
    assembly = load(doc, kind, tmp_path / "repeated.step")
    assert [child.name for child in assembly.children] == expected
    assert assembly.name == "vehicle"
    assert len(assembly.toCompound().Solids()) == len(names)
    assert assembly.toCompound().Volume() == pytest.approx(6 * len(names))
    for i, child in enumerate(assembly.children):
        assert child.loc.toTuple()[0] == pytest.approx((5 * i, 0, 0))
        assert child.color.toTuple() == pytest.approx((i / len(names), .3, .7, 1))
        assert assembly[child.name] is child
        leaf = child["tire"] if nested else child
        assert list(leaf._subshape_names.values()) == ["top_face"]
        assert leaf.obj.isValid()
        if child.name != names[i]:
            assert child.metadata["original_name"] == names[i]
    centers = sorted(solid.Center().toTuple() for solid in assembly.toCompound().Solids())
    expected_z = 4.5 if nested else 1.5
    for i, center in enumerate(centers):
        assert center == pytest.approx((5 * i + .5, 1, expected_z))
    # A repeated load must assign the same names, independently of prior calls.
    again = load(doc, kind, tmp_path / "repeated-again.step")
    assert list(again.objects) == list(assembly.objects)
    assert source_names(doc) == names


@pytest.mark.parametrize("nested", [False, True])
def test_missing_names_are_deterministic_and_do_not_steal_explicit_names(nested):
    assembly = cq.Assembly()
    _importDoc(document(["", "", "unnamed"], nested), assembly)
    assert [child.name for child in assembly.children] == ["unnamed_1", "unnamed_2", "unnamed"]
    assert len(assembly.toCompound().Solids()) == 3


def test_programmatic_duplicate_names_still_raise():
    assembly = cq.Assembly(name="root")
    assembly.add(cq.Solid.makeBox(1, 2, 3), name="part")
    with pytest.raises(ValueError, match="Unique name"):
        assembly.add(cq.Solid.makeBox(2, 3, 4), name="part")
