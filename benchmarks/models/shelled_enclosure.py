"""Open instrument enclosure: offset shell, rounded rim, bosses and blind holes."""
import cadquery as cq

body = (cq.Workplane("XY").box(96, 64, 32, centered=(True, True, False))
        .edges("|Z").fillet(6).faces(">Z").shell(-2))
mounts = [(-38, -22), (-38, 22), (38, -22), (38, 22)]
bosses = cq.Workplane("XY").pushPoints(mounts).circle(5).extrude(14)
body = body.union(bosses)
holes = cq.Workplane("XY").workplane(offset=4).pushPoints(mounts).circle(1.6).extrude(12)
result = body.cut(holes)
