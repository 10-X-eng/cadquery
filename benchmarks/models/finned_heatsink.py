"""Thirty-two thin fins joined in one union, then cross-cut and drilled."""
import cadquery as cq

base = cq.Workplane("XY").box(100, 70, 5, centered=(True, True, False))
fins = (cq.Workplane("XY").workplane(offset=4)
        .pushPoints([(0, -31 + 2 * i) for i in range(32)])
        .rect(90, 0.8).extrude(24, combine=False))
body = base.union(fins)
slots = (cq.Workplane("XY").workplane(offset=14)
         .pushPoints([(-25, 0), (0, 0), (25, 0)]).rect(3, 70).extrude(16))
body = body.cut(slots)
holes = (cq.Workplane("XY").pushPoints([(-47, -30), (-47, 30), (47, -30), (47, 30)])
         .circle(1.6).extrude(5))
result = body.cut(holes)
