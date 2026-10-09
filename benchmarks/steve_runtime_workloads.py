"""Steve build/export integration workloads, run inside its geometry image.

Use compare.py --suite benchmarks/steve_runtime_workloads.py --steve /steve.
Mount Steve's runtime and examples at /steve/{runtime,examples}. Each CadQuery
source tree must target its worker's OCP version. compare.py can use separate
Docker images for dependency comparisons. Output stays in temporary dirs.
"""
import os
from pathlib import Path
import sys
import tempfile
import time


TIMING_SCOPE = "feature_runtime.run_request; validation and fixture cleanup excluded"


def models(steve):
    """Named request inputs; keep generated models alongside this benchmark."""
    for name in ('plate', 'bearing_pedestal', 'design', 'modeling/housing',
                 'modeling/flange', 'modeling/impeller',
                 'modeling/sheet_metal_bracket', 'modeling/sheet_metal_return_tray',
                 'modeling/sheet_metal_enclosure', 'modeling/turbine_stage'):
        yield name.replace('/', '_'), {
            'code': (steve / 'examples' / (name + '.py')).read_text(),
            'kind': 'design' if name == 'design' else 'part'}
    for name in ('planetary_gearset', 'turbo_rotor'):
        root = steve / 'examples' / 'modeling' / name
        yield name, {'kind': 'design', 'code': (root / 'main.py').read_text(),
                     'files': {str(path.relative_to(root)): path.read_text()
                               for path in sorted(root.rglob('*.py'))
                               if path.name not in ('main.py', '__init__.py')}}
    for path in sorted(Path(__file__).with_name('models').glob('*.py')):
        yield path.stem, {'code': path.read_text(),
                          'kind': 'design' if path.stem in ('colored_rack', 'varied_linkage') else 'part'}


def workloads(steve, output_dir=None):
    sys.path.insert(0, str(steve))
    sys.path.insert(0, str(steve / 'runtime'))
    import run as runtime
    # features.runtime prepends /opt/cad. Bind Steve's package first so its
    # relative imports keep using the selected checkout, not an older image.
    import steve as steve_api
    from app.features import runtime as feature_runtime, trace

    for name, request in models(steve):
        for mode in ('preview', 'full'):
            def build(request=request, name=name, mode=mode):
                previous = Path.cwd()
                previous_path = sys.path[:]
                with tempfile.TemporaryDirectory(dir=output_dir) as directory:
                    try:
                        os.chdir(directory)
                        # Production jobs run in separate forked children.
                        # Do not retain models from earlier benchmark jobs.
                        if 'steve.model' in sys.modules:
                            sys.modules['steve.model']._ACTIVE.clear()
                        trace.reset(None)
                        runtime.STARTED = time.monotonic()
                        wall_start, cpu_start = time.perf_counter(), time.process_time()
                        result = feature_runtime.run_request({**request, 'mode': mode,
                            'timeout': 180})['metadata']
                        timing = {'elapsed_s': time.perf_counter() - wall_start,
                                  'cpu_s': time.process_time() - cpu_start}
                        if result['topology']['state'] != 'complete':
                            raise AssertionError(f'{name}: incomplete viewer topology')
                        if not Path('preview.glb').is_file():
                            raise AssertionError(f'{name}: missing viewer export')
                        if mode == 'full' and not Path('result.step').is_file():
                            raise AssertionError(f'{name}: missing STEP export')
                        errors = [f for f in result.get('modeling', {}).get('features', [])
                                  if f['status'] == 'error']
                        if errors:
                            raise AssertionError(f'{name}: failed model features: {errors}')
                        if mode == 'full' and request['kind'] == 'part':
                            if not result['feature_tree']['equivalence']['passed']:
                                raise AssertionError(f'{name}: feature-history replay differs')
                        result['_benchmark_timing'] = timing
                        return result
                    finally:
                        os.chdir(previous)
                        sys.path[:] = previous_path
                        # Uploaded design modules must be rebuilt in the next
                        # job, just as they are in fresh production children.
                        for module_name, module in list(sys.modules.items()):
                            file = getattr(module, '__file__', None)
                            if file and Path(file).is_relative_to(directory):
                                del sys.modules[module_name]
            yield name + '_' + mode, build
