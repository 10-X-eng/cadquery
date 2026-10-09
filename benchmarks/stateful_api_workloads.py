"""Valid API stress cases to check reliability changes preserve common speed."""

import cadquery as cq


def workloads(steve=None, output_dir=None):
    def iterative_profiles():
        wp = cq.Workplane()
        for i in range(1200):
            wp.pushPoints([(3 * i, 0)]).circle(1)
        return cq.Compound.makeCompound(wp.ctx.pendingWires)

    def callback_array():
        wp = cq.Workplane().rarray(3, 3, 30, 30)
        prototype = cq.Solid.makeBox(1, 1, 1)
        return wp.eachpoint(lambda l: prototype.moved(l), True)

    def direct_shape_array():
        prototype = cq.Solid.makeBox(1, 1, 1)
        return cq.Workplane().rarray(3, 3, 30, 30).eachpoint(prototype, True)

    def closure():
        solids = []
        for _ in range(60):
            solids.append(
                cq.Workplane().lineTo(4, 0).lineTo(4, 3).close().extrude(2).val()
            )
        return cq.Compound.makeCompound(solids)

    def nested_assembly():
        part = cq.Solid.makeBox(1, 2, 3)
        result = cq.Assembly(name="root")
        source = cq.Assembly(name="sub").add(part, name="part")
        for i in range(300):
            result.add(source, name=f"instance{i}", loc=cq.Location((3 * i, 0, 0)))
        return result

    yield "iterative_pending_profiles", iterative_profiles
    yield "callback_array", callback_array
    yield "direct_shape_array", direct_shape_array
    yield "wire_closure", closure
    yield "nested_assembly", nested_assembly
