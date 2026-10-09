"""A thin circular-to-elliptical transition with independent inner/outer lofts."""
import cadquery as cq

outer = (cq.Workplane("XY").circle(20).workplane(offset=25).ellipse(25, 17)
         .workplane(offset=35).ellipse(32, 14).loft())
inner = (cq.Workplane("XY").circle(18).workplane(offset=25).ellipse(23, 15)
         .workplane(offset=35).ellipse(30, 12).loft())
result = outer.cut(inner)
