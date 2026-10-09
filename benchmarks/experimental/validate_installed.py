"""Run existing quality checks while verifying CadQuery comes from the package.

Mount this repository at --root and provide its test dependencies separately.
The working directory supplies fixtures; it must not supply the CadQuery import.
"""
import argparse
import os
from pathlib import Path
import sys
import sysconfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    os.chdir(root)
    sys.path[:] = [entry for entry in sys.path if entry and Path(entry).resolve() != root]
    import cadquery
    installed = Path(sysconfig.get_paths()['purelib']).resolve()
    assert Path(cadquery.__file__).resolve().is_relative_to(installed), cadquery.__file__
    print('Installed CadQuery:', cadquery.__file__, flush=True)
    from cadquery.occ_impl.shapes import setThreads
    setThreads(1)
    import pytest
    checks = ['tests', 'benchmarks/test_native_affine_normals.py',
              'benchmarks/test_native_affine_scale.py',
              'benchmarks/test_native_affine_precision.py',
              'benchmarks/test_native_line_plane.py']
    raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider',
                                 *[str(root / check) for check in checks]]))


if __name__ == '__main__':
    main()
