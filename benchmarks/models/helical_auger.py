"""Two-turn helical blade fused to a bored shaft; curved boolean and meshing load."""
import cadquery as cq

shaft = cq.Workplane("XY").circle(6).extrude(72)
blade = (cq.Workplane("XY").moveTo(11, 0).rect(14, 2)
         .twistExtrude(72, 720))
result = shaft.union(blade).faces(">Z").workplane().hole(5)
