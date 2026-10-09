"""Ported ball valve with an angled cross-bore, stem socket and trimmed poles."""
import cadquery as cq

ball = cq.Workplane("XY").sphere(22)
port = cq.Workplane("YZ").circle(9).extrude(60, both=True)
cross_port = (cq.Workplane("YZ").circle(5).extrude(28)
              .rotate((0, 0, 0), (0, 0, 1), 55))
socket = cq.Workplane("XY").workplane(offset=16).rect(8, 8).extrude(12)
flat = cq.Workplane("XY").workplane(offset=-22).box(60, 60, 8)
result = ball.cut(port).cut(cross_port).cut(socket).cut(flat)
