"""200 colored instances of two parts, arranged into nested assemblies."""
import cadquery as cq

block = cq.Workplane("XY").box(18, 18, 8).edges("|Z").fillet(2)
bolt = cq.Workplane("XY").circle(2).extrude(9).faces(">Z").workplane().polygon(6, 7).extrude(3)
result = cq.Assembly(name="rack")
for row in range(10):
    shelf = cq.Assembly(name=f"shelf_{row}")
    for column in range(10):
        color = cq.Color(0.2 + row * 0.07, 0.2 + column * 0.07, 0.6)
        shelf.add(block, name=f"block_{column}", loc=cq.Location(cq.Vector(column * 24, 0, 0)), color=color)
        shelf.add(bolt, name=f"bolt_{column}", loc=cq.Location(cq.Vector(column * 24, 0, 4)), color=cq.Color(0.7, 0.7, 0.75))
    result.add(shelf, loc=cq.Location(cq.Vector(0, row * 24, row * 3)))
