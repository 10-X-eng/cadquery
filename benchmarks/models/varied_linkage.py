"""120 located parts: unique link sizes, nested rotations and reused pins."""
import math
import cadquery as cq

pin = cq.Workplane("XY").circle(2).extrude(9)
result = cq.Assembly(name="linkages")
for row in range(8):
    chain = cq.Assembly(name=f"chain_{row}")
    x, y = 0.0, 0.0
    for index in range(5):
        length = 18 + row + 2 * index
        link = (cq.Workplane("XY").moveTo(length / 2, 0)
                .slot2D(length + 8, 8).extrude(3)
                .faces(">Z").workplane(centerOption="ProjectedOrigin")
                .pushPoints([(0, 0), (length, 0)]).hole(4.2))
        joint = cq.Assembly(name=f"joint_{index}")
        joint.add(link, name="link", color=cq.Color(0.2 + row * 0.08, 0.3, 0.7))
        joint.add(pin, name="pin_start", loc=cq.Location(cq.Vector(0, 0, -3)))
        joint.add(pin, name="pin_end", loc=cq.Location(cq.Vector(length, 0, -3)))
        angle = 20 * math.sin(index + row / 2)
        chain.add(joint, loc=cq.Location(cq.Vector(x, y, index * 4), cq.Vector(0, 0, 1), angle))
        x += length * math.cos(math.radians(angle))
        y += length * math.sin(math.radians(angle))
    result.add(chain, loc=cq.Location(cq.Vector(0, row * 35, 0), cq.Vector(1, 0, 0), row * 3))
