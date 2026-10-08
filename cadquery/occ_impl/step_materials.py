"""Keep physical material identity and density units intact across STEP I/O.

OCCT's material writer keys materials only by name and emits incorrect density
dimensions in 7.9/8.0. Its reader also misses SI mass prefixes. Adapt the private
transfer documents/models; never modify the user's Material or geometry.
"""
from math import isclose, isfinite
import re
from uuid import uuid4

from OCP.collections import (
    Sequence_TDF_Label as TDF_LabelSequence,
    HArray1_StepBasic_DerivedUnitElement,
)
from OCP.TCollection import TCollection_HAsciiString
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_Material
from OCP.StepBasic import (
    StepBasic_ConversionBasedUnit,
    StepBasic_DerivedUnit,
    StepBasic_DerivedUnitElement,
    StepBasic_SiUnit,
    StepBasic_SiUnitAndMassUnit,
    StepBasic_SiUnitAndLengthUnit,
    StepBasic_Unit,
    StepBasic_spCenti,
    StepBasic_sunGram,
    StepBasic_sunMetre,
)
from OCP.StepRepr import (
    StepRepr_DescriptiveRepresentationItem,
    StepRepr_MeasureRepresentationItem,
)


_MASS_G = {"mg": .001, "g": 1., "kg": 1000., "lb": 453.59237, "oz": 28.349523125}
_LENGTH_CM = {"mm": .1, "cm": 1., "m": 100., "in": 2.54, "ft": 30.48}
_SI_PREFIXES = dict(zip(
    ("Exa", "Peta", "Tera", "Giga", "Mega", "Kilo", "Hecto", "Deca",
     "Deci", "Centi", "Milli", "Micro", "Nano", "Pico", "Femto", "Atto"),
    (18, 15, 12, 9, 6, 3, 2, 1, -1, -2, -3, -6, -9, -12, -15, -18),
))


def _density(value, unit):
    match = re.fullmatch(r"(mg|g|kg|lb|oz)/(mm|cm|m|in|ft)(?:\^?3|³)",
                         "".join(unit.split()))
    if not match:
        raise ValueError(f"Unsupported STEP material density unit: {unit!r}")
    result = value * _MASS_G[match[1]] / _LENGTH_CM[match[2]] ** 3
    if not isfinite(result) or result < 0:
        raise ValueError("STEP material density must be finite and nonnegative")
    return result


def prepare_materials(doc):
    """Normalize densities and give distinct native material records unique keys."""
    labels = TDF_LabelSequence()
    XCAFDoc_DocumentTool.MaterialTool_s(doc.Main()).GetMaterialLabels(labels)
    names, keys = {}, {}
    prefix = f"cadquery-material-{uuid4().hex}-" if labels.Length() else ""
    for i in range(1, labels.Length() + 1):
        material = XCAFDoc_Material()
        if not labels.Value(i).FindAttribute(XCAFDoc_Material.GetID_s(), material):
            continue
        density = _density(material.GetDensity(), material.GetDensValType().ToCString())
        key = (material.GetName().ToCString(), material.GetDescription().ToCString(), density)
        token = keys.setdefault(key, prefix + str(len(keys)))
        names[token] = key[0]
        # FindAttribute fills a detached Python attribute object. Set_s updates
        # the actual document record used by the native transfer writer.
        XCAFDoc_Material.Set_s(
            labels.Value(i), TCollection_HAsciiString(token), material.GetDescription(), density,
            TCollection_HAsciiString(token), TCollection_HAsciiString("NUMERIC_MEASURE"))
    return names


def _entities(model, kind):
    # Select in native code instead of wrapping every edge/vertex STEP entity
    # in Python. Most imported assemblies contain no material density at all.
    iterator = model.Entities()
    iterator.SelectType(kind.get_type_descriptor_s(), True)
    iterator.Start()
    while iterator.More():
        yield iterator.Value()
        iterator.Next()


def finish_materials(model, names):
    """Restore display names and correct the writer's mass/length exponents."""
    if not names:
        return
    for entity in _entities(model, StepRepr_DescriptiveRepresentationItem):
        name = entity.Name().ToCString()
        if name in names:
            entity.SetName(TCollection_HAsciiString(names[name]))
    for entity in _entities(model, StepRepr_MeasureRepresentationItem):
        if entity.Name().ToCString() not in names:
            continue
        measure = entity.Measure()
        unit = measure.UnitComponent().DerivedUnit()
        if unit is None:
            raise ValueError("STEP writer omitted material density units")
        for j in range(1, unit.NbElements() + 1):
            element = unit.ElementsValue(j)
            base = element.Unit()
            if isinstance(base, StepBasic_SiUnitAndMassUnit) and base.Name() == StepBasic_sunGram:
                element.SetExponent(1.)
            elif isinstance(base, StepBasic_SiUnitAndLengthUnit) and base.Name() == StepBasic_sunMetre:
                element.SetExponent(-3.)
            else:
                raise ValueError("Unsupported native STEP material density unit")
        factor, mass, length = _unit_terms(measure.UnitComponent())
        if not (isclose(factor, 1.) and mass == 1. and length == -3.):
            raise ValueError("STEP writer changed canonical material density units")
        entity.SetName(TCollection_HAsciiString("MassDensity"))


def _unit_terms(unit, depth=0):
    """Return the scale to grams/centimeters and dimensional exponents."""
    if depth > 16 or unit is None:
        raise ValueError("Invalid or cyclic STEP material density units")
    if isinstance(unit, StepBasic_Unit):
        derived = unit.DerivedUnit()
        return _unit_terms(derived if derived is not None else unit.NamedUnit(), depth + 1)
    if isinstance(unit, StepBasic_DerivedUnit):
        factor, mass, length = 1., 0., 0.
        for i in range(1, unit.NbElements() + 1):
            element = unit.ElementsValue(i)
            scale, m, l = _unit_terms(element.Unit(), depth + 1)
            exponent = element.Exponent()
            if not isfinite(exponent) or not isfinite(scale) or scale <= 0:
                raise ValueError("Invalid STEP density unit scale or exponent")
            try:
                factor *= scale ** exponent
            except (OverflowError, ZeroDivisionError) as error:
                raise ValueError("Invalid STEP density unit scale") from error
            if not isfinite(factor) or factor <= 0:
                raise ValueError("Invalid STEP density unit scale")
            mass += m * exponent
            length += l * exponent
        return factor, mass, length
    if isinstance(unit, StepBasic_ConversionBasedUnit):
        conversion = unit.ConversionFactor()
        if conversion is None:
            raise ValueError("Missing STEP density unit conversion")
        factor, mass, length = _unit_terms(conversion.UnitComponent(), depth + 1)
        factor *= conversion.ValueComponent()
        if not isfinite(factor) or factor <= 0:
            raise ValueError("Invalid STEP density unit conversion")
        return factor, mass, length
    if isinstance(unit, StepBasic_SiUnit):
        prefix = 10. ** _SI_PREFIXES[unit.Prefix().name.removeprefix("StepBasic_sp")] if unit.HasPrefix() else 1.
        if unit.Name() == StepBasic_sunGram:
            return prefix, 1., 0.
        if unit.Name() == StepBasic_sunMetre:
            return 100. * prefix, 0., 1.
    raise ValueError("Unsupported STEP material density unit")


def _canonical_unit():
    gram = StepBasic_SiUnitAndMassUnit()
    gram.Init(False, StepBasic_spCenti, StepBasic_sunGram)
    centimeter = StepBasic_SiUnitAndLengthUnit()
    centimeter.Init(True, StepBasic_spCenti, StepBasic_sunMetre)
    elements = HArray1_StepBasic_DerivedUnitElement(1, 2)
    for i, (unit, exponent) in enumerate(((gram, 1.), (centimeter, -3.)), 1):
        element = StepBasic_DerivedUnitElement()
        element.Init(unit, exponent)
        elements.SetValue(i, element)
    derived = StepBasic_DerivedUnit()
    derived.Init(elements)
    result = StepBasic_Unit()
    result.SetValue(derived)
    return result


def normalize_imported_densities(model):
    """Convert valid density measures before OCCT can discard SI mass prefixes."""
    canonical = None
    for item in _entities(model, StepRepr_MeasureRepresentationItem):
        named_density = re.sub(r"[ _-]", "", item.Name().ToCString()).casefold() in ("density", "massdensity")
        measure = item.Measure()
        try:
            factor, mass, length = _unit_terms(measure.UnitComponent())
        except ValueError:
            if named_density:
                raise
            continue
        if not (isclose(mass, 1., rel_tol=0., abs_tol=1e-12) and
                isclose(length, -3., rel_tol=0., abs_tol=1e-12)):
            if named_density:
                raise ValueError("STEP material density must have dimensions mass / length^3")
            continue
        value = measure.ValueComponent() * factor
        if not isfinite(value) or value < 0 or factor <= 0:
            raise ValueError("Invalid STEP material density")
        if canonical is None:
            canonical = _canonical_unit()
        measure.SetValueComponent(value)
        measure.SetUnitComponent(canonical)
