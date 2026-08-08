"""
Pipeline/run_realworld_scale_validation.py
────────────────────────────────────────────
Validates the Experiment D scalability findings against real deployment
scales, rather than round-number synthetic grid points. Four configs,
P=4 (matching the Experiment D baseline), run SEQUENTIALLY:

  1. ccin2p3          T=1000, N=312   — Cochard & Simon 2026, confirmed
                                         full-year figures (arXiv:2606.05914)
  2. mit_supercloud   T=1000, N=704   — N confirmed (TX-Gaia, arXiv:2108.02037);
                                         T set to the upper bound of the paper's
                                         reported 600-1000+ user range (not a
                                         single confirmed number — flag this in
                                         any writeup that cites it)
  3. google_borg_5k   T=1000, N=5000  — Cell A user estimate x a sub-Borg node
                                         count matching Experiment D's largest
                                         tested N (row 19). Sits just above
                                         Experiment D's observed ~20-25M
                                         variable memory ceiling — genuine
                                         unknown outcome, not an obvious fail.
  4. google_borg_12k  T=1000, N=12000 — Same tenant count x full Borg median
                                         cell size (Verma et al. 2015). Well
                                         past the ceiling — expected OOM.

IMPORTANT — output files are UNIQUELY NAMED to avoid overwriting any prior
Experiment D / canary output:
  results/timing_data/realworld_scale_results.csv
  results/timing_data/realworld_scale_memlog.csv
(NOT sweep_results.csv, NOT canary_results.csv, NOT realworld_results.csv
from an earlier draft — those are untouched by this script.)

Safe to leave running overnight:
  - Sequential execution, one config at a time.
  - Each config capped at 4h (matching Experiment D's solver cap).
  - Resumable: reruns skip any label already in realworld_scale_results.csv.
  - Live memory polling logged continuously, same as prior scripts.

Usage
─────
  cd Pipeline/
  python run_realworld_scale_validation.py              # run all 4
  python run_realworld_scale_validation.py --only ccin2p3 mit_supercloud
  python run_realworld_scale_validation.py --dry-run     # print configs + var estimates only
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

# ── Path setup — mirrors run_scalability_sweep.py exactly ──────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "models" / "realtime"))
sys.path.insert(0, str(_ROOT / "models"))

from plan_ahead_data import build_synthetic_data, make_gurobi_env
from plan_ahead_optimizer import build_model
from gurobipy import GRB

DATA_DIR = Path(__file__).resolve().parent.parent / "results" / "timing_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Uniquely named — will NOT collide with sweep_*, canary_*, or any earlier file.
MEMLOG_PATH = DATA_DIR / "realworld_scale_memlog.csv"
RESULT_PATH = DATA_DIR / "realworld_scale_results.csv"

SEED = 42
CAP_S = 4 * 60 * 60      # 4h, matching Experiment D
HORIZON_HOURS = 24.0
P = 4                    # fixed at baseline P for all four configs
POLL_S = 5.0

# Same PA_* constants as run_scalability_sweep.py / computational_time_analysis.py
# Update here if these have changed on doubl since last sync.
PA_ALWAYS_FRAC = 0.5
PA_EXCL_FRAC = 0.20
PA_USAGE_MIN = 0.5
PA_USAGE_MAX = 2.5
PA_NODE_CAPACITY = 10.0
PA_MIP_GAP = 0.01

CONFIGS = [
    dict(label="ccin2p3", T=1000, N=312,
         source="Cochard & Simon 2026 (arXiv:2606.05914) — full-year confirmed T and N"),
    dict(label="mit_supercloud", T=1000, N=704,
         source="Samsi et al. 2021 (arXiv:2108.02037) — N confirmed (TX-Gaia); "
                "T set to upper bound of paper's reported 600-1000+ range, not a single confirmed figure"),
    dict(label="google_borg_5k", T=1000, N=5000,
         source="Cell A user estimate x Experiment D's largest tested N (row 19) — "
                "sits just above Experiment D's ~20-25M variable memory ceiling; outcome genuinely uncertain"),
    dict(label="google_borg_12k", T=1000, N=12000,
         source="Cell A user estimate x Verma et al. 2015 Borg median cell size — "
                "well past Experiment D's memory ceiling, OOM expected"),
]

FIELDNAMES = [
    "label", "T", "N", "P", "source",
    "total_vars", "binary_vars", "cont_vars", "constraints",
    "build_s", "solve_s", "total_s", "mip_gap", "status", "gurobi_obj",
    "started_at", "finished_at",
]

_proc = psutil.Process()
_total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)


def _rss_gb() -> float:
    return _proc.memory_info().rss / (1024 ** 3)


def _var_estimate(T: int, N: int, P: int) -> int:
    return 2 * T * N * P + 5 * N * P + N + 1


class MemPoller:
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
            done.add(row["label"])
    return done


def _save_result(result: dict) -> None:
    write_header = not RESULT_PATH.exists()
    with open(RESULT_PATH, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        if write_header:
            w.writeheader()
        w.writerow(result)


def run_one(cfg: dict) -> dict:
    T, N, label, source = cfg["T"], cfg["N"], cfg["label"], cfg["source"]
    slot_hours = HORIZON_HOURS / P

    n_always = max(1, int(N * PA_ALWAYS_FRAC))
    n_excl = min(max(1, int(T * PA_EXCL_FRAC)), T - 1)
    min_cap = (T * PA_USAGE_MAX) / max(1, N) * 1.3
    cap = max(PA_NODE_CAPACITY, min_cap)
    cap = min(cap, 500.0)
    usage_max = min(PA_USAGE_MAX, cap * 0.70)
    usage_min = min(PA_USAGE_MIN, usage_max * 0.50)

    print("=" * 70)
    print(f"  {label}   T={T} N={N} P={P}  slot_hours={slot_hours:.2f}  "
          f"est_vars={_var_estimate(T,N,P):,}")
    print(f"  Source: {source}")
    print("=" * 70)

    result = dict(label=label, T=T, N=N, P=P, source=source,
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
    ap = argparse.ArgumentParser(description="Real-world-scale validation runs (CC-IN2P3, MIT Supercloud, Google Borg x2)")
    ap.add_argument("--only", nargs="+", choices=[c["label"] for c in CONFIGS], default=None,
                     help="Run only specific labels, e.g. --only ccin2p3 mit_supercloud")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    run_list = [c for c in CONFIGS if (args.only is None or c["label"] in args.only)]

    if args.dry_run:
        for cfg in run_list:
            v = _var_estimate(cfg["T"], cfg["N"], P)
            print(f"{cfg['label']:<18} T={cfg['T']:<6} N={cfg['N']:<6} P={P}  est_vars={v:,}")
            print(f"    {cfg['source']}")
        sys.exit(0)

    completed = _load_completed_labels()
    print(f"Results  → {RESULT_PATH}")
    print(f"Mem log  → {MEMLOG_PATH}")
    if completed:
        print(f"Resuming: {len(completed)} label(s) already in results CSV will be skipped.")
    print()

    for cfg in run_list:
        if cfg["label"] in completed:
            print(f"Skipping {cfg['label']} (already completed).")
            continue
        res = run_one(cfg)
        _save_result(res)
        print(f"  → {cfg['label']} status={res['status']}  "
              f"build={res['build_s']}s  solve={res['solve_s']}s  logged.\n")

    print("Real-world-scale validation run(s) complete. Review realworld_scale_results.csv.")
