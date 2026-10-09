"""Validate every Steve case in its own process; retain failures and timeouts.

Run inside Steve's geometry image. These cold-process durations are validation
timings, not comparable with compare.py's warmed performance measurements.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steve', type=Path, required=True)
    parser.add_argument('--cadquery', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--only', nargs='+')
    parser.add_argument('--worker')
    parser.add_argument('--audit-artifacts', action='store_true',
                        help='Inspect generated STEP/STL archive contents before temporary files are removed')
    args = parser.parse_args()
    if args.cadquery:
        sys.path.insert(0, str(args.cadquery))
    import steve_runtime_workloads as suite
    if args.worker:
        import cadquery as cq
        from cadquery.func import setThreads
        setThreads(1)
        with tempfile.TemporaryDirectory() as directory:
            funcs = dict(suite.workloads(args.steve, directory))
            artifact_audits = []
            if args.audit_artifacts:
                from app.features import runtime as feature_runtime
                from audit_export_artifacts import audit
                original_request = feature_runtime.run_request

                def audited_request(request):
                    result = original_request(request)
                    artifact_audits.append(audit(result['metadata'], request.get('mode', 'full')))
                    return result

                feature_runtime.run_request = audited_request
            metadata = funcs[args.worker]()
            summary = {key: metadata[key] for key in
                       ('components', 'solids', 'faces', 'bounds_mm', 'volume_mm3', 'timings_ms')
                       if key in metadata}
            summary['history_equivalence'] = metadata.get('feature_tree', {}).get('equivalence')
            if args.audit_artifacts:
                assert len(artifact_audits) == 1
                summary['artifact_audit'] = artifact_audits[0]
            summary['cadquery_file'] = cq.__file__
            summary['cadquery_shapes_sha256'] = hashlib.sha256(Path(sys.modules['cadquery.occ_impl.shapes'].__file__).read_bytes()).hexdigest()
            summary['cadquery_geom_sha256'] = hashlib.sha256(Path(sys.modules['cadquery.occ_impl.geom'].__file__).read_bytes()).hexdigest()
            summary['cadquery_assembly_sha256'] = hashlib.sha256(Path(sys.modules['cadquery.occ_impl.assembly'].__file__).read_bytes()).hexdigest()
            summary['cadquery_assembly_exporter_sha256'] = hashlib.sha256(Path(sys.modules['cadquery.occ_impl.exporters.assembly'].__file__).read_bytes()).hexdigest()
            for module, key in (
                ('cadquery.occ_impl.importers.assembly', 'cadquery_assembly_importer_sha256'),
                ('cadquery.occ_impl.step_materials', 'cadquery_step_materials_sha256'),
            ):
                summary[key] = (
                    hashlib.sha256(Path(sys.modules[module].__file__).read_bytes()).hexdigest()
                    if module in sys.modules else None
                )
            summary['native_preload'] = os.environ.get('LD_PRELOAD')
            summary['native_preload_sha256'] = (
                hashlib.sha256(Path(summary['native_preload']).read_bytes()).hexdigest()
                if summary['native_preload'] and Path(summary['native_preload']).is_file()
                else None
            )
            # Toolkit replacements keep the same package version and filename.
            # Record the actual loaded native library, not just the wheel tag.
            native_paths = {line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
                            if any(name in line for name in ('/libTKBRep-', '/libTKGeomBase-', '/libTKMath-', '/libTKBool-', '/libTKernel-', '/libTKTopAlgo-'))}
            summary['native_geometry_libraries'] = {
                path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                for path in sorted(native_paths)
            }
            summary['native_brep_libraries'] = {
                path: digest for path, digest in summary['native_geometry_libraries'].items()
                if '/libTKBRep-' in path
            }
            summary['trace_file'] = sys.modules['app.features.trace'].__file__
            summary['steve_file'] = sys.modules['steve'].__file__
            summary['steve_model_file'] = sys.modules['steve.model'].__file__
            summary['steve_model_sha256'] = hashlib.sha256(Path(summary['steve_model_file']).read_bytes()).hexdigest()
            summary['steve_naming_sha256'] = hashlib.sha256(Path(sys.modules['steve.naming'].__file__).read_bytes()).hexdigest()
            summary['steve_run_sha256'] = hashlib.sha256(Path(sys.modules['run'].__file__).read_bytes()).hexdigest()
            summary['trace_sha256'] = hashlib.sha256(Path(summary['trace_file']).read_bytes()).hexdigest()
            request = dict(suite.models(args.steve))[args.worker.rsplit('_', 1)[0]]
            summary['source_sha256'] = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
            print('VALIDATED' + json.dumps(summary), flush=True)
        return
    if not args.output:
        parser.error('--output is required')
    names = [name + '_' + mode for name, _ in suite.models(args.steve)
             for mode in ('preview', 'full')]
    if args.only:
        unknown = set(args.only) - set(names)
        if unknown:
            parser.error(f'Unknown cases: {sorted(unknown)}')
        names = args.only
    report = {'complete': False, 'method': 'one fresh process per case, one validation run',
              'timeout_s': args.timeout, 'cases': {}}
    for name in names:
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', name,
                   '--steve', str(args.steve)]
        if args.cadquery:
            command += ['--cadquery', str(args.cadquery)]
        if args.audit_artifacts:
            command += ['--audit-artifacts']
        start = time.monotonic()
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
            lines = [line[9:] for line in process.stdout.splitlines() if line.startswith('VALIDATED')]
            result = {'passed': process.returncode == 0 and bool(lines),
                      'returncode': process.returncode}
            if result['passed']:
                result['geometry'] = json.loads(lines[-1])
            else:
                result['error'] = (process.stdout + process.stderr)[-12000:]
        except subprocess.TimeoutExpired:
            result = {'passed': False, 'error': 'process timeout'}
        result['cold_process_s'] = time.monotonic() - start
        report['cases'][name] = result
        print(f'{name}: {"PASS" if result["passed"] else "FAIL"} ({result["cold_process_s"]:.2f}s)', flush=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    report['complete'] = True
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    if any(not result['passed'] for result in report['cases'].values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
