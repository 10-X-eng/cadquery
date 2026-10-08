"""Reproductions from the upstream backlog relevant to geometry hosting.

Issue numbers refer to https://github.com/CadQuery/cadquery/issues.
"""
from math import cos, sin, pi

import pytest
import cadquery as cq
import OCP


def test_issue_2078_nested_empty_compound():
    empty = cq.Compound.makeCompound([])
    nested = cq.Compound.makeCompound([empty])
    assert nested.Volume() == 0
    solid = cq.Workplane().box(1, 2, 3).val()
    assert cq.Compound.makeCompound([nested, solid]).Volume() == pytest.approx(6)


def test_issue_981_invalid_vector_length():
    for coords in [(), (1,), (1, 2, 3, 4), [], [1], [1, 2, 3, 4]]:
        with pytest.raises(TypeError):
            cq.Vector(coords)


def test_issue_433_plane_axes():
    with pytest.raises(ValueError):
        cq.Plane((0, 0, 0), (0, 1, 0), (0, 2, 0))
    plane = cq.Plane((0, 0, 0), (1, 0, 1), (0, 0, 1))
    assert plane.xDir.dot(plane.zDir) == pytest.approx(0, abs=1e-12)
    assert plane.toWorldCoords((1, 0, 0)).toTuple() == pytest.approx(plane.xDir.toTuple())


def test_issue_2018_nested_assembly_add_remove():
    leaf = cq.Workplane().box(1, 1, 1)
    inner = cq.Assembly(name='inner').add(leaf, name='part')
    middle = cq.Assembly(name='middle').add(inner)
    root = cq.Assembly(name='root').add(middle)
    owned = root.objects['middle/inner']
    owned.add(leaf, name='extra')
    assert root.objects['middle/inner/extra'] is owned.objects['extra']
    root.remove('middle/inner/part')
    assert 'part' not in owned.objects
    assert 'inner/part' not in root.objects['middle'].objects
    root.remove('middle')
    assert set(root.objects) == {'root'}


def test_issue_2018_renamed_assembly_self_index():
    box = cq.Workplane().box(1, 2, 3)
    template = cq.Assembly(box, name='template').add(box, name='pin')
    root = cq.Assembly(name='root').add(template, name='mounted')
    mounted = root.objects['mounted']
    assert mounted.objects['mounted'] is mounted
    assert 'template' not in mounted.objects
    assert template.objects['template'] is template
    assert template.children[0].parent is template
    assert mounted.objects['pin'] is root.objects['mounted/pin']
    mounted.add(box, name='template')
    assert root.objects['mounted/template'] is mounted.objects['template']
    with pytest.raises(ValueError, match='Cannot remove the assembly itself'):
        mounted.remove('mounted')


def test_issue_2018_rename_cannot_hide_existing_descendant():
    box = cq.Workplane().box(1, 2, 3)
    template = cq.Assembly(name='template').add(box, name='pin')
    root = cq.Assembly(name='root')
    with pytest.raises(ValueError, match='already in the subassembly'):
        root.add(template, name='pin')
    assert root.children == []
    assert set(root.objects) == {'root'}
    assert template.objects['pin'] is template.children[0]


def test_issue_2084_parametric_helix():
    def helix(t):
        return cos(2*pi*t), sin(2*pi*t), t
    curve = cq.Workplane().parametricCurve(helix, stop=4).val()
    # A wrong low-degree fit can collapse several turns. Check the whole curve.
    for i in range(81):
        assert curve.distance(cq.Vertex.makeVertex(*helix(i/20))) < 0.005


def test_issue_2074_rotated_sphere_shell():
    shape = cq.Workplane('XZ').sphere(13).shell(-1).val()
    assert shape.isValid()
    assert shape.Volume() == pytest.approx(4*pi/3*(13**3-12**3), rel=1e-6)


def test_issue_2020_sphere_cut():
    a = cq.Workplane().transformed(offset=(-3, 0, 0)).sphere(5)
    b = cq.Workplane().transformed(offset=(3, 0, 0)).sphere(5)
    shape = b.cut(a).val()
    assert shape.isValid()
    overlap = pi * (20 + 6) * (10 - 6)**2 / 12
    assert shape.Volume() == pytest.approx(4*pi/3*5**3 - overlap, rel=1e-6)
    assert all(f.Area() > 0 for f in shape.Faces())


def test_issue_1485_find_solid_after_section():
    shape = cq.Workplane().box(1, 2, 3).section(0).findSolid()
    assert len(shape.Solids()) == 1
    assert shape.Volume() == pytest.approx(6)


@pytest.mark.skipif(
    int(OCP.__version__.split(".")[0]) < 8,
    reason="Exercise old-kernel memory exhaustion only in an isolated, memory-limited process",
)
def test_issue_1665_collinear_sketch_cut_preserves_rectangle():
    # The OCCT 7.9 runtime exhausts memory for this published sketch. OCCT 8
    # treats the zero-area subtraction as a no-op. Check the resulting solid,
    # not merely that the operation returned.
    x, y = 48.5800789794081, -3.3737790291878085
    height = 88.65465934289723
    result = (cq.Workplane().sketch().push([(x, y)])
              .rect(3.0, 87.6847679284009).rect(3.0, height)
              .polygon([(0, 0), (1, 1), (2, 2)], mode="s")
              .finalize().extrude(1).val())
    assert result.isValid()
    assert len(result.Solids()) == 1
    assert len(result.Faces()) == 6
    assert result.Volume() == pytest.approx(3 * height, rel=1e-10)
    assert result.Center().toTuple() == pytest.approx((x, y, .5), abs=1e-9)
