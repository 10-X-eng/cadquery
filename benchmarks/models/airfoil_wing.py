"""Five smooth NACA-style airfoil sections with taper, sweep and washout."""
import math
import cadquery as cq


def section(chord, span, sweep, twist):
    # Cosine spacing resolves the leading edge. The closed-edge coefficient
    # avoids a tiny trailing-edge gap and makes each periodic spline a wire.
    xs = [(1 - math.cos(math.pi * i / 40)) / 2 for i in range(41)]
    def point(x, sign):
        y = sign * 5 * 0.12 * (0.2969 * math.sqrt(x) - 0.126 * x
            - 0.3516 * x*x + 0.2843 * x**3 - 0.1036 * x**4)
        a = math.radians(twist)
        return (sweep + chord * (x * math.cos(a) - y * math.sin(a)),
                chord * (x * math.sin(a) + y * math.cos(a)), span)
    points = [point(x, 1) for x in reversed(xs)]
    points += [point(x, -1) for x in xs[1:-1]]
    return cq.Wire.assembleEdges([cq.Edge.makeSpline([cq.Vector(p) for p in points], periodic=True)])


wires = [section(60 - 7*i, 30*i, 5*i, -2*i) for i in range(5)]
result = cq.Workplane().add(cq.Solid.makeLoft(wires))
