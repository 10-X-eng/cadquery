"""Analytic geometry oracles for the experimental line/plane extrema path."""

import math

import cadquery as cq
import pytest
from OCP.Extrema import Extrema_ExtCS, Extrema_POnCurv, Extrema_POnSurf
from OCP.Geom import Geom_Line, Geom_Plane
from OCP.GeomAdaptor import GeomAdaptor_Curve, GeomAdaptor_Surface
from OCP.gp import gp_Ax3, gp_Dir, gp_Lin, gp_Pln, gp_Pnt, gp_Vec


def pair(target, direction, placement, parameter=5):
    trsf = placement.wrapped.Transformation()
    unit = gp_Dir(*direction)
    point = gp_Pnt(*target)
    origin = point.Translated(gp_Vec(unit).Multiplied(-parameter))
    line = gp_Lin(origin, unit).Transformed(trsf)
    plane = gp_Pln(gp_Ax3(gp_Pnt(), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))).Transformed(trsf)
    curve = GeomAdaptor_Curve(Geom_Line(line), 0, 10)
    surface = GeomAdaptor_Surface(Geom_Plane(plane), -8, 8, -6, 6)
    return curve, surface, point.Transformed(trsf), plane


PLACEMENTS = [
    cq.Location(),
    cq.Location((7, -13, 4), (1, 2, 3), 37),
    cq.Location((1e6, -2e6, 3e6), (2, -1, 3), 73),
]


@pytest.mark.parametrize("placement", PLACEMENTS)
@pytest.mark.parametrize("direction", [(0, 0, 1), (1, 2, 3), (1, 1, -2)])
@pytest.mark.parametrize("target", [(0, 0, 0), (8, 0, 0), (0, -6, 0), (-8, 6, 0)])
def test_transverse_intersection(target, direction, placement):
    curve, surface, target_point, plane = pair(target, direction, placement)
    extrema = Extrema_ExtCS(curve, surface, 1e-9, 1e-9)
    assert extrema.IsDone() and not extrema.IsParallel()
    assert extrema.NbExt() >= 1
    index = min(range(1, extrema.NbExt() + 1), key=extrema.SquareDistance)
    on_curve, on_surface = Extrema_POnCurv(), Extrema_POnSurf()
    extrema.Points(index, on_curve, on_surface)
    assert on_curve.Parameter() == pytest.approx(5, abs=2e-8)
    assert on_curve.Value().Distance(target_point) < 2e-8
    assert on_curve.Value().Distance(curve.Value(on_curve.Parameter())) < 1e-9
    assert on_surface.Value().Distance(target_point) < 2e-8
    assert plane.Distance(on_surface.Value()) < 2e-8
    assert extrema.SquareDistance(index) < 1e-14


@pytest.mark.parametrize("slope", [1e-3, 1e-6, 1e-9, -1e-9])
def test_shallow_transverse_intersection(slope):
    curve, surface, target, _ = pair((0, 0, 0), (1, 0, slope), cq.Location())
    extrema = Extrema_ExtCS(curve, surface, 1e-9, 1e-9)
    assert extrema.IsDone() and not extrema.IsParallel()
    assert extrema.NbExt() >= 1
    index = min(range(1, extrema.NbExt() + 1), key=extrema.SquareDistance)
    on_curve, on_surface = Extrema_POnCurv(), Extrema_POnSurf()
    extrema.Points(index, on_curve, on_surface)
    assert on_curve.Parameter() == pytest.approx(5, abs=1e-7)
    assert on_curve.Value().Distance(target) < 1e-7
    assert extrema.SquareDistance(index) < 1e-14


@pytest.mark.parametrize("placement", PLACEMENTS)
@pytest.mark.parametrize("height", [0, 2])
def test_parallel_status_and_distance(height, placement):
    curve, surface, _, _ = pair((0, 0, height), (1, 0, 0), placement)
    extrema = Extrema_ExtCS(curve, surface, 1e-9, 1e-9)
    assert extrema.IsDone() and extrema.IsParallel()
    assert extrema.SquareDistance(1) == pytest.approx(height * height, abs=1e-8)


@pytest.mark.parametrize("ranges", [
    (6, 10, -8, 8, -6, 6),
    (0, 4, -8, 8, -6, 6),
    (0, 10, 1, 8, -6, 6),
    (0, 10, -8, 8, -6, -1),
])
def test_explicit_trim_bounds_exclude_intersection(ranges):
    curve, surface, _, _ = pair((0, 0, 0), (1, 1, 2), cq.Location())
    extrema = Extrema_ExtCS(curve, surface, *ranges, 1e-9, 1e-9)
    assert extrema.IsDone() and not extrema.IsParallel()
    for index in range(1, extrema.NbExt() + 1):
        on_curve, on_surface = Extrema_POnCurv(), Extrema_POnSurf()
        extrema.Points(index, on_curve, on_surface)
        u, v = on_surface.Parameter()
        assert ranges[0] - 1e-9 <= on_curve.Parameter() <= ranges[1] + 1e-9
        assert ranges[2] - 1e-9 <= u <= ranges[3] + 1e-9
        assert ranges[4] - 1e-9 <= v <= ranges[5] + 1e-9
        assert math.isfinite(extrema.SquareDistance(index))


def test_short_curve_fallback_point_matches_its_parameter():
    curve = GeomAdaptor_Curve(
        Geom_Line(gp_Lin(gp_Pnt(2, 3, 5), gp_Dir(1, 1, 1))), 0, 1e-8)
    surface = GeomAdaptor_Surface(
        Geom_Plane(gp_Pln(gp_Pnt(), gp_Dir(0, 0, 1))), -20, 20, -20, 20)
    extrema = Extrema_ExtCS(curve, surface, 1e-9, 1e-9)
    assert extrema.IsDone() and not extrema.IsParallel()
    assert extrema.NbExt() == 1
    on_curve, on_surface = Extrema_POnCurv(), Extrema_POnSurf()
    extrema.Points(1, on_curve, on_surface)
    assert on_curve.Parameter() == pytest.approx(5e-9, rel=1e-14, abs=0)
    assert on_curve.Value().Distance(curve.Value(on_curve.Parameter())) < 1e-12
    assert on_curve.Value().SquareDistance(on_surface.Value()) == pytest.approx(
        extrema.SquareDistance(1), rel=1e-14, abs=1e-12)
    u, v = on_surface.Parameter()
    assert on_surface.Value().Distance(surface.Value(u, v)) < 1e-12
