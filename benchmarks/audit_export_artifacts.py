"""Validate generated archive contents while a Steve validation job still owns them.

This checks completeness, finite STL data, manifest consistency, and requested
mesh settings. It is not a surface-deflection proof or a substitute for the
independent meshing and STEP round-trip regression tests.
"""

import hashlib
import json
import math
from pathlib import Path
import struct
import zipfile


def audit(metadata, mode):
    files = {p.name: p for p in Path.cwd().iterdir() if p.is_file()
             and p.suffix in {".glb", ".step", ".zip", ".json", ".svg", ".dxf"}}
    result = {"files": sorted(files), "viewer_tessellation": metadata.get("tessellation")}
    for name in ("preview.glb",):
        data = files[name].read_bytes()
        assert data[:4] == b"glTF" and struct.unpack_from("<I", data, 4)[0] == 2
        assert struct.unpack_from("<I", data, 8)[0] == len(data)
    if mode == "preview":
        return result

    def step_header(data):
        stripped = data.strip()
        assert stripped.startswith(b"ISO-10303-21;")
        assert stripped.endswith(b"END-ISO-10303-21;")

    step_header(files["result.step"].read_bytes())
    if metadata.get("solids", 0):
        assert metadata.get("body_meshes"), "Full solid model omitted its print meshes"
    for name, key in (("bodies-mesh.zip", "body_meshes"),
                      ("components-step.zip", "component_steps")):
        expected = metadata.get(key)
        assert (name in files) == bool(expected), f"{name}: metadata/file mismatch"
        if not expected:
            continue
        with zipfile.ZipFile(files[name]) as archive:
            assert archive.testzip() is None, f"{name}: CRC failure"
            entries = archive.namelist()
            assert len(entries) == len(set(entries)), f"{name}: duplicate archive entries"
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["items"] == expected, f"{name}: manifest differs from metadata"
            assert set(entries) == {"manifest.json", *(item["file"] for item in expected)}
            details = []
            for item in expected:
                data = archive.read(item["file"])
                detail = {k: item[k] for k in ("instance", "body", "key", "name", "file") if k in item}
                detail["bytes"] = len(data)
                detail["sha256"] = hashlib.sha256(data).hexdigest()
                if key == "component_steps":
                    step_header(data)
                else:
                    assert len(data) >= 84, f"{item['file']}: truncated STL header"
                    count = struct.unpack_from("<I", data, 80)[0]
                    assert count == item["triangles"] and count > 0
                    assert len(data) == 84 + 50 * count, f"{item['file']}: STL size mismatch"
                    lower, upper = [math.inf] * 3, [-math.inf] * 3
                    for triangle in struct.iter_unpack("<12fH", data[84:]):
                        assert all(math.isfinite(v) for v in triangle[:12]), f"{item['file']}: nonfinite mesh"
                        for start in (3, 6, 9):
                            for axis in range(3):
                                lower[axis] = min(lower[axis], triangle[start + axis])
                                upper[axis] = max(upper[axis], triangle[start + axis])
                    detail.update(triangles=count, mesh_extent_mm=lower + upper,
                                  exact_extent_mm=item["extent_mm"],
                                  mass_properties=item["mass_properties"], placement=item["placement"],
                                  material=item["material"], density_g_cm3=item["density_g_cm3"])
                    assert all(math.isfinite(v) for v in item["extent_mm"])
                    # This is an outer-bound sanity check, not a lower bound on
                    # surface sampling quality. Account for float32 STL output.
                    for lo, hi, exact_lo, exact_hi in zip(lower, upper, item["extent_mm"][:3], item["extent_mm"][3:]):
                        epsilon = 1e-4 + 2e-7 * max(abs(exact_lo), abs(exact_hi))
                        assert lo >= exact_lo - epsilon and hi <= exact_hi + epsilon
                details.append(detail)
            result[key] = {"count": len(details), "items": details}
            if key == "body_meshes":
                result[key]["settings"] = {k: manifest[k] for k in
                    ("units", "frame", "pose", "linear_tessellation_mm", "angular_tessellation_rad")}
    return result
