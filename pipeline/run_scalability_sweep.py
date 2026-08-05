"""
Pipeline/run_scalability_sweep.py
──────────────────────────────────
Sequential Plan-Ahead MISOCP scalability sweep — Gurobi-only, per capstone
experiment prompt. Runs the 25-config final list (32 original rows minus
the 7 excluded T=2500/N=5000-and-adjacent rows confirmed/inferred to OOM
on doubl — see canary_results.csv).

Design notes (deliberate departures from _run_experiment in
computational_time_analysis.py):
  - SEQUENTIAL, not threaded. Every config builds+solves one at a time.
  - slot_hours = 24 / P, computed per row, so the 24h horizon stays fixed
    as P varies (the prior run_exp_b() hardcoded slot_hours=6.0, which let
    the horizon drift with P — not replicated here).
  - Explicit (T,N,P) tuple list, not a T_list × N_list × P_list cartesian
    product — this grid is NOT a full factorial.
  - Row 25 (T=2500,N=1000,P=4, ~20M est. vars) is UNTESTED for memory —
    it's included in its natural run-order position; if it OOMs, that's
    logged like any other row and the sweep continues.
  - Resumable: on startaup, any label already present in the results CSV
    is skipped, so a Ctrl+C or crash partway through doesn't lose progress
    or force a restart from row 1.

Usage
─────
  cd Pipeline/
  python run_scalability_sweep.py                 # full 25-row sweep
  python run_scalability_sweep.py --start-at 10    # resume from row 10 (1-indexed, run-order)
  python run_scalability_sweep.py --dry-run        # print the row list + var estimates, no Gurobi calls
"""

from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except ImportError:
    print("This script needs psutil for memory polling: pip install psutil")
    sys.exit(1)

# ── Path setup — mirrors computational_time_analysis.py exactly ────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "models" / "realtime"))
sys.path.insert(0, str(_ROOT / "models"))

from plan_ahead_data import build_synthetic_data, make_gurobi_env
from plan_ahead_optimizer import build_model
from gurobipy import GRB

DATA_DIR = Path(__file__).resolve().parent.parent / "results" / "timing_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MEMLOG_PATH = DATA_DIR / "sweep_memlog.csv"
RESULT_PATH = DATA_DIR / "sweep_results.csv"

SEED = 42
CAP_S = 4 * 60 * 60      # 4h fixed cap, per your grid spec
HORIZON_HOURS = 24.0     # fixed horizon — slot_hours derived per row as HORIZON_HOURS / P
POLL_S = 5.0             # slightly coarser than the canary's 3s; sweep runs much longer overall

# Same PA_* constants as computational_time_analysis.py — kept in sync manually.
# If these have changed on doubl since the version I reviewed, UPDATE HERE TOO.
PA_ALWAYS_FRAC = 0.5
PA_EXCL_FRAC = 0.20
PA_USAGE_MIN = 0.5
PA_USAGE_MAX = 2.5
PA_NODE_CAPACITY = 10.0
PA_MIP_GAP = 0.01

# ── Final 25-config run list (excludes rows 26,27,28,29,30,31,32 from the
#    original 32-row grid — see canary results). Order = cheapest→most
#    expensive, per your original prompt.
RUN_LIST = [
    dict(idx=1,  T=10,   N=250,  P=1,  layer="L2-Small"),
    dict(idx=2,  T=100,  N=10,   P=4,  layer="L1-B"),
    dict(idx=3,  T=10,   N=250,  P=2,  layer="L2-Small"),
    dict(idx=4,  T=10,   N=250,  P=4,  layer="L2-Small"),
    dict(idx=5,  T=100,  N=50,   P=4,  layer="L1-B"),
    dict(idx=6,  T=10,   N=250,  P=8,  layer="L2-Small"),
    dict(idx=7,  T=10,   N=1000, P=4,  layer="L1-A"),
    dict(idx=8,  T=10,   N=250,  P=24, layer="L2-Small"),
    dict(idx=9,  T=25,   N=1000, P=4,  layer="L1-A"),
    dict(idx=10, T=100,  N=250,  P=4,  layer="L1-B"),
    dict(idx=11, T=100,  N=1000, P=1,  layer="L1-C"),
    dict(idx=12, T=100,  N=1000, P=2,  layer="L1-C"),
    dict(idx=13, T=100,  N=3000, P=1,  layer="L2-Medium"),
    dict(idx=14, T=100,  N=1000, P=4,  layer="Baseline"),
    dict(idx=15, T=100,  N=3000, P=2,  layer="L2-Medium"),
    dict(idx=16, T=100,  N=1000, P=8,  layer="L1-C"),
    dict(idx=17, T=100,  N=3000, P=4,  layer="L1-B"),
    dict(idx=18, T=500,  N=1000, P=4,  layer="L1-A"),
    dict(idx=19, T=100,  N=5000, P=4,  layer="L1-B"),
    dict(idx=20, T=100,  N=1000, P=24, layer="L1-C"),
    dict(idx=21, T=100,  N=3000, P=8,  layer="L2-Medium"),
    dict(idx=22, T=2500, N=1000, P=1,  layer="L2-Large"),
    dict(idx=23, T=2500, N=1000, P=2,  layer="L2-Large"),
    dict(idx=24, T=100,  N=3000, P=24, layer="L2-Medium"),
    dict(idx=25, T=2500, N=1000, P=4,  layer="L1-A"),   # UNTESTED for memory — see docstring
]

EXCLUDED = [
    dict(idx=26, T=2500, N=5000, P=1,  layer="L2-Large", reason="OOM confirmed (canary)"),
    dict(idx=27, T=2500, N=1000, P=8,  layer="L2-Large", reason="OOM confirmed (canary)"),
    dict(idx=28, T=2500, N=5000, P=2,  layer="L2-Large", reason="OOM inferred (same family as row 26/29)"),
    dict(idx=29, T=2500, N=5000, P=4,  layer="L2-Large", reason="OOM confirmed (canary)"),
    dict(idx=30, T=2500, N=1000, P=24, layer="L2-Large", reason="OOM inferred (>row 27's est. var count, which OOM'd)"),
    dict(idx=31, T=2500, N=5000, P=8,  layer="L2-Large", reason="OOM inferred (same family as row 26/29)"),
    dict(idx=32, T=2500, N=5000, P=24, layer="L2-Large", reason="OOM inferred (same family as row 26/29)"),
]

FIELDNAMES = [
    "idx", "layer", "T", "N", "P", "slot_hours",
    "total_vars", "binary_vars", "cont_vars", "constraints",
    "build_s", "solve_s", "total_s", "mip_gap", "status", "gurobi_obj",
    "started_at", "finished_at",
]

_proc = psutil.Process()
_total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)


def _rss_gb() -> float:
    return _proc.memory_info().rss / (1024 ** 3)


def _var_estimate(T: int, N: int, P: int) -> int:
    # Matches _pa_var_estimate's algebra: 2*T*N*P + 5*N*P + N + 1
    return 2 * T * N * P + 5 * N * P + N + 1


class MemPoller:
    """Background thread: samples RSS every POLL_S seconds, prints + logs to CSV."""

    def __init__(self, label: str, phase_holder: list[str]):
        self.label = label
        self.phase_holder = phase_holder
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        write_header = not MEMLOG_PATH.exists()
        self._fh = open(MEMLOG_PATH, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        if write_header:
            self._writer.writerow(["timestamp", "label", "phase", "rss_gb", "total_ram_gb", "pct_of_total"])

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=POLL_S + 2)
        self._fh.close()

    def _run(self):
        while not self._stop.is_set():
            rss = _rss_gb()
            pct = 100.0 * rss / _total_ram_gb
            ts = datetime.now(timezone.utc).isoformat()
            phase = self.phase_holder[0]
            print(f"    [mem] {phase:<8} rss={rss:6.2f} GB  ({pct:5.1f}% of {_total_ram_gb:.1f} GB total)")
            self._writer.writerow([ts, self.label, phase, round(rss, 3), round(_total_ram_gb, 2), round(pct, 2)])
            self._fh.flush()
            self._stop.wait(POLL_S)


def _load_completed_labels() -> set[str]:
    if not RESULT_PATH.exists():
        return set()
    done = set()
    with open(RESULT_PATH, "r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            done.add(row["idx"])
    return done


def _save_result(result: dict) -> None:
    write_header = not RESULT_PATH.exists()
    with open(RESULT_PATH, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        if write_header:
            w.writeheader()
        w.writerow(result)


def run_one(cfg: dict) -> dict:
    T, N, P, idx, layer = cfg["T"], cfg["N"], cfg["P"], cfg["idx"], cfg["layer"]
    label = f"row{idx}_T{T}_N{N}_P{P}"
    slot_hours = HORIZON_HOURS / P

    n_always = max(1, int(N * PA_ALWAYS_FRAC))
    n_excl = min(max(1, int(T * PA_EXCL_FRAC)), T - 1)
    min_cap = (T * PA_USAGE_MAX) / max(1, N) * 1.3
    cap = max(PA_NODE_CAPACITY, min_cap)
    cap = min(cap, 500.0)
    usage_max = min(PA_USAGE_MAX, cap * 0.70)
    usage_min = min(PA_USAGE_MIN, usage_max * 0.50)

    print("=" * 70)
    print(f"  ROW {idx}/{RUN_LIST[-1]['idx']}  [{layer}]  T={T} N={N} P={P}  "
          f"slot_hours={slot_hours:.2f}  est_vars={_var_estimate(T,N,P):,}")
    print("=" * 70)

    result = dict(idx=idx, layer=layer, T=T, N=N, P=P, slot_hours=round(slot_hours, 4),
                  total_vars=None, binary_vars=None, cont_vars=None, constraints=None,
                  build_s=None, solve_s=None, total_s=None, mip_gap=None, status="UNKNOWN",
                  gurobi_obj=None, started_at=datetime.now(timezone.utc).isoformat(),
                  finished_at=None)

    phase = ["init"]
    poller = MemPoller(label, phase)
    poller.start()

    env = None
    t_row_start = time.perf_counter()
    try:
        phase[0] = "data"
        P_dict = build_synthetic_data(
            seed=SEED, n_tenants=T, n_nodes=N, n_intervals=P,
            node_capacity=cap, n_always_available=n_always, n_exclusive=n_excl,
            tenant_usage_min=usage_min, tenant_usage_max=usage_max,
            sigma_frac=0.20, epsilon=0.10, min_machines_per_tenant=1,
        )

        env = make_gurobi_env()

        phase[0] = "build"
        t0 = time.perf_counter()
        model, _ = build_model(P_dict, env, use_socp=True)
        model.update()
        build_s = time.perf_counter() - t0
        result["build_s"] = round(build_s, 3)
        result["total_vars"] = model.NumVars
        result["binary_vars"] = model.NumBinVars
        result["cont_vars"] = model.NumVars - model.NumBinVars
        result["constraints"] = model.NumConstrs + model.NumQConstrs + model.NumGenConstrs
        print(f"  BUILD DONE: {build_s:.1f}s  vars={model.NumVars:,}  constrs={result['constraints']:,}")

        model.Params.LogToConsole = 0
        model.Params.OutputFlag = 0
        model.Params.TimeLimit = CAP_S
        model.Params.MIPGap = PA_MIP_GAP

        phase[0] = "solve"
        model.optimize()
        result["solve_s"] = round(model.Runtime, 3)

        sc = model.Status
        if sc == GRB.OPTIMAL:
            result["status"] = "OPT"
            result["mip_gap"] = model.MIPGap
        elif sc == GRB.TIME_LIMIT:
            result["status"] = "TLim"
            try:
                result["mip_gap"] = model.MIPGap
            except Exception:
                pass
        elif sc in (GRB.INFEASIBLE, GRB.INF_OR_UNBD):
            result["status"] = "INF"
        else:
            result["status"] = f"S{sc}"

        try:
            result["gurobi_obj"] = model.ObjVal
        except Exception:
            pass

        model.dispose()

    except MemoryError:
        result["status"] = "ERR_MemoryError"
        print("  !! Python-level MemoryError caught !!")
    except Exception as exc:
        result["status"] = f"ERR_{type(exc).__name__}"
        print(f"  !! Exception: {exc}")
    finally:
        phase[0] = "done"
        poller.stop()
        if env is not None:
            try:
                env.dispose()
            except Exception:
                pass
        result["total_s"] = round(time.perf_counter() - t_row_start, 3)
        result["finished_at"] = datetime.now(timezone.utc).isoformat()

    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Sequential Plan-Ahead scalability sweep (25-row final list)")
    ap.add_argument("--start-at", type=int, default=None,
                     help="Skip to this row index (1-indexed, run-order) — for manual resume")
    ap.add_argument("--dry-run", action="store_true",
                     help="Print the row list + variable estimates, make no Gurobi calls")
    args = ap.parse_args()

    if args.dry_run:
        print(f"{'#':>3} {'T':>6} {'N':>6} {'P':>4} {'~Vars':>14} {'Layer':<10}")
        for cfg in RUN_LIST:
            v = _var_estimate(cfg["T"], cfg["N"], cfg["P"])
            print(f"{cfg['idx']:>3} {cfg['T']:>6} {cfg['N']:>6} {cfg['P']:>4} {v:>14,} {cfg['layer']:<10}")
        print(f"\nExcluded ({len(EXCLUDED)} rows):")
        for cfg in EXCLUDED:
            print(f"  row{cfg['idx']}: T={cfg['T']} N={cfg['N']} P={cfg['P']}  — {cfg['reason']}")
        sys.exit(0)

    completed = _load_completed_labels()
    print(f"Results  → {RESULT_PATH}")
    print(f"Mem log  → {MEMLOG_PATH}")
    if completed:
        print(f"Resuming: {len(completed)} row(s) already in results CSV will be skipped.")
    print()

    for cfg in RUN_LIST:
        if args.start_at and cfg["idx"] < args.start_at:
            continue
        if str(cfg["idx"]) in completed:
            print(f"Skipping row {cfg['idx']} (already completed).")
            continue
        res = run_one(cfg)
        _save_result(res)
        print(f"  → row {cfg['idx']} status={res['status']}  "
              f"build={res['build_s']}s  solve={res['solve_s']}s  logged.\n")

    print("Sweep complete (or all remaining rows attempted). Review sweep_results.csv.")
