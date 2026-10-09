"""225 through holes exercise booleans, topology, meshing and large history replay."""
import cadquery as cq

points = [((i - 7) * 8, (j - 7) * 8) for i in range(15) for j in range(15)]
result = (cq.Workplane("XY").box(128, 128, 5)
          .edges("|Z").fillet(4)
          .faces(">Z").workplane().pushPoints(points).hole(4))
