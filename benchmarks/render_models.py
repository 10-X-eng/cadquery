"""Render an overview of the six added workloads; never part of timed runs.

Requires Matplotlib and NumPy in addition to CadQuery. Run with the selected
CadQuery checkout on PYTHONPATH, outside the source tree if using a backport.
"""
import argparse
from pathlib import Path
import runpy

import cadquery as cq
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    names = ("shelled_enclosure", "finned_heatsink", "helical_auger",
             "airfoil_wing", "spherical_valve", "varied_linkage")
    figure = plt.figure(figsize=(15, 10), facecolor="#f5f6f8")
    for index, name in enumerate(names, 1):
        result = runpy.run_path(str(Path(__file__).with_name("models") / (name + ".py")))["result"]
        shape = result.toCompound() if isinstance(result, cq.Assembly) else result.val()
        vertices, triangles = shape.tessellate(0.05, 0.2)
        points = np.asarray([v.toTuple() for v in vertices])
        facets = points[np.asarray(triangles)]
        normals = np.cross(facets[:, 1] - facets[:, 0], facets[:, 2] - facets[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        normals /= np.maximum(lengths[:, None], 1e-15)
        light = np.array([0.3, -0.6, 0.74])
        brightness = 0.5 + 0.5 * np.abs(normals @ light)
        colors = brightness[:, None] * np.array([0.28, 0.56, 0.74])
        axes = figure.add_subplot(2, 3, index, projection="3d", facecolor="#f5f6f8")
        axes.add_collection3d(Poly3DCollection(facets, facecolors=colors, linewidths=0, antialiased=False))
        low, high = points.min(axis=0), points.max(axis=0)
        center = (low + high) / 2
        radius = max(high - low) * 0.52
        axes.set_xlim(center[0] - radius, center[0] + radius)
        axes.set_ylim(center[1] - radius, center[1] + radius)
        axes.set_zlim(center[2] - radius, center[2] + radius)
        axes.set_box_aspect((1, 1, 1))
        axes.view_init(elev=27, azim=-60)
        axes.set_axis_off()
        axes.set_title(name.replace("_", " ").title(), fontsize=14, color="#243345")
    figure.subplots_adjust(left=0, right=1, bottom=0, top=0.95, wspace=0, hspace=0.02)
    figure.savefig(args.output, dpi=140, facecolor=figure.get_facecolor())
    plt.close(figure)


if __name__ == "__main__":
    main()
