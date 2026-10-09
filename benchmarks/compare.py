"""Compare two source trees with alternating warm subprocess measurements.

Example:
    python benchmarks/compare.py --baseline /tmp/cadquery-baseline \
        --candidate . --steve ../ --output results.json

By default both versions use the same interpreter/dependencies. Optional Docker
images allow explicit comparisons across dependency versions. Imports and setup
are not included in timing; fresh-export workloads include creation and meshing.
"""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import uuid


WORKER = r'''
import sys, json, runpy, tempfile, time, os, platform, hashlib
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
if sys.argv[6]:
    os.sched_setaffinity(0, {int(sys.argv[6])})
sys.path.insert(0, sys.argv[1])
import cadquery as cq
import OCP
from cadquery.func import setThreads
from OCP.OSD import OSD_ThreadPool
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
if int(sys.argv[4]):
    setThreads(int(sys.argv[4]))

def checks(result):
    if isinstance(result, dict):
        selected = {key: result[key] for key in ('components', 'solids', 'faces',
            'bounds_mm', 'volume_mm3', 'surface_area_mm2', 'center_of_mass_mm', 'topology')
            if key in result}
        selected['feature_errors'] = [(f['id'], f.get('error'))
            for f in result.get('modeling', {}).get('features', []) if f['status'] == 'error']
        selected['history_equivalent'] = result.get('feature_tree', {}).get('equivalence', {}).get('passed')
        return selected
    if isinstance(result, cq.Assembly):
        result = result.toCompound()
    if isinstance(result, cq.Workplane):
        result = cq.Compound.makeCompound(result.vals())
    if isinstance(result, cq.Shape):
        # BoundingBox's default may include triangulation deflection. Compare
        # exact geometry here so changing a valid tessellation cannot change
        # the reported solid bounds. Quality checks cover the mesh separately.
        native_box = Bnd_Box()
        BRepBndLib.AddOptimal_s(result.wrapped, native_box, False, False)
        box = cq.BoundBox(native_box)
        return {'valid': result.isValid(), 'solids': len(result.Solids()),
            'volume': result.Volume(), 'area': result.Area(),
            'bounds': [box.xmin, box.ymin, box.zmin, box.xmax, box.ymax, box.zmax]}
    if isinstance(result, tuple) and len(result) == 2:
        return {'vertices': len(result[0]), 'triangles': len(result[1])}
    return None

module = runpy.run_path(sys.argv[2])
def module_hash(name):
    path = getattr(sys.modules.get(name), '__file__', None)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None

dependencies = {}
for name in ('cadquery-ocp', 'cadquery-ocp-proxy', 'multimethod', 'numpy', 'vtk',
             'nlopt', 'casadi', 'ezdxf'):
    try:
        dependencies[name] = version(name)
    except PackageNotFoundError:
        dependencies[name] = None

with tempfile.TemporaryDirectory() as output_dir:
    steve_root = Path(sys.argv[3]) if sys.argv[3] else None
    installed_steve = sys.argv[5] == '1'
    if installed_steve:
        # Keep fixture inputs external, but load the runtime compiled into each
        # image. Production also preimports the recorder/bindings before fork.
        installed_root = Path(output_dir) / 'installed-steve'
        installed_root.mkdir()
        (installed_root / 'runtime').symlink_to('/opt/cad', target_is_directory=True)
        (installed_root / 'app').symlink_to('/opt/cad/app', target_is_directory=True)
        (installed_root / 'examples').symlink_to(steve_root / 'examples', target_is_directory=True)
        steve_root = installed_root
    funcs = dict(module['workloads'](steve_root, output_dir))
    if installed_steve:
        from app.features import recorder, bindings
    recorder_module = sys.modules.get('app.features.recorder')
    recorder_class = getattr(recorder_module, 'Recorder', None)
    trace_file = getattr(sys.modules.get('app.features.trace'), '__file__', None)
    native_paths = ({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
                     if any(name in line for name in ('/libTKBRep-', '/libTKGeomBase-', '/libTKMath-', '/libTKBool-', '/libTKernel-', '/libTKTopAlgo-'))}
                    if Path('/proc/self/maps').is_file() else set())
    native_geometry_libraries = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                                 for path in sorted(native_paths)}
    print('BENCH' + json.dumps({'file': cq.__file__, 'python': platform.python_version(),
        'cadquery': cq.__version__, 'ocp': OCP.__version__, 'workloads': list(funcs),
        'dependencies': dependencies,
        'steve': sys.argv[3],
        'installed_steve': installed_steve,
        'steve_runtime_root': str(steve_root) if steve_root else None,
        'steve_file': getattr(sys.modules.get('steve'), '__file__', None),
        'cadquery_workplane_sha256': module_hash('cadquery.cq'),
        'cadquery_shapes_sha256': module_hash('cadquery.occ_impl.shapes'),
        'cadquery_geom_sha256': module_hash('cadquery.occ_impl.geom'),
        'cadquery_assembly_sha256': module_hash('cadquery.occ_impl.assembly'),
        'cadquery_assembly_exporter_sha256': module_hash('cadquery.occ_impl.exporters.assembly'),
        'cadquery_assembly_importer_sha256': module_hash('cadquery.occ_impl.importers.assembly'),
        'cadquery_step_materials_sha256': module_hash('cadquery.occ_impl.step_materials'),
        'steve_model_sha256': module_hash('steve.model'),
        'steve_naming_sha256': module_hash('steve.naming'),
        'steve_run_sha256': module_hash('run'),
        'steve_recorder_class': (recorder_class.__module__ + '.' + recorder_class.__qualname__)
            if recorder_class else None,
        'steve_recorder_sha256': module_hash('app.features.recorder'),
        'steve_recorder_backend_sha256': module_hash(recorder_class.__module__)
            if recorder_class else None,
        'suite_sha256': hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest(),
        'suite_timing_scope': module.get('TIMING_SCOPE', 'complete workload callable'),
        'native_preload': os.environ.get('LD_PRELOAD'),
        'native_preload_sha256': hashlib.sha256(Path(os.environ['LD_PRELOAD']).read_bytes()).hexdigest()
            if os.environ.get('LD_PRELOAD') and Path(os.environ['LD_PRELOAD']).is_file() else None,
        'native_brep_libraries': {path: digest for path, digest in native_geometry_libraries.items()
                                  if '/libTKBRep-' in path},
        'native_geometry_libraries': native_geometry_libraries,
        'trace_file': trace_file,
        'trace_sha256': hashlib.sha256(Path(trace_file).read_bytes()).hexdigest() if trace_file else None,
        'threads': OSD_ThreadPool.DefaultPool_s().NbThreads(),
        'cpu_affinity': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None}), flush=True)
    for line in sys.stdin:
        command = json.loads(line)
        forked = command.get('fork', False)
        if forked:
            child = os.fork()
            if child:
                _, status = os.waitpid(child, 0)
                if status:
                    raise RuntimeError(f'Runtime job exited with wait status {status}')
                continue
        name = command['name']
        iterations = command.get('iterations', 1)
        start = time.perf_counter()
        cpu_start = time.process_time()
        inner_elapsed = inner_cpu = 0.0
        for _ in range(iterations):
            result = funcs[name]()
            if 'TIMING_SCOPE' in module:
                timing = result['_benchmark_timing']
                inner_elapsed += timing['elapsed_s']
                inner_cpu += timing['cpu_s']
        cpu_elapsed = (time.process_time() - cpu_start) / iterations
        elapsed = (time.perf_counter() - start) / iterations
        if 'TIMING_SCOPE' in module:
            # Only an explicitly declared suite can supply a narrower timer.
            # Runtime correctness assertions and cleanup still execute, and
            # failed checks abort the comparison instead of producing a score.
            cpu_elapsed = inner_cpu / iterations
            elapsed = inner_elapsed / iterations
        response = {'elapsed_s': elapsed, 'cpu_s': cpu_elapsed}
        if isinstance(result, dict):
            response['diagnostics'] = {'stages_ms': result.get('timings_ms', {}),
                'features_ms': {f['id']: f.get('ms')
                    for f in result.get('modeling', {}).get('features', [])}}
            response['diagnostics']['steve_bytecode_caches'] = {
                name: bool(getattr(sys.modules.get(name), '__cached__', None)
                           and Path(sys.modules[name].__cached__).is_file())
                for name in ('steve.design', 'steve.simulation', 'steve.sheetmetal.geometry')
                if name in sys.modules}
        if command.get('check'):
            response['checks'] = checks(result)
        print('BENCH' + json.dumps(response), flush=True)
        if forked:
            os._exit(0)
'''


def equivalent(before, after):
    if isinstance(before, dict) and isinstance(after, dict):
        return before.keys() == after.keys() and all(equivalent(before[k], after[k]) for k in before)
    if isinstance(before, list) and isinstance(after, list):
        return len(before) == len(after) and all(equivalent(a, b) for a, b in zip(before, after))
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return math.isclose(before, after, rel_tol=1e-6, abs_tol=1e-7)
    return before == after


def receive(process):
    while line := process.stdout.readline():
        if line.startswith('BENCH'):
            return json.loads(line[5:])
    raise RuntimeError(f'Benchmark worker exited with status {process.poll()}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, default=Path('.'))
    parser.add_argument('--baseline-container', help='Docker image for the baseline worker')
    parser.add_argument('--candidate-container', help='Docker image for the candidate worker')
    parser.add_argument('--steve', type=Path)
    parser.add_argument('--baseline-steve', type=Path,
                        help='baseline Steve source root; defaults to --steve')
    parser.add_argument('--installed-steve', action='store_true',
                        help='load compiled /opt/cad runtime in both images; --steve roots supply fixtures only')
    parser.add_argument('--baseline-native-library', type=Path,
                        help='experimental native override library for the baseline (LD_PRELOAD)')
    parser.add_argument('--candidate-native-library', type=Path,
                        help='experimental native override library for the candidate (LD_PRELOAD)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', type=Path, default=Path(__file__).with_name('steve_workloads.py'))
    parser.add_argument('--only', nargs='+', help='run named cases for diagnostic comparisons')
    parser.add_argument('--repeat', type=int, default=7)
    parser.add_argument('--fork-jobs', action='store_true',
                        help='run each request in a fresh forked child, as Steve does')
    parser.add_argument('--batch-seconds', type=float, default=0.2,
                        help='batch short workloads to reduce timer/scheduling noise')
    parser.add_argument('--threads', type=int, default=1, help='OCCT threads; 0 keeps the default')
    parser.add_argument('--cpu', type=int,
                        help='pin both serial workers to this allowed Linux CPU before imports; requires --threads 1')
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error('--repeat must be positive')
    if args.batch_seconds < 0:
        parser.error('--batch-seconds must not be negative')
    if args.cpu is not None:
        if args.threads != 1:
            parser.error('--cpu requires --threads 1')
        if not hasattr(os, 'sched_getaffinity') or args.cpu not in os.sched_getaffinity(0):
            parser.error('--cpu must be in this process\'s allowed Linux CPU affinity')
    if args.fork_jobs and not hasattr(os, 'fork'):
        parser.error('--fork-jobs requires os.fork')
    if bool(args.baseline_container) != bool(args.candidate_container):
        parser.error('supply both container images for a dependency comparison')
    if args.installed_steve and not (args.baseline_container and args.steve):
        parser.error('--installed-steve requires both container images and --steve')
    if args.baseline_container and (args.baseline_native_library or args.candidate_native_library):
        parser.error('native library interposition is only supported for local workers')
    processes = {}
    containers = []
    report = {'complete': False,
              'method': 'alternating subprocesses, one warm-up per workload; median time per invocation',
              'shape_bounds_check': 'BRepBndLib.AddOptimal without triangulation or shape-tolerance inflation',
              'repeat': args.repeat, 'fork_jobs': args.fork_jobs,
              'versions': {}, 'workloads': {}}
    if args.fork_jobs:
        report['method'] = ('alternating preloaded subprocesses, fresh fork per request; '
                            'fork overhead excluded, one warm-up, median request time')
    suite = args.suite.resolve()
    try:
        for name, path in [('before', args.baseline), ('after', args.candidate)]:
            env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
            native_library = args.baseline_native_library if name == 'before' else args.candidate_native_library
            if native_library:
                env['LD_PRELOAD'] = str(native_library.resolve(strict=True))
            steve = args.baseline_steve if name == 'before' and args.baseline_steve else args.steve
            worker_args = ['-u', '-c', WORKER,
                str(path.resolve()), str(suite), str(steve.resolve()) if steve else '',
                str(args.threads), '1' if args.installed_steve else '0',
                str(args.cpu) if args.cpu is not None else '']
            image_ref = args.baseline_container if name == 'before' else args.candidate_container
            container_metadata = None
            if image_ref:
                image_id = subprocess.check_output(
                    ['docker', 'image', 'inspect', '--format', '{{.Id}}', image_ref],
                    text=True).strip()
                container_name = f'cadquery-bench-{uuid.uuid4().hex}'
                containers.append(container_name)
                command = ['docker', 'run', '--rm', '-i', '--network', 'none',
                           '--name', container_name, '--user', f'{os.getuid()}:{os.getgid()}',
                           '--workdir', '/tmp', '--entrypoint', 'python',
                           '-e', 'OPENBLAS_NUM_THREADS=1', '-e', 'OMP_NUM_THREADS=1']
                roots = {path.resolve(strict=True), suite.parent.resolve(strict=True)}
                if steve:
                    roots.add(steve.resolve(strict=True))
                for root in sorted(roots):
                    if not any(parent != root and parent in root.parents for parent in roots):
                        command += ['--mount', f'type=bind,src={root},dst={root},readonly']
                command += [image_id, *worker_args]
                container_metadata = {'image_ref': image_ref, 'image_id': image_id}
            else:
                command = [sys.executable, *worker_args]
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                text=True, env=env, cwd=tempfile.gettempdir())
            processes[name] = proc
            report['versions'][name] = receive(proc)
            if container_metadata:
                report['versions'][name]['container'] = container_metadata
        names = report['versions']['before']['workloads']
        assert names == report['versions']['after']['workloads']
        if args.only:
            unknown = set(args.only) - set(names)
            if unknown:
                parser.error(f'Unknown workloads: {sorted(unknown)}')
            names = args.only
        for name in names:
            samples = {key: [] for key in processes}
            cpu_samples = {key: [] for key in processes}
            diagnostics = {key: [] for key in processes}
            validation = {}
            warmups = []
            batch = 1
            for iteration in range(args.repeat + 1):
                order = ['before', 'after'] if iteration % 2 == 0 else ['after', 'before']
                for key in order:
                    proc = processes[key]
                    proc.stdin.write(json.dumps({'name': name, 'iterations': batch,
                                                 'fork': args.fork_jobs,
                                                 'check': not iteration}) + '\n')
                    proc.stdin.flush()
                    response = receive(proc)
                    elapsed = response['elapsed_s']
                    if iteration:
                        samples[key].append(elapsed)
                        cpu_samples[key].append(response['cpu_s'])
                        if 'diagnostics' in response:
                            diagnostics[key].append(response['diagnostics'])
                    else:
                        warmups.append(elapsed)
                        validation[key] = response['checks']
                if not iteration:
                    if not equivalent(validation['before'], validation['after']):
                        report['validation_failure'] = {'workload': name, 'checks': validation}
                        args.output.write_text(json.dumps(report, indent=2) + '\n')
                        raise AssertionError(f'{name}: geometry/results differ: {validation}')
                    batch = 1 if args.fork_jobs else max(1, min(100, math.ceil(args.batch_seconds / max(warmups))))
            medians = {key: statistics.median(values) for key, values in samples.items()}
            speedup = medians['before'] / medians['after']
            report['workloads'][name] = {'median_s': medians, 'samples_s': samples,
                                         'cpu_samples_s': cpu_samples,
                                         'median_cpu_s': {key: statistics.median(values) for key, values in cpu_samples.items()},
                                         'batch_iterations': batch, 'speedup': speedup,
                                         'checks': validation}
            if any(diagnostics.values()):
                report['workloads'][name]['diagnostics'] = diagnostics
            print(f'{name}: {medians["before"]:.4f}s -> {medians["after"]:.4f}s ({speedup:.2f}x)', flush=True)
            args.output.write_text(json.dumps(report, indent=2) + '\n')
        report['geometric_mean_speedup'] = math.exp(statistics.mean(
            math.log(value['speedup']) for value in report['workloads'].values()))
        report['complete'] = True
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    finally:
        for proc in processes.values():
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
        # Remove only containers created by this invocation, including native
        # jobs that remain alive after their Docker client exits or is interrupted.
        for container in containers:
            subprocess.run(['docker', 'rm', '-f', container],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=30)
        for proc in processes.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait()


if __name__ == '__main__':
    main()
