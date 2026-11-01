"""Reanalyse sourced teaching cases and run the actual workflow, honestly recording pauses.

Default mode is offline mock. Only --noninteractive-benchmark can approve an
exact predefined analysis plan; it never answers data verification requests.
An independent numerical reference is reported separately from workflow success.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import platform
import uuid

import numpy as np
import scipy
from scipy import stats

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "examples" / "public_reproductions"


def load_manifest(root=FIXTURES):
    return json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_fixtures(root=FIXTURES, manifest=None):
    root = Path(root)
    manifest = manifest if manifest is not None else load_manifest(root)
    failures = []
    for source in manifest["sources"]:
        if file_hash(root / source["file"]) != source["sha256"]:
            failures.append("Source hash mismatch: " + source["file"])
    for case in manifest["cases"]:
        if file_hash(root / case["data_file"]) != case["data_sha256"]:
            failures.append("Data hash mismatch: " + case["data_file"])
        if file_hash(root / case["source_file"]) != case["source_sha256"]:
            failures.append("Case source hash mismatch: " + case["source_file"])
    counts = read_csv(root / "berkeley_counts.csv")
    expanded = read_csv(root / "berkeley_frequency_expanded.csv")
    expected = Counter({(r["department"], r["sex"], r["admission"]): int(r["count"]) for r in counts})
    actual = Counter((r["department"], r["sex"], r["admission"]) for r in expanded)
    if len(counts) != 24 or sum(expected.values()) != 4526 or expected != actual:
        failures.append("Berkeley count table and deterministic expansion disagree.")
    ids = [r["derived_record_id"] for r in expanded]
    if len(set(ids)) != 4526 or not all(v.startswith("derived_") for v in ids):
        failures.append("Frequency-expanded identifiers must be unique and explicitly derived.")
    if failures:
        raise ValueError(" ".join(failures))
    return manifest


def department_rates(root=FIXTURES):
    grouped = {}
    for row in read_csv(Path(root) / "berkeley_counts.csv"):
        key = (row["department"], row["sex"])
        target = grouped.setdefault(key, {"department": key[0], "sex": key[1], "admitted": 0, "applicants": 0})
        target["applicants"] += int(row["count"])
        if row["admission"] == "Admitted":
            target["admitted"] += int(row["count"])
    return [{**r, "admission_rate": r["admitted"] / r["applicants"]} for _, r in sorted(grouped.items())]


def quartet_descriptive_summaries(root=FIXTURES):
    """Four descriptive fits for plotting, never four inferential workflow runs."""
    rows = read_csv(Path(root) / "anscombe_quartet.csv")
    summaries = []
    for i in range(1, 5):
        x = np.array([float(r[f"x{i}"]) for r in rows])
        y = np.array([float(r[f"y{i}"]) for r in rows])
        xc, yc = x - x.mean(), y - y.mean()
        slope = float(xc @ yc / (xc @ xc))
        intercept = float(y.mean() - slope * x.mean())
        r = float(xc @ yc / np.sqrt((xc @ xc) * (yc @ yc)))
        summaries.append({"dataset": i, "n": len(rows), "mean_x": float(x.mean()), "mean_y": float(y.mean()),
                          "sd_x": float(x.std(ddof=1)), "sd_y": float(y.std(ddof=1)),
                          "slope": slope, "intercept": intercept, "r": r, "r_squared": r * r})
    return summaries


def numerical_reference(case, root=FIXTURES):
    """Independent explicit oracle; never calls application statistical tools or agents."""
    root = Path(root)
    if case["id"] == "student_sleep":
        rows = read_csv(root / case["data_file"])
        x = np.array([float(r["drug_1"]) for r in rows])
        y = np.array([float(r["drug_2"]) for r in rows])
        differences = y - x
        n = len(differences)
        mean = float(np.mean(differences))
        se = float(np.std(differences, ddof=1) / math.sqrt(n))
        t = mean / se
        half = float(stats.t.ppf(.975, n - 1) * se)
        return {"n": n, "n_pairs": n, "mean_difference": mean, "t_statistic": t, "df": n - 1,
                "p_value": float(2 * stats.t.sf(abs(t), n - 1)), "ci_lower": mean - half, "ci_upper": mean + half}
    if case["id"] == "anscombe_quartet":
        rows = read_csv(root / case["data_file"])
        x = np.array([float(r["x1"]) for r in rows])
        y = np.array([float(r["y1"]) for r in rows])
        xc, yc = x - x.mean(), y - y.mean()
        slope = float(xc @ yc / (xc @ xc))
        intercept = float(y.mean() - slope * x.mean())
        residuals = y - (intercept + slope * x)
        df = len(rows) - 2
        sse = float(residuals @ residuals)
        se = math.sqrt(sse / df / float(xc @ xc))
        t = slope / se
        half = float(stats.t.ppf(.975, df) * se)
        return {"n": len(rows), "slope": slope, "intercept": intercept,
                "r_squared": 1 - sse / float(yc @ yc), "t_statistic": t, "df": df,
                "p_value": float(2 * stats.t.sf(abs(t), df)), "ci_lower": slope - half, "ci_upper": slope + half}
    # Build the original grouped table directly, without using the expanded CSV.
    cells = {(r["sex"], r["admission"]): 0 for r in read_csv(root / case["count_file"])}
    for row in read_csv(root / case["count_file"]):
        cells[row["sex"], row["admission"]] += int(row["count"])
    table = np.array([[cells[sex, admission] for admission in ("Admitted", "Rejected")]
                      for sex in ("Male", "Female")], dtype=float)
    n = int(np.sum(table))
    expected = table.sum(axis=1)[:, None] * table.sum(axis=0)[None, :] / n
    chi = float(np.sum((table - expected) ** 2 / expected))
    return {"n": n, "chi_square": chi, "df": 1, "p_value": float(stats.chi2.sf(chi, 1)),
            "cramers_v": math.sqrt(chi / n)}


def compare(expected, calculated, tolerance):
    checks = {}
    for key, value in expected.items():
        actual = calculated.get(key)
        absolute = tolerance.get("p_value_atol", 1e-30) if key == "p_value" else tolerance["atol"]
        checks[key] = {"expected": value, "calculated": actual, "rtol": tolerance["rtol"], "atol": absolute,
                       "passed": isinstance(actual, (int, float)) and not isinstance(actual, bool)
                       and math.isclose(actual, value, rel_tol=tolerance["rtol"], abs_tol=absolute)}
    return {"status": "passed" if all(v["passed"] for v in checks.values()) else "failed", "checks": checks}


def tool_request(case, root=FIXTURES):
    root = Path(root)
    design = json.loads((root / case["design_file"]).read_text(encoding="utf-8"))
    return {"data_path": str(root / case["data_file"]), "data_version": case.get("fixture_version") or load_manifest(root)["fixture_version"],
            "method": case["method"], "roles": case["roles"], "id_column": design["id_column"],
            "valid_levels": {k: v["levels"] for k, v in design["variables"].items() if "levels" in v},
            "valid_ranges": {}, "excluded_ids": [], "alpha": .05, "conf_level": .95}


def _dump(path, payload):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False, default=str)
        stream.write("\n")


def _interrupt_payload(state):
    items = state.get("__interrupt__") or []
    return [item.value if hasattr(item, "value") else item for item in items]


def run_workflow(case, mode, benchmark, root=FIXTURES):
    from stat_assistant.models import create_agents, resolve_configuration
    from stat_assistant.runtime import new_run, resume_plan
    from stat_assistant.workflow import build_graph

    configuration = {"mode": "mock"} if mode == "mock" else {**resolve_configuration(), "mode": "real"}
    a, b, resolved = create_agents(configuration)
    graph = build_graph(a, b, mode=mode)
    design = json.loads((Path(root) / case["design_file"]).read_text(encoding="utf-8"))
    state = new_run(graph, Path(root) / case["data_file"], case["question"], design,
                    require_plan_confirmation=True)
    decisions = []
    payloads = _interrupt_payload(state)
    # This policy is solely a benchmark setup operation. It cannot verify, edit,
    # exclude, impute, or choose another scientific question on a user's behalf.
    if benchmark and len(payloads) == 1 and payloads[0].get("kind") == "plan_approval":
        pending = payloads[0]
        plan = pending["plan"]
        matches = plan.get("method") == case["method"] and all(
            plan.get(role) == column for role, column in case["roles"].items())
        if matches:
            decision = {"action": "approve", "plan_id": pending["plan_id"]}
            decisions.append({"policy": "benchmark_predefined_plan", "source": "explicit --noninteractive-benchmark",
                              "human_approval": False, "decision": decision,
                              "note": "Only the fixture's predefined method and variable roles were approved; no data verification was supplied."})
            state = resume_plan(graph, state["run_id"], decision)
            payloads = _interrupt_payload(state)
        else:
            decisions.append({"policy": "benchmark_predefined_plan", "action": "left_paused",
                              "reason": "The proposed method or variable roles differ from the predefined benchmark task."})
    return {"mode": mode, "agents_are_llms": mode == "real", "configuration": resolved,
            "status": "paused" if payloads else state.get("final_status", "unknown"),
            "final_status": state.get("final_status"), "run_id": state.get("run_id"),
            "interrupts": payloads, "benchmark_decisions": decisions,
            "analysis_plan": state.get("analysis_plan"), "plan_approval": state.get("plan_approval"),
            "retrieved_references": state.get("retrieved_references", []), "stat_result": state.get("stat_result"),
            "program_check": state.get("program_check"), "review_verdict": state.get("review_verdict"),
            "final_report": state.get("final_report", ""), "errors": state.get("errors", []),
            "stop_reasons": state.get("stop_reasons", []), "trace": state.get("trace", []),
            "model_calls": state.get("model_calls", []), "correction_log": state.get("correction_log", [])}


def create_plots(output, root=FIXTURES):
    """Create standalone SVGs and, when matplotlib is available, classroom PNGs."""
    output, root = Path(output), Path(root)
    def start(title, description, height=440):
        return [f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}" role="img" aria-labelledby="title desc">',
                f'<title id="title">{html.escape(title)}</title><desc id="desc">{html.escape(description)}</desc>',
                '<rect width="100%" height="100%" fill="#fafafa"/>',
                '<style>text{font-family:Arial,sans-serif;fill:#172536}.title{font-size:23px;font-weight:bold}.label{font-size:16px}.small{font-size:13px}</style>',
                f'<text class="title" x="35" y="36">{html.escape(title)}</text>']
    parts = start("The same ten patients received both drugs", "Lines join each patient's additional hours of sleep under the two drugs. The mean drug two minus drug one difference is 1.58 hours.")
    ycoord = lambda value: 340 - (value + 2) / 8 * 255
    for tick in range(-2, 7, 2):
        y = ycoord(tick)
        parts += [f'<line x1="100" y1="{y}" x2="650" y2="{y}" stroke="#dce1e7"/>',
                  f'<text class="small" x="65" y="{y + 4}">{tick}</text>']
    for row in read_csv(root / "student_sleep.csv"):
        y1, y2 = ycoord(float(row["drug_1"])), ycoord(float(row["drug_2"]))
        parts += [f'<line x1="200" y1="{y1}" x2="550" y2="{y2}" stroke="#557388" stroke-opacity=".60" stroke-width="2"/>',
                  f'<circle cx="200" cy="{y1}" r="5" fill="#26738b"/><circle cx="550" cy="{y2}" r="5" fill="#b24b35"/>']
    parts += ['<text class="label" x="160" y="372">Drug one</text><text class="label" x="510" y="372">Drug two</text>',
              '<text class="label" transform="translate(28,300) rotate(-90)">Additional hours of sleep</text>',
              '<text class="label" x="690" y="150">Mean paired difference</text><text x="690" y="188" font-size="32" fill="#b24b35">+1.58 hours</text>',
              '<text class="small" x="690" y="219">95% CI: +0.70 to +2.46</text>',
              '<text class="small" x="35" y="414">Source: R datasets::sleep; Student (1908). Modern paired reanalysis; no randomization claim.</text></svg>']
    (output / "student_sleep.svg").write_text("\n".join(parts), encoding="utf-8")
    rates = {(r["department"], r["sex"]): r["admission_rate"] for r in department_rates(root)}
    parts = start("Berkeley: the pooled gap changes when departments are shown", "Admission rates for men and women in the six largest departments, followed by their pooled rates. This is grouped historical data and does not establish discrimination.", 470)
    pool = {"Male": 1198 / 2691, "Female": 557 / 1835}
    for tick in range(0, 101, 20):
        y = 350 - tick * 2.5
        parts += [f'<line x1="75" y1="{y}" x2="920" y2="{y}" stroke="#dce1e7"/>',
                  f'<text class="small" x="30" y="{y + 4}">{tick}%</text>']
    for i, dept in enumerate([*"ABCDEF", "Pooled"]):
        center = 130 + i * 120
        if dept == "Pooled":
            parts.append('<rect x="800" y="82" width="115" height="270" fill="#edf0f4"/>')
        for sex, delta, color in (("Male", -23, "#26738b"), ("Female", 5, "#b24b35")):
            rate = pool[sex] if dept == "Pooled" else rates[dept, sex]
            height = 250 * rate
            parts += [f'<rect x="{center + delta}" y="{350 - height}" width="25" height="{height}" fill="{color}"/>',
                      f'<text class="small" text-anchor="middle" x="{center + delta + 12.5}" y="{342 - height}">{100 * rate:.1f}</text>']
        parts.append(f'<text class="label" text-anchor="middle" x="{center + 2}" y="379">{dept}</text>')
    parts += ['<rect x="650" y="54" width="14" height="14" fill="#26738b"/><text class="small" x="670" y="66">Male</text>',
              '<rect x="750" y="54" width="14" height="14" fill="#b24b35"/><text class="small" x="770" y="66">Female</text>',
              '<text class="small" x="35" y="418">Six departments only, 1973: aggregate counts, n = 4,526. Higher female rates in four departments; lower in two.</text>',
              '<text class="small" x="35" y="443">Source: R datasets::UCBAdmissions; Bickel, Hammel and O’Connell (1975). Rates are descriptive.</text></svg>']
    (output / "berkeley_admissions.svg").write_text("\n".join(parts), encoding="utf-8")
    if (root / "anscombe_quartet.csv").exists():
        create_anscombe_plots(output, root)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import PercentFormatter
    except ImportError:
        return
    plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "axes.labelcolor": "#172536", "text.color": "#172536"})
    blue, orange = "#26738b", "#b24b35"
    fig, axis = plt.subplots(figsize=(10, 5.6), layout="constrained")
    for row in read_csv(root / "student_sleep.csv"):
        vals = [float(row["drug_1"]), float(row["drug_2"])]
        axis.plot([0, 1], vals, color="#71879a", alpha=.6, linewidth=1.5, zorder=1)
        axis.scatter([0, 1], vals, color=[blue, orange], s=40, zorder=2)
    axis.set(xticks=[0, 1], xticklabels=["Drug one", "Drug two"], xlim=(-.35, 1.9),
             ylim=(-2.1, 6.2), ylabel="Additional hours of sleep versus control",
             title="The same ten patients received both drugs\n")
    axis.grid(axis="y", color="#e2e7ec")
    axis.text(1.18, 3.5, "Mean paired difference\n+1.58 hours", fontsize=17, weight="bold", color=orange)
    axis.text(1.18, 2.1, "Drug two minus drug one\n95% CI: +0.70 to +2.46 hours", fontsize=11)
    fig.supxlabel("R datasets::sleep; Student (1908). Modern paired reanalysis; no randomization claim.", fontsize=9)
    fig.savefig(output / "student_sleep.png", dpi=180, facecolor="white")
    plt.close(fig)
    fig, axis = plt.subplots(figsize=(11.5, 5.8), layout="constrained")
    labels = [*"ABCDEF", "Pooled"]
    positions = np.arange(len(labels))
    axis.axvspan(5.55, 6.5, color="#eef1f5", zorder=0)
    for sex, offset, color in (("Male", -.18, blue), ("Female", .18, orange)):
        values = [rates[d, sex] for d in "ABCDEF"] + [pool[sex]]
        bars = axis.bar(positions + offset, values, width=.32, color=color, label=sex, zorder=2)
        axis.bar_label(bars, labels=[f"{100 * v:.1f}%" for v in values], padding=4, fontsize=9)
    axis.set(xticks=positions, xticklabels=labels, ylim=(0, 1.0), ylabel="Admitted / applicants",
             title="Berkeley: the pooled gap changes when departments are shown\n")
    axis.yaxis.set_major_formatter(PercentFormatter(1))
    axis.grid(axis="y", color="#e2e7ec", zorder=1)
    axis.legend(frameon=False, loc="upper right", ncol=2)
    fig.supxlabel("R datasets::UCBAdmissions; 1973, six departments, n = 4,526. Rates are descriptive; grouped counts do not establish discrimination.", fontsize=9)
    fig.savefig(output / "berkeley_admissions.png", dpi=180, facecolor="white")
    plt.close(fig)


def create_anscombe_plots(output, root=FIXTURES):
    """Draw all four constructed datasets with their own fitted lines and common axes."""
    output, root = Path(output), Path(root)
    if any((output / ("anscombe_quartet." + extension)).exists() for extension in ("svg", "png")):
        raise ValueError("Refusing to overwrite an existing Anscombe plot.")
    rows = read_csv(root / "anscombe_quartet.csv")
    summaries = quartet_descriptive_summaries(root)
    labels = ["I: roughly linear scatter", "II: a curved pattern", "III: an unusual y value", "IV: one distant x value"]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1060" height="880" viewBox="0 0 1060 880" role="img" aria-labelledby="title desc">',
             '<title id="title">Anscombe’s quartet: similar summaries, different plots</title>',
             '<desc id="desc">Four published constructed datasets, each with eleven pairs and its own fitted line. Similar regression summaries conceal different patterns. Only the first pair of variables is a workflow target.</desc>',
             '<rect width="1060" height="880" fill="#fafafa"/>',
             '<style>text{font-family:Arial,sans-serif;fill:#172536}.title{font-size:25px;font-weight:bold}.panel{font-size:17px;font-weight:bold}.small{font-size:13px}</style>',
             '<text class="title" x="35" y="38">Anscombe’s quartet: similar summaries, different plots</text>',
             '<text class="small" x="35" y="65">Published pedagogically constructed data, not empirical observations. Each orange line is fitted separately.</text>']
    for j, summary in enumerate(summaries):
        i = j + 1
        left, top = 55 + 510 * (j % 2), 95 + 355 * (j // 2)
        px = lambda value: left + 40 + (value - 2) / 18 * 410
        py = lambda value: top + 300 - (value - 2) / 12 * 230
        parts += [f'<text class="panel" x="{left}" y="{top + 18}">{html.escape(labels[j])}</text>',
                  f'<text class="small" x="{left}" y="{top + 40}">y = {summary["intercept"]:.4f} + {summary["slope"]:.4f}x; R² = {summary["r_squared"]:.4f}</text>']
        for value in (4, 8, 12):
            parts += [f'<line x1="{px(2)}" y1="{py(value)}" x2="{px(20)}" y2="{py(value)}" stroke="#dce1e7"/>',
                      f'<text class="small" text-anchor="end" x="{px(2) - 8}" y="{py(value) + 4}">{value}</text>']
        for value in (4, 8, 12, 16, 20):
            parts.append(f'<text class="small" text-anchor="middle" x="{px(value)}" y="{top + 319}">{value}</text>')
        parts += [f'<line x1="{px(2)}" y1="{py(2)}" x2="{px(20)}" y2="{py(2)}" stroke="#607080"/>',
                  f'<line x1="{px(2)}" y1="{py(2)}" x2="{px(2)}" y2="{py(14)}" stroke="#607080"/>',
                  f'<line x1="{px(2)}" y1="{py(summary["intercept"] + 2 * summary["slope"])}" x2="{px(20)}" y2="{py(summary["intercept"] + 20 * summary["slope"])}" stroke="#b24b35" stroke-width="2.3"/>']
        for row in rows:
            parts.append(f'<circle cx="{px(float(row[f"x{i}"]))}" cy="{py(float(row[f"y{i}"]))}" r="5" fill="#26738b"/>')
        parts += [f'<text class="small" text-anchor="middle" x="{px(11)}" y="{top + 340}">x{i}</text>',
                  f'<text class="small" x="{left}" y="{top + 67}">y{i}</text>']
    parts += ['<text class="small" x="35" y="838">One approved workflow target: x1 → y1. The four-panel comparison is descriptive; unrounded statistics are nearly identical.</text>',
              '<text class="small" x="35" y="862">Source: R datasets::anscombe; Anscombe (1973), Graphs in Statistical Analysis.</text></svg>']
    with (output / "anscombe_quartet.svg").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(parts))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, axes = plt.subplots(2, 2, figsize=(11.4, 8.6), sharex=True, sharey=True, layout="constrained")
    for j, axis in enumerate(axes.flat):
        i, summary = j + 1, summaries[j]
        x = [float(r[f"x{i}"]) for r in rows]
        y = [float(r[f"y{i}"]) for r in rows]
        axis.scatter(x, y, s=45, color="#26738b", zorder=3)
        axis.plot([2, 20], [summary["intercept"] + summary["slope"] * value for value in (2, 20)],
                  color="#b24b35", linewidth=1.7, zorder=2)
        axis.set(xlim=(2, 20), ylim=(2, 14), xlabel=f"x{i}", ylabel=f"y{i}",
                 title=f"{labels[j]}\ny = {summary['intercept']:.4f} + {summary['slope']:.4f}x; R² = {summary['r_squared']:.4f}")
        axis.grid(color="#e2e7ec", zorder=1)
        axis.spines[["top", "right"]].set_visible(False)
        axis.set_title(axis.get_title(), fontsize=11)
    fig.suptitle("Anscombe’s quartet: similar summaries, different plots\nPublished constructed values, not empirical observations", fontsize=16, weight="bold")
    fig.supxlabel("R datasets::anscombe; Anscombe (1973). Separate fitted lines; descriptive comparison only. Workflow target: x1 → y1.", fontsize=9)
    fig.savefig(output / "anscombe_quartet.png", dpi=180, facecolor="white")
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--noninteractive-benchmark", action="store_true",
                        help="Approve only exact predefined fixture plans, logging benchmark_predefined_plan. Never answer data verification.")
    parser.add_argument("--case", choices=("student_sleep", "berkeley_admissions", "anscombe_quartet", "all"), default="all")
    parser.add_argument("--output", type=Path, help="New output directory; existing paths are never overwritten.")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output or ROOT / "artifacts" / "public_reproductions" / f"{stamp}_{uuid.uuid4().hex[:8]}").resolve()
    if output.exists():
        parser.error("--output must be a new directory; existing evidence is never overwritten.")
    manifest_bytes_at_start = (FIXTURES / "manifest.json").read_bytes()
    manifest_hash_at_start = hashlib.sha256(manifest_bytes_at_start).hexdigest()
    manifest = verify_fixtures(manifest=json.loads(manifest_bytes_at_start))
    output.mkdir(parents=True, exist_ok=False)
    from stat_assistant import settings
    from stat_assistant.tool_bridge import run_stat_tool
    settings.OUTPUT_DIR = output / "runtime"
    reports = []
    for case in manifest["cases"]:
        if args.case != "all" and case["id"] != args.case:
            continue
        independent = numerical_reference(case)
        oracle = {"calculation": "Independent explicit oracle; no application compute function or LLM",
                  "source_version": manifest["fixture_version"], "source_sha256": case["source_sha256"],
                  "expected": case["reference"], "calculated": independent, "tolerance": case["tolerance"],
                  **compare(case["reference"], independent, case["tolerance"])}
        tool_result = run_stat_tool("run_test", tool_request(case), "public-reference-" + case["id"])
        tool_check = compare(case["reference"], tool_result, case["tolerance"]) if tool_result.get("status") == "ok" else {"status": "not_computed"}
        try:
            workflow = run_workflow(case, args.mode, args.noninteractive_benchmark)
        except Exception as error:
            workflow = {"mode": args.mode, "agents_are_llms": args.mode == "real", "status": "error",
                        "error": f"{type(error).__name__}: {error}", "benchmark_decisions": []}
        if (workflow.get("stat_result") or {}).get("status") == "ok":
            workflow["numeric_comparison"] = compare(case["reference"], workflow["stat_result"], case["tolerance"])
        report = {"case_id": case["id"], "source": {k: case[k] for k in (
            "source_name", "source_url", "source_sha256", "data_sha256", "documentation_url", "citation", "paper_doi")},
                  "source_version": manifest["fixture_version"], "question": case["question"],
                  "data_kind": case.get("data_kind", "historical_observations"),
                  "scope": {"supports": case["claim_supported"], "does_not_support": case["claim_not_supported"]},
                  "independent_reference": oracle,
                  "numerical_tool_reference": {"status": tool_result.get("status"), "comparison": tool_check, "result": tool_result,
                                               "note": "Read-only numerical reference call; does not approve the workflow's pending data checks."},
                  "workflow": workflow}
        if case["id"] == "berkeley_admissions":
            report["department_descriptive_rates"] = department_rates()
        if case["id"] == "anscombe_quartet":
            report["quartet_descriptive_summaries"] = quartet_descriptive_summaries()
        _dump(output / (case["id"] + ".json"), report)
        reports.append(report)
    create_plots(output)
    summary = {"schema_version": 1, "run_id": output.name, "created_utc": datetime.now(timezone.utc).isoformat(),
               "fixture_version": manifest["fixture_version"], "source_manifest_sha256": manifest_hash_at_start,
               "software": {"python": platform.python_version(), "scipy": scipy.__version__},
               "mode": args.mode, "noninteractive_benchmark": args.noninteractive_benchmark,
               "mock_note": "Mock uses deterministic agent stand-ins and real statistical tools; it is not evidence of real-model performance." if args.mode == "mock" else None,
               "cases": [{"id": r["case_id"], "independent_reference_status": r["independent_reference"]["status"],
                          "numerical_tool_status": r["numerical_tool_reference"]["status"],
                          "numerical_tool_comparison": r["numerical_tool_reference"]["comparison"]["status"],
                          "workflow_status": r["workflow"]["status"], "report_file": r["case_id"] + ".json"} for r in reports],
               "note": "Numerical correctness, workflow delivery, and real-model performance are separate outcomes. A pause is not a delivered analysis."}
    _dump(output / "summary.json", summary)
    print(json.dumps({"output": str(output), **summary}, indent=2, ensure_ascii=False))
    return 1 if any(r["independent_reference"]["status"] != "passed" or r["numerical_tool_reference"]["comparison"]["status"] != "passed"
                    or r["workflow"]["status"] == "error" for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
