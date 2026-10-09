"""A hollow tube swept along a curved spline with an inflection."""
import cadquery as cq

path = cq.Workplane("XZ").spline([(0, 0), (16, 24), (-8, 48), (0, 80)])
result = cq.Workplane("XY").circle(2).circle(1.5).sweep(path)
