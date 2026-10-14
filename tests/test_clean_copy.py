"""clean() merges a copy and never breaks a face that was sound.

The face merge (ShapeUpgrade_UnifySameDomain) rewrites the edges and faces it
works on in place, and a boolean's result shares them with its inputs. Its
wire repair can also turn a torus face with holes inside out.
"""
import pytest
import cadquery as cq
from cadquery import Solid, Vector
from cadquery.func import clean


def collar_and_ring():
    ring = Solid.makeTorus(1800, 230)
    collar = Solid.makeCylinder(1280, 400, Vector(0, 0, -200))
    for d in ((0.7071, 0.7071, 0), (-0.7071, 0.7071, 0), (-0.7071, -0.7071, 0), (0.7071, -0.7071, 0)):
        spoke = Solid.makeCylinder(80, 1800 - 1240, Vector(d[0] * 1240, d[1] * 1240, 0), Vector(*d))
        collar = collar.fuse(spoke)
    return collar, ring


@pytest.mark.parametrize("merge", [lambda s: s.clean(), clean])
def test_torus_with_holes_stays_valid_and_inputs_untouched(merge):
    collar, ring = collar_and_ring()
    raw = collar.fuse(ring)
    volume = raw.Volume()
    cleaned = merge(raw)
    assert cleaned.isValid()
    assert cleaned.Volume() == pytest.approx(volume, rel=1e-9)
    assert all(f.Area() > 0 for f in cleaned.Faces())
    assert raw.isValid() and ring.isValid() and collar.isValid()
    assert raw.Volume() == pytest.approx(volume, rel=1e-12)


def test_union_of_valid_solids_is_valid():
    collar, ring = collar_and_ring()
    result = cq.Workplane().add(collar).union(cq.Workplane().add(ring)).val()
    assert result.isValid()
    assert result.Volume() == pytest.approx(collar.fuse(ring).Volume(), rel=1e-9)


def test_clean_still_merges_and_leaves_its_input_alone():
    a = Solid.makeBox(1, 1, 1)
    raw = a.fuse(a.moved(cq.Location(Vector(1, 0, 0))))
    assert len(raw.Faces()) == 10
    cleaned = raw.clean()
    assert len(cleaned.Faces()) == 6
    assert cleaned.isValid()
    assert len(raw.Faces()) == 10 and raw.isValid()


def test_faces_the_merge_leaves_alone_keep_their_identity():
    a = Solid.makeBox(1, 1, 1)
    tower = Solid.makeBox(0.5, 0.5, 1, Vector(0.25, 0.25, 1))
    raw = a.fuse(a.moved(cq.Location(Vector(1, 0, 0)))).fuse(tower)
    cleaned = raw.clean()
    kept = [f for f in cleaned.Faces() if any(f.isSame(g) for g in raw.Faces())]
    assert cleaned.isValid()
    assert len(cleaned.Faces()) < len(raw.Faces())
    assert len(kept) >= 4  # the tower's sides and top
