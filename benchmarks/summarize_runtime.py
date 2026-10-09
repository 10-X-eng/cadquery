"""Summarize a complete, geometry-checked preview/full request comparison."""
import argparse
import json
from pathlib import Path
import statistics

from compare import equivalent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="Output path prefix")
    parser.add_argument("--reference-speedup", type=float,
                        help="Previously demonstrated speedup to retain")
    args = parser.parse_args()
    report = json.loads(args.input.read_text())
    cases = report["workloads"]
    if not report["complete"] or "validation_failure" in report:
        parser.error("Refusing to summarize an incomplete or failed comparison")
    expected = set(report["versions"]["before"]["workloads"])
    if expected != set(cases) or expected != set(report["versions"]["after"]["workloads"]):
        parser.error("Both versions must cover the complete declared workload set")
    if any(not equivalent(case["checks"]["before"], case["checks"]["after"]) for case in cases.values()):
        parser.error("Geometry checks do not match")
    models = list(dict.fromkeys(name.rsplit("_", 1)[0] for name in cases))
    if any(f"{name}_{mode}" not in cases for name in models for mode in ("preview", "full")):
        parser.error("Every model must have both preview and full requests")
    timing_scopes = {version.get("suite_timing_scope", "complete workload callable")
                     for version in report["versions"].values()}
    installed_modes = {version.get("installed_steve", False)
                       for version in report["versions"].values()}
    if len(timing_scopes) != 1 or len(installed_modes) != 1:
        parser.error("Both versions must use the same timing and runtime-loading method")

    def aggregate(selected):
        totals = {side: sum(case["median_s"][side] for case in selected) for side in ("before", "after")}
        return {
            "cases": len(selected),
            "geometric_mean_speedup": statistics.geometric_mean(case["speedup"] for case in selected),
            "sum_of_medians_s": totals,
            "ratio_of_summed_medians": totals["before"] / totals["after"],
        }

    result = {
        "source": str(args.input), "repeat": report["repeat"],
        "reference_speedup": args.reference_speedup,
        "fork_jobs": report["fork_jobs"], "all_geometry_checks_match": True,
        "timing_scope": timing_scopes.pop(), "installed_steve": installed_modes.pop(),
        "overall": aggregate(list(cases.values())),
        **{mode: aggregate([cases[f"{name}_{mode}"] for name in models]) for mode in ("preview", "full")},
        "slower_medians": [name for name, case in cases.items() if case["speedup"] < 1],
        "models": {
            name: {mode: {"median_s": cases[f"{name}_{mode}"]["median_s"],
                          "speedup": cases[f"{name}_{mode}"]["speedup"]}
                   for mode in ("preview", "full")}
            for name in models
        },
    }
    args.output.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "Complete Steve runtime comparison", "=================================", "",
        f"All {len(cases)} request checks match. Each version has {report['repeat']} alternating samples",
        "per case, plus warm-up, using a fresh forked child for each request.", "",
        f"Timing scope: ``{result['timing_scope']}``.",
        f"Installed compiled Steve runtime: {'yes' if result['installed_steve'] else 'no'}.", "",
        f"Overall geometric mean: **{result['overall']['geometric_mean_speedup']:.3f}x**.",
        f"Preview: **{result['preview']['geometric_mean_speedup']:.3f}x**; full builds:",
        f"**{result['full']['geometric_mean_speedup']:.3f}x**. " +
        (f"The reference to preserve is approximately {args.reference_speedup:g}x."
         if args.reference_speedup else "The 2x target is not established."), "",
        "These are full request timings. The fixed library score is separate.",
        "Medians below 1x remain in the results. Small sample counts do not establish",
        "that a small difference is significant. Summing medians weights slow",
        "cases more heavily and must not replace the geometric mean.", "",
        ".. list-table:: Median request durations in seconds", "   :header-rows: 1", "",
        "   * - Model", "     - Preview before", "     - Preview after", "     - Speedup",
        "     - Full before", "     - Full after", "     - Speedup",
    ]
    for name in models:
        lines.append(f"   * - {name}")
        for mode in ("preview", "full"):
            case = cases[f"{name}_{mode}"]
            lines += [f"     - {case['median_s']['before']:.3f}",
                      f"     - {case['median_s']['after']:.3f}",
                      f"     - {case['speedup']:.3f}x"]
    args.output.with_suffix(".rst").write_text("\n".join(lines) + "\n")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 11))
    for mode, shift, color in (("preview", -.18, "#3a78ad"), ("full", .18, "#258873")):
        values = [cases[f"{name}_{mode}"]["speedup"] for name in models]
        bars = ax.barh([i + shift for i in range(len(models))], values, height=.32, label=mode.title(), color=color)
        ax.bar_label(bars, labels=[f"{value:.2f}×" for value in values], padding=3, fontsize=7)
    ax.set_yticks(range(len(models)), [name.removeprefix("modeling_").replace("_", " ") for name in models])
    ax.invert_yaxis()
    ax.axvline(1, color="#777777", linewidth=1)
    reference = args.reference_speedup or 2
    label = f"Previous {reference:g}× result" if args.reference_speedup else "2× target"
    ax.axvline(reference, color="#ab672b", linestyle="--", linewidth=1, label=label)
    ax.set_xlim(0, max(case["speedup"] for case in cases.values()) * 1.12)
    ax.set_xlabel("Speedup: original median / candidate median")
    ax.set_title(f"Steve: all {len(cases)} preview/full requests\nOverall {result['overall']['geometric_mean_speedup']:.3f}× geometric mean")
    ax.legend(loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(args.output.with_suffix(".png"), dpi=160)
    plt.close(fig)
    print(json.dumps({key: result[key] for key in ("overall", "preview", "full", "slower_medians")}, indent=2))


if __name__ == "__main__":
    main()
