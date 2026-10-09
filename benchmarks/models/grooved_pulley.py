"""Revolved pulley with belt grooves, hub bore and a keyway cut."""
import cadquery as cq

profile = [(8, 0), (30, 0), (30, 4), (25, 7), (30, 10), (30, 14),
           (25, 17), (30, 20), (30, 24), (16, 24), (16, 34), (8, 34)]
body = cq.Workplane("XZ").polyline(profile).close().revolve(360, (0, 0), (0, 1))
keyway = cq.Workplane("XY").center(0, 8).rect(5, 5).extrude(34)
result = body.cut(keyway)
