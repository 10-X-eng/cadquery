"""Semantic checks for optimized paths (timings live in benchmarks/)."""
import pytest
import cadquery as cq
from cadquery.selectors import StringSyntaxSelector


def test_surface_types_preserve_trimming_orientation_and_placement():
    shapes = [
        (cq.Workplane().box(6, 8, 10).val(), {'PLANE'}),
        (cq.Solid.makeCylinder(3, 7), {'PLANE', 'CYLINDER'}),
        (cq.Solid.makeCone(4, 2, 7), {'PLANE', 'CONE'}),
        (cq.Solid.makeSphere(5, angleDegrees1=-30, angleDegrees2=60), {'PLANE', 'SPHERE'}),
        (cq.Solid.makeTorus(8, 2), {'TORUS'}),
        (cq.Workplane().circle(10).workplane(offset=15).rect(12, 16)
         .workplane(offset=15).circle(6).loft().val(), {'PLANE', 'BSPLINE'}),
    ]
    location = cq.Location((12, -3, 7), (1, 2, 3), 47)
    for shape, kinds in shapes:
        for placed in (shape, shape.moved(location), shape.reverse().moved(location)):
            assert {face.geomType() for face in placed.Faces()} == kinds
            for face in placed.Faces():
                if face.geomType() == 'PLANE':
                    plane = face.toPln()
                    # The recovered infinite plane must still contain the
                    # trimmed face, including after a nontrivial placement.
                    for vertex in face.Vertices():
                        assert plane.Distance(vertex.Center().toPnt()) < 1e-7


@pytest.mark.parametrize('name', ['XY', 'YZ', 'ZX', 'XZ', 'YX', 'ZY', 'front',
                                  'back', 'left', 'right', 'top', 'bottom'])
def test_named_planes_have_independent_consistent_transforms(name):
    origin = cq.Vector(3, -5, 8)
    reference = cq.Plane.named(name, origin)
    factory = getattr(cq.Plane, name)
    assert factory(origin) == reference
    # Rotate the requested x direction in its plane and give it a normal
    # component: factories must project it and update their transforms.
    x_dir = (reference.xDir + reference.yDir).normalized()
    plane = factory(origin, x_dir + reference.zDir)
    assert plane.xDir.toTuple() == pytest.approx(x_dir.toTuple(), abs=1e-10)
    point = origin + plane.xDir * 2 + plane.yDir * 4 + plane.zDir * 6
    assert plane.toWorldCoords((2, 4, 6)).toTuple() == pytest.approx(point.toTuple())
    assert plane.toLocalCoords(point).toTuple() == pytest.approx((2, 4, 6))
    plane.origin = (0, 0, 0)
    assert reference.origin.toTuple() == origin.toTuple()
    assert cq.Plane.named(name, origin) == reference


def test_topology_iteration_preserves_order_location_orientation_and_uniqueness():
    from cadquery.occ_impl.shapes import TopTools_IndexedMapOfShape, inverse_shape_LUT
    from OCP.TopExp import TopExp

    box = cq.Workplane().box(1, 2, 3).val()
    shapes = [cq.Compound.makeCompound([]), box,
              cq.Compound.makeCompound([box, box, box.moved(cq.Location(5, 0, 0)),
                                        box.reverse()])]
    for shape in shapes:
        for kind in ('Vertex', 'Edge', 'Wire', 'Face', 'Shell', 'Solid', 'Compound'):
            expected = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape.wrapped, inverse_shape_LUT[kind], expected)
            actual = list(shape._entities(kind))
            assert len(actual) == expected.Extent()
            assert all(a.IsEqual(b) for a, b in zip(actual, expected))
    # Repeated and reversed references share topology; located instances do not.
    assert len(shapes[-1].Faces()) == 12


def test_new_object_preserves_chain_and_independent_plane():
    parent = cq.Workplane('YZ', origin=(1, 2, 3)).tag('source')
    child = parent.newObject(iter([cq.Vector(3, 4, 5)]))
    assert child.parent is parent
    assert child.ctx is parent.ctx
    assert child._tag is None
    assert child.plane == parent.plane
    assert child.plane is not parent.plane
    child.plane.origin = (9, 8, 7)
    assert parent.plane.origin.toTuple() == (1, 2, 3)
    assert child.val().toTuple() == (3, 4, 5)


def test_new_object_calls_subclass_constructor():
    class Custom(cq.Workplane):
        calls = 0
        def __init__(self):
            super().__init__()
            Custom.calls += 1
            self.custom_state = []
    parent = Custom()
    child = parent.newObject([])
    assert Custom.calls == 2
    assert isinstance(child, Custom)
    assert child.custom_state is not parent.custom_state


@pytest.mark.parametrize('callback', [False, True])
def test_eachpoint_on_rotated_translated_plane(callback):
    plane = cq.Plane((4, -2, 8), (1, 2, 0), (2, -1, 3))
    points = [cq.Vector(7, 8, 9), cq.Vertex.makeVertex(-3, 2, 1),
              cq.Sketch().rect(2, 3)]
    face = cq.Face.makePlane(1, 2)
    arg = (lambda loc: face.moved(loc)) if callback else face
    result = cq.Workplane(plane).newObject(points).eachpoint(
        arg, useLocalCoordinates=True, clean=False)
    for shape, center in zip(result.vals(), [(7, 8, 9), (-3, 2, 1), (0, 0, 0)]):
        assert shape.Center().toTuple() == pytest.approx(center, abs=1e-10)
        assert shape.normalAt().toTuple() == pytest.approx(plane.zDir.toTuple())


@pytest.mark.parametrize('clean', [False, True])
def test_cut_each_with_split_tool_surfaces(clean):
    from math import pi
    # Adjacent cylinders leave a same-domain split in the cutting tool.
    tool = cq.Solid.makeCylinder(1, 2, (0, 0, -4)).fuse(
        cq.Solid.makeCylinder(1, 2, (0, 0, -2)))
    shape = (cq.Workplane('YZ', origin=(3, 2, 1)).box(10, 10, 10)
             .faces('>X').workplane().cutEach(lambda loc: tool.moved(loc),
                                            useLocalCoords=True, clean=clean).val())
    assert shape.isValid()
    assert shape.Volume() == pytest.approx(1000 - 4*pi)
    if clean:
        assert len(shape.Faces()) == 8
    assert tool.Volume() == pytest.approx(4*pi)


def test_combined_center_single_pass_iterable_and_mutation():
    a = cq.Workplane().box(1, 1, 1).val()
    b = cq.Workplane().box(2, 2, 2).translate((9, 0, 0)).val()
    assert cq.Shape.CombinedCenter(iter([a, b])).toTuple() == pytest.approx((8, 0, 0))
    b.move(cq.Location(9, 0, 0))
    assert cq.Shape.CombinedCenter(iter([a, b])).toTuple() == pytest.approx((16, 0, 0))
    with pytest.raises(ValueError, match='zero total mass'):
        cq.Shape.CombinedCenter([])


def test_empty_compound_does_not_hide_face_or_edge_mass():
    empty = cq.Compound.makeCompound([cq.Compound.makeCompound([])])
    for shape, mass in [(cq.Face.makePlane(2, 3), 6),
                        (cq.Edge.makeLine((0, 0, 0), (3, 4, 0)), 5)]:
        obj = cq.Compound.makeCompound([empty, shape])
        assert obj.Volume() == pytest.approx(mass)
        assert obj.Center().toTuple() == pytest.approx(shape.Center().toTuple())


def test_string_filters_do_not_cache_shapes_or_share_public_state():
    wp = cq.Workplane().box(1, 2, 3)
    assert wp.faces('>Z').val().Center().z == pytest.approx(1.5)
    altered = StringSyntaxSelector('>Z')
    altered.mySelector = StringSyntaxSelector('<Z')
    assert wp.faces(altered).val().Center().z == pytest.approx(-1.5)
    moved = wp.translate((0, 0, 10))
    assert moved.faces('>Z').val().Center().z == pytest.approx(11.5)
    assert wp.faces('>Z').val().Center().z == pytest.approx(1.5)


@pytest.mark.parametrize('reverse', [False, True])
def test_tessellation_location_and_winding(reverse):
    shape = cq.Workplane().box(2, 3, 4).val()
    if reverse:
        shape = shape.reverse()
    loc = cq.Location((5, -2, 8), (1, 2, 3), 37)
    vertices, triangles = shape.tessellate(0.01)
    moved_vertices, moved_triangles = shape.moved(loc).tessellate(0.01)
    assert moved_triangles == triangles
    for vertex, moved in zip(vertices, moved_vertices):
        p = vertex.toPnt().Transformed(loc.wrapped.Transformation())
        assert moved.toTuple() == pytest.approx(p.Coord())
    # Signed mesh volume checks both face orientation and triangle indexing.
    volume = sum(vertices[a].dot(vertices[b].cross(vertices[c])) / 6
                 for a, b, c in triangles)
    assert volume == pytest.approx(-24 if reverse else 24)


def test_assembly_copy_paths_and_remove_only_target_branch():
    part = cq.Workplane().box(1, 1, 1)
    branch = cq.Assembly(name='branch').add(part, name='part')
    tree = cq.Assembly(name='tree').add(branch, name='a').add(
        branch, name='b', loc=cq.Location(2, 0, 0)
    )
    root = cq.Assembly(name='root').add(tree)
    assert set(root.objects['tree'].objects) == {'tree', 'a', 'a/part', 'b', 'b/part'}
    root.remove('tree/a')
    assert 'tree/a/part' not in root.objects
    assert 'a/part' not in root.objects['tree'].objects
    assert root.objects['tree/b/part'].obj is part
    assert len(root.toCompound().Solids()) == 1
    assert len(tree.toCompound().Solids()) == 2


def test_assembly_leaf_add_preserves_attributes_and_subclass_hooks():
    part = cq.Workplane().box(1, 2, 3)
    loc, color, metadata = cq.Location(2, 3, 4), cq.Color('red'), {'purpose': 'test'}
    root = cq.Assembly(name='root')
    root.add(part, name='part', loc=loc, color=color, metadata=metadata)
    child = root.objects['part']
    assert child.obj is part
    assert child.loc is loc
    assert child.color is color
    assert child.metadata is metadata
    assert child.objects['part'] is child
    with pytest.raises(ValueError, match='Unique name'):
        root.add(part, name='part')
    assert root.children == [child]

    class Custom(cq.Assembly):
        copies = 0
        def _copy(self):
            Custom.copies += 1
            return super()._copy()

    custom = Custom(name='custom').add(part, name='part')
    assert Custom.copies == 1
    assert isinstance(custom.objects['part'], Custom)


def test_gltf_failure_restores_assembly_location(monkeypatch, tmp_path):
    from cadquery.occ_impl.exporters import assembly as exporter
    assy = cq.Assembly(cq.Workplane().box(1, 1, 1), loc=cq.Location(1, 2, 3))
    original = assy.loc
    def fail(*args):
        raise RuntimeError('meshing failed')
    monkeypatch.setattr(exporter, 'toCAF', fail)
    with pytest.raises(RuntimeError, match='meshing failed'):
        exporter.exportGLTF(assy, str(tmp_path / 'failed.glb'))
    assert assy.loc is original


def test_gltf_shared_mesh_keeps_colors_names_and_placements(tmp_path):
    import json
    import struct
    part = cq.Workplane().box(2, 3, 4)
    assy = cq.Assembly(name='root')
    colors = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    for i, color in enumerate(colors):
        assy.add(part, name=f'part_{i}', color=cq.Color(*color), loc=cq.Location(10*i, 0, 0))
    path = tmp_path / 'shared.glb'
    assy.export(str(path))
    data = path.read_bytes()
    size = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20+size])
    nodes = {node['name']: node for node in gltf['nodes']}
    positions = []
    for i, color in enumerate(colors):
        node = nodes[f'part_{i}']
        assert node.get('translation', [0, 0, 0]) == pytest.approx((10*i, 0, 0))
        primitives = gltf['meshes'][node['mesh']]['primitives']
        positions.append([p['attributes']['POSITION'] for p in primitives])
        for primitive in primitives:
            material = gltf['materials'][primitive['material']]
            assert material['pbrMetallicRoughness']['baseColorFactor'] == pytest.approx((*color, 1))
    assert positions[0] == positions[1] == positions[2]
    assert len(assy.children) == 3


def test_gltf_shared_geometry_keeps_per_face_colors(tmp_path):
    import json
    import struct
    part = cq.Workplane().box(2, 3, 4)
    top = part.faces('>Z').val()
    top_index = part.val().Faces().index(top)
    assy = cq.Assembly(name='root')
    for name, base, face in [('a', (1, 0, 0), (1, 1, 0)), ('b', (0, 0, 1), (0, 1, 0))]:
        assy.add(part, name=name, color=cq.Color(*base))
        assy.objects[name].addSubshape(top, name='top', color=cq.Color(*face))
    path = tmp_path / 'face-colors.glb'
    assy.export(str(path))
    data = path.read_bytes()
    size = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20+size])
    nodes = {node['name']: node for node in gltf['nodes']}
    for name, expected in [('a', (1, 1, 0, 1)), ('b', (0, 1, 0, 1))]:
        primitive = gltf['meshes'][nodes[name]['mesh']]['primitives'][top_index]
        material = gltf['materials'][primitive['material']]
        assert material['pbrMetallicRoughness']['baseColorFactor'] == pytest.approx(expected)
