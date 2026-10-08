"""Check STEP density entities independently of CadQuery's roundtrip reader."""
import re

import cadquery as cq
import pytest
from OCP.STEPControl import STEPControl_Reader
from OCP.StepRepr import StepRepr_MeasureRepresentationItem
from OCP.StepBasic import StepBasic_sunGram, StepBasic_sunMetre, StepBasic_spCenti


def assembly(density=8.9, unit="g/cm^3"):
    return cq.Assembly(name="root").add(
        cq.Solid.makeBox(1, 2, 3), name="part",
        material=cq.Material("copper", description="alloy", density=density, densityUnit=unit))


def density_entities(path):
    reader = STEPControl_Reader()
    reader.ReadFile(str(path))
    model = reader.StepModel()
    return [e for i in range(1, model.NbEntities() + 1)
            if isinstance(e := model.Value(i), StepRepr_MeasureRepresentationItem)
            and e.Name().ToCString() == "MassDensity"]


def external_density(text, mass_prefix, length_prefix, density, length_exponent=-3.):
    """Build controlled input independently of whether the exporter is fixed."""
    text = text.replace("SI_UNIT($,.GRAM.)", f"SI_UNIT({mass_prefix},.GRAM.)")
    text = text.replace("SI_UNIT(.CENTI.,.METRE.)", f"SI_UNIT({length_prefix},.METRE.)")
    text, count = re.subn(
        r"(MEASURE_REPRESENTATION_ITEM\('MassDensity',)\s*(?:NUMERIC_MEASURE\(\s*[^)]*\)|[^,]+),",
        lambda m: m[1] + f"NUMERIC_MEASURE({density:.17E}),", text)
    assert count == 1
    exponents = iter((1., length_exponent))
    text, count = re.subn(r"(DERIVED_UNIT_ELEMENT\(#[0-9]+,)[^)]*\)",
                          lambda m: m[1] + f"{next(exponents)})", text)
    assert count == 2
    return text


@pytest.mark.parametrize("density,unit,expected", [
    (8.9, "g/cm^3", 8.9), (8900, "kg/m^3", 8.9),
    (.3215, "lb/in^3", .3215 * 453.59237 / 2.54**3),
    (1., "oz/ft3", 28.349523125 / 30.48**3), (8.9, "mg/mm³", 8.9),
])
@pytest.mark.parametrize("output_unit", ["MM", "M", "INCH"])
def test_density_dimensions_and_values_are_correct(tmp_path, density, unit, expected, output_unit):
    source = assembly(density, unit)
    original = source.objects['part'].material.toTuple()
    path = tmp_path / 'material.step'
    source.export(str(path), outputUnit=output_unit)
    assert source.objects['part'].material.toTuple() == original
    assert "cadquery-material-" not in path.read_text()
    entities = density_entities(path)
    assert len(entities) == 1
    measure = entities[0].Measure()
    assert measure.ValueComponent() == pytest.approx(expected)
    assert measure.ValueComponentMember().Name() == "NUMERIC_MEASURE"
    native = measure.UnitComponent().DerivedUnit()
    assert native.NbElements() == 2
    dimensions = {}
    for i in range(1, native.NbElements() + 1):
        element = native.ElementsValue(i)
        base = element.Unit()
        dimensions[base.Name()] = element.Exponent()
        if base.Name() == StepBasic_sunGram:
            assert not base.HasPrefix()
        else:
            assert base.HasPrefix() and base.Prefix() == StepBasic_spCenti
    assert dimensions == {StepBasic_sunGram: 1., StepBasic_sunMetre: -3.}
    loaded = cq.Assembly.load(str(path)).objects['part']
    assert loaded.material.name == "copper"
    assert loaded.material.description == "alloy"
    assert loaded.material.density == pytest.approx(expected)
    assert loaded.material.densityUnit == "g/cm^3"
    assert loaded.obj.Volume() == pytest.approx(6)


def test_same_name_materials_keep_independent_properties(tmp_path):
    source = assembly()
    shape = source.objects['part'].obj
    for i, density in enumerate((8.1, 8.9, 0.)):
        source.add(shape, name=f'variant_{i}', loc=cq.Location(5 * (i + 1), 0, 0),
                   material=cq.Material('copper', description=f'alloy {i}', density=density))
    path = tmp_path / 'same-name.step'
    source.export(str(path))
    loaded = cq.Assembly.load(str(path))
    for name, part in source.objects.items():
        if part.material:
            assert loaded.objects[name].material.toTuple() == part.material.toTuple()


@pytest.mark.parametrize("mass_prefix,length_prefix,density", [
    (".KILO.", "$", 8900.), (".MILLI.", ".MILLI.", 8.9),
    (".KILO.", ".MILLI.", .0000089), ("$", "$", 8900000.),
])
def test_import_honors_si_mass_and_length_prefixes(tmp_path, mass_prefix, length_prefix, density):
    path = tmp_path / 'external.step'
    assembly().export(str(path))
    path.write_text(external_density(path.read_text(), mass_prefix, length_prefix, density))
    material = cq.Assembly.load(str(path)).objects['part'].material
    assert material.density == pytest.approx(8.9)
    assert material.densityUnit == "g/cm^3"


@pytest.mark.parametrize("density,unit", [
    (-1., "g/cm^3"), (float('nan'), "g/cm^3"), (float('inf'), "g/cm^3"),
    (1., "unknown"), (1., "kg/m^2"),
])
def test_bad_density_does_not_overwrite_output_or_mutate_material(tmp_path, density, unit):
    path = tmp_path / 'existing.step'
    path.write_text('existing file')
    source = assembly(density, unit)
    material = source.objects['part'].material
    with pytest.raises(ValueError, match='density'):
        source.export(str(path))
    assert path.read_text() == 'existing file'
    assert material.name == 'copper' and material.densityUnit == unit


def test_incompatible_step_density_dimensions_are_rejected(tmp_path):
    path = tmp_path / 'bad.step'
    assembly().export(str(path))
    path.write_text(external_density(path.read_text(), "$", ".CENTI.", 8.9, length_exponent=2.))
    with pytest.raises(ValueError, match='dimensions mass'):
        cq.Assembly.load(str(path))


def test_import_handles_conversion_based_mass_and_length_units(tmp_path):
    path = tmp_path / 'pounds-inches.step'
    assembly().export(str(path))
    value = 8.9 * 2.54**3 / 453.59237
    text = external_density(path.read_text(), "$", ".CENTI.", value)
    references = re.findall(r"DERIVED_UNIT_ELEMENT\(#([0-9]+),", text)
    assert len(references) == 2
    next_id = max(map(int, re.findall(r"#([0-9]+) =", text))) + 1
    for offset, (base, name, factor, kind, dimensions) in enumerate([
        (references[0], 'pound', 453.59237, 'MASS', '0.,1.,0.,0.,0.,0.,0.'),
        (references[1], 'inch', 2.54, 'LENGTH', '1.,0.,0.,0.,0.,0.,0.'),
    ]):
        unit, dims, measure = (next_id + 3 * offset + i for i in range(3))
        text = text.replace(f'DERIVED_UNIT_ELEMENT(#{base},', f'DERIVED_UNIT_ELEMENT(#{unit},')
        added = (
            f"#{unit} = ( CONVERSION_BASED_UNIT('{name}',#{measure}) "
            f"{kind}_UNIT() NAMED_UNIT(#{dims}) );\n"
            f"#{dims} = DIMENSIONAL_EXPONENTS({dimensions});\n"
            f"#{measure} = MEASURE_WITH_UNIT({kind}_MEASURE({factor}),#{base});\n"
        )
        end = text.rfind('ENDSEC;')
        text = text[:end] + added + text[end:]
    path.write_text(text)
    loaded = cq.Assembly.load(str(path)).objects['part']
    assert loaded.material.density == pytest.approx(8.9)
    assert loaded.material.densityUnit == 'g/cm^3'
    assert loaded.obj.Volume() == pytest.approx(6)
    assert path.read_text() == text


def test_import_density_does_not_depend_on_display_names(tmp_path):
    path = tmp_path / 'rho.step'
    assembly().export(str(path))
    text = external_density(path.read_text(), '.KILO.', '$', 8900.)
    text = text.replace("'MassDensity'", "'bulk_rho'").replace("REPRESENTATION('density'", "REPRESENTATION('rho'")
    path.write_text(text)
    material = cq.Assembly.load(str(path)).objects['part'].material
    assert material.density == pytest.approx(8.9)
    assert material.densityUnit == 'g/cm^3'
