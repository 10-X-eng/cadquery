import cadquery as cq
from steve import Model

length = 60  # mm Block length (X)
width = 40  # mm Block width (Y)
height = 20  # mm Block height (Z)
corner_r = 5  # mm Vertical corner radius
top_r = 2  # mm Top edge round
bottom_ch = 1  # mm Bottom edge chamfer
hole_d = 6.6  # mm Centre through-hole (M6 clearance)
cbore_d = 11  # mm Counterbore diameter (M6 SHCS)
cbore_depth = 6.5  # mm Counterbore depth
mount_d = 4.5  # mm Corner hole diameter (M4 clearance)
csk_d = 9  # mm Corner countersink diameter (M4 flat head)
mount_x = 22  # mm Corner hole X offset from centre
mount_y = 12  # mm Corner hole Y offset from centre
text_size = 7  # mm Engraved label height
text_depth = 0.6  # mm Engraving depth

model = Model()
with model.sketch("sketch_1", on="XY", name="Base") as s:
    s.center_rect("r1", (0.0, 0.0), length, width)
model.extrude("extrude_1", "sketch_1", distance=height)
model.fillet("fillet_1", edges=["extrude_1.lateral_edges"], radius=corner_r)
model.fillet("fillet_top", edges=cq.selectors.BoxSelector((-length, -width, height - 0.1), (length, width, height + 0.1)), radius=top_r)
model.chamfer("chamfer_bottom", edges=cq.selectors.BoxSelector((-length, -width, -0.1), (length, width, 0.1)), distance=bottom_ch)
model.hole("hole_center", on="extrude_1.end", points=[(0, 0)], diameter=hole_d, kind="counterbore", cbore_diameter=cbore_d, cbore_depth=cbore_depth)
model.hole("hole_mounts", on="extrude_1.end", points=[(mount_x, mount_y), (-mount_x, mount_y), (mount_x, -mount_y), (-mount_x, -mount_y)], diameter=mount_d, kind="countersink", csk_diameter=csk_d)
label_solid = cq.Workplane(cq.Plane(origin=(0, -width / 2 + text_depth, height / 2), xDir=(1, 0, 0), normal=(0, -1, 0))).text("BLOCKY", text_size, 2 * text_depth, kind="bold")
model.add("label_b", cq.Workplane().add(label_solid.val().Solids()[0]), op="cut")
model.add("label_l", cq.Workplane().add(label_solid.val().Solids()[1]), op="cut")
model.add("label_o", cq.Workplane().add(label_solid.val().Solids()[2]), op="cut")
model.add("label_c", cq.Workplane().add(label_solid.val().Solids()[3]), op="cut")
model.add("label_k", cq.Workplane().add(label_solid.val().Solids()[4]), op="cut")
model.add("label_y", cq.Workplane().add(label_solid.val().Solids()[5]), op="cut")
result = model.result()
