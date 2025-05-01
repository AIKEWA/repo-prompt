"""
Evaluation Criteria utilities (Step 2.9).

This module formalises three KPI targets as defined in the specification:

| Metric                                     | Target                |
|--------------------------------------------|-----------------------|
| Code error rate *post-LLM*                  | ↓ 30 % (vs baseline) |
| Developer satisfaction                     | ↑ (non-negative delta)|
| Prompt-to-diff application success rate    | ≥ 85 %               |

The helper operates **exclusively** on data captured by existing stores, so
*no additional instrumentation* is required.

Integration strategy
--------------------
* Code error rate → derived from the *success_rate* of applied diffs returned
  by :pyfunc:`src.documentation_monitoring._combine_kpis`.
* Developer satisfaction → provided by
  :pyclass:`src.feedback_mechanism.DeveloperSurvey` events.
* Prompt-to-diff success rate → exposed as *"diffs.success_rate"* in the
  combined KPI dictionary.

CLI Usage
~~~~~~~~~
```bash
# Snapshot the current KPI values as the *baseline* for future comparisons
python -m src.evaluation_criteria snapshot-baseline

# Compare latest metrics against the defined targets
python -m src.evaluation_criteria evaluate
```

The *evaluate* command exits with a **non-zero** status when *any* target is
missed, making it suitable for CI gating.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import sys
from typing import Any, Dict, List

import typer

from .documentation_monitoring import _combine_kpis
from .logger import get_logger, setup_logging

__all__ = [
    "EvaluationTargets",
    "Evaluator",
    "app",
]

_log = get_logger(__name__)

_BASELINE_FILE = Path(".baseline_kpis.json")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EvaluationTargets:
    """Hard-coded KPI targets (can be serialised to JSON for customisation)."""

    code_error_reduction: float = 0.30  # ↓ 30 % (relative improvement)
    developer_satisfaction_delta: float = 0.0  # any positive gain (>= 0)
    prompt_to_diff_success_min: float = 0.85  # absolute threshold (≥ 85 %)

    # -------------------
    # Serialisation utils
    # -------------------

    def to_json(self) -> str:  # noqa: D401 – imperative mode not needed
        return json.dumps(asdict(self), indent=2) + "\n"


# ---------------------------------------------------------------------------
# Core evaluator
# ---------------------------------------------------------------------------


class Evaluator:
    """Compare *current* KPI values against a *baseline* & target thresholds."""

    def __init__(
        self,
        baseline_file: Path | str = _BASELINE_FILE,
        targets: EvaluationTargets | None = None,
    ) -> None:
        self.baseline_file = Path(baseline_file)
        self.targets = targets or EvaluationTargets()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def load_baseline(self) -> Dict[str, Any]:
        if not self.baseline_file.exists():
            _log.warning("Baseline KPI file %s does not exist; assuming empty baseline", self.baseline_file)
            return {}
        return json.loads(self.baseline_file.read_text(encoding="utf-8"))

    def save_baseline(self, kpis: Dict[str, Any]) -> None:
        self.baseline_file.write_text(json.dumps(kpis, indent=2) + "\n", encoding="utf-8")
        _log.info("Baseline KPI written to %s", self.baseline_file)

    def evaluate(self, current: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Return a *report* dictionary showing goal compliance for each KPI."""

        current = current or _combine_kpis()
        baseline = self.load_baseline()
        report: Dict[str, Any] = {
            "targets": asdict(self.targets),
            "baseline": baseline,
            "current": current,
            "results": {},
        }

        # ------------------------------
        # 1) Code error rate post-LLM
        # ------------------------------

        # Derive error rate as (1 - success_rate)
        curr_success = (current.get("diffs", {}).get("success_rate", 0)) / 100.0
        curr_error_rate = 1.0 - curr_success

        base_success = (baseline.get("diffs", {}).get("success_rate", 0)) / 100.0
        base_error_rate = 1.0 - base_success if baseline else None  # type: ignore[assignment]

        if base_error_rate is None or base_error_rate == 0:
            # Without baseline we cannot compute relative reduction; treat as *undetermined*
            err_ok = None
            perc_red = None
        else:
            perc_red = (base_error_rate - curr_error_rate) / base_error_rate
            err_ok = perc_red >= self.targets.code_error_reduction

        report["results"]["code_error_rate"] = {
            "current": round(curr_error_rate * 100, 2),
            "baseline": None if base_error_rate is None else round(base_error_rate * 100, 2),
            "percent_reduction": None if perc_red is None else round(perc_red * 100, 1),
            "ok": err_ok,
        }

        # ------------------------------
        # 2) Developer satisfaction ↑
        # ------------------------------

        curr_sat = current.get("developer_load", {}).get("average_satisfaction")
        base_sat = baseline.get("developer_load", {}).get("average_satisfaction") if baseline else None

        if base_sat is None:
            sat_ok = None  # cannot evaluate delta without baseline
            delta_sat = None
        else:
            delta_sat = curr_sat - base_sat if curr_sat is not None else None
            sat_ok = delta_sat is not None and delta_sat >= self.targets.developer_satisfaction_delta

        report["results"]["developer_satisfaction"] = {
            "current": curr_sat,
            "baseline": base_sat,
            "delta": delta_sat,
            "ok": sat_ok,
        }

        # ------------------------------
        # 3) Prompt→diff success rate > 85 %
        # ------------------------------

        curr_p2d = current.get("diffs", {}).get("success_rate")
        p2d_ok = curr_p2d is not None and curr_p2d >= self.targets.prompt_to_diff_success_min * 100

        report["results"]["prompt_to_diff_success_rate"] = {
            "current": curr_p2d,
            "threshold": self.targets.prompt_to_diff_success_min * 100,
            "ok": p2d_ok,
        }

        # ------------------------------
        # Overall pass/fail
        # ------------------------------

        oks = [v["ok"] for v in report["results"].values() if v["ok"] is not None]
        report["overall_pass"] = all(oks) if oks else None
        return report

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_status(ok: bool | None) -> str:
        if ok is None:
            return "❓"
        return "✅" if ok else "❌"

    def to_markdown(self, report: Dict[str, Any]) -> str:
        """Return a human-readable markdown table for *report*."""

        res = report["results"]
        lines: List[str] = [
            "# KPI Evaluation – Step 2.9\n",
            "| Metric | Current | Target / Delta | Status |",
            "|--------|---------|----------------|--------|",
            f"| Code error rate post-LLM | {res['code_error_rate']['current']}% | ↓ {int(self.targets.code_error_reduction*100)}% vs baseline | {self._render_status(res['code_error_rate']['ok'])} |",
            f"| Developer satisfaction | {res['developer_satisfaction']['current']} | ↑ | {self._render_status(res['developer_satisfaction']['ok'])} |",
            f"| Prompt→diff success rate | {res['prompt_to_diff_success_rate']['current']}% | ≥ {int(self.targets.prompt_to_diff_success_min*100)}% | {self._render_status(res['prompt_to_diff_success_rate']['ok'])} |",
        ]
        if report["overall_pass"] is not None:
            lines.append("\n**Overall**: " + ("🟢 PASS" if report["overall_pass"] else "🔴 FAIL"))
        else:
            lines.append("\nBaseline data missing – unable to compute complete evaluation.")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Typer CLI – minimal surface for CI & manual checks
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, help="Evaluate KPIs against targets (step 2.9).")


@app.command()
def snapshot_baseline(
    baseline_file: Path = typer.Option(_BASELINE_FILE, "--file", help="Path for baseline snapshot"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Write the *current* KPI aggregates to *baseline_file*."""

    setup_logging("DEBUG" if verbose else "INFO")
    evaluator = Evaluator(baseline_file)
    kpis = _combine_kpis()
    evaluator.save_baseline(kpis)
    typer.echo(f"Baseline KPI snapshot written to {baseline_file}")


@app.command()
def evaluate(
    baseline_file: Path = typer.Option(_BASELINE_FILE, "--baseline", help="Baseline KPI file"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Compare KPIs against targets. Exits *1* if **any** target is missed."""

    setup_logging("DEBUG" if verbose else "INFO")
    evaluator = Evaluator(baseline_file)
    report = evaluator.evaluate()

    if json_output:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        typer.echo(evaluator.to_markdown(report))

    # CI-friendly exit status
    if report["overall_pass"] is False:
        raise typer.Exit(code=1)


# Allow "python -m src.evaluation_criteria …"
if __name__ == "__main__":
    app()