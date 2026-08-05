"""
Pipeline/canary_scalability_check.py
─────────────────────────────────────
Memory canary for the T=2500 block of the new scalability grid, BEFORE
committing the full 32-config sweep.

Runs two configs SEQUENTIALLY (not threaded — this is the point):
  Canary 1: T=2500, N=5000, P=1   (~25M vars estimated)
  Canary 2: T=2500, N=5000, P=4   (~100M vars estimated)

A background thread polls process RSS (via psutil) every POLL_S seconds
and appends to canary_memlog.csv on disk, so if the OS OOM-kills the
process outright, you still have the memory trajectory leading up to it —
not just a crashed terminal.

Usage
─────
  cd Pipeline/
  python canary_scalability_check.py            # runs both, in order
  python canary_scalability_check.py --only 1   # just the smaller one first

Read the printed RSS numbers as you go. If canary 1 looks like it's
climbing toward the machine's total RAM before build finishes, kill it
(Ctrl+C) — the CSV log will still show the trajectory, which is itself
useful data for deciding the real cutoff.
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
LOG_PATH = DATA_DIR / "canary_memlog.csv"
RESULT_PATH = DATA_DIR / "canary_results.csv"

SEED = 42          # same master seed as computational_time_analysis.py
CAP_S = 4 * 60 * 60  # 4h fixed cap, per your grid spec
POLL_S = 3.0        # seconds between memory samples

# Same PA_* constants as computational_time_analysis.py (kept in sync manually —
# if you've changed those constants since I saw the file, update here too)
PA_ALWAYS_FRAC = 0.5
PA_EXCL_FRAC = 0.20
PA_USAGE_MIN = 0.5
PA_USAGE_MAX = 2.5
PA_NODE_CAPACITY = 10.0
PA_MIP_GAP = 0.01

CANARIES = {
    1: dict(T=2500, N=1000, P=8, label="row27_T2500_N1000_P8"),
}

_proc = psutil.Process()
_total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)


def _rss_gb() -> float:
    return _proc.memory_info().rss / (1024 ** 3)


class MemPoller:
    """Background thread: samples RSS every POLL_S seconds, prints + logs to CSV."""

    def __init__(self, label: str, phase_holder: list[str]):
        self.label = label
        self.phase_holder = phase_holder  # mutable [phase_string], updated by caller
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        write_header = not LOG_PATH.exists()
        self._fh = open(LOG_PATH, "a", newline="", encoding="utf-8")
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


def run_canary(T: int, N: int, P: int, label: str) -> dict:
    n_always = max(1, int(N * PA_ALWAYS_FRAC))
    n_excl = min(max(1, int(T * PA_EXCL_FRAC)), T - 1)

    min_cap = (T * PA_USAGE_MAX) / max(1, N) * 1.3
    cap = max(PA_NODE_CAPACITY, min_cap)
    cap = min(cap, 500.0)
    usage_max = min(PA_USAGE_MAX, cap * 0.70)
    usage_min = min(PA_USAGE_MIN, usage_max * 0.50)

    print("=" * 70)
    print(f"  CANARY: {label}   T={T}  N={N}  P={P}  cap={CAP_S/3600:.0f}h")
    print(f"  Machine RAM total: {_total_ram_gb:.1f} GB")
    print("=" * 70)

    phase = ["init"]
    poller = MemPoller(label, phase)
    poller.start()

    result = dict(label=label, T=T, N=N, P=P, status="UNKNOWN",
                  build_s=None, solve_s=None, n_vars=None, n_bin_vars=None,
                  n_cont_vars=None, n_constrs=None, obj_val=None, mip_gap=None)

    env = None
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
        build_s = time.perf_counter() - t0
        result["build_s"] = round(build_s, 3)
        result["n_vars"] = model.NumVars
        result["n_bin_vars"] = model.NumBinVars
        result["n_cont_vars"] = model.NumVars - model.NumBinVars
        result["n_constrs"] = model.NumConstrs + model.NumQConstrs + model.NumGenConstrs
        print(f"  BUILD DONE: {build_s:.1f}s  vars={model.NumVars:,}  "
              f"constrs={result['n_constrs']:,}")

        model.Params.LogToConsole = 0
        model.Params.OutputFlag = 0
        model.Params.TimeLimit = CAP_S
        model.Params.MIPGap = PA_MIP_GAP

        phase[0] = "solve"
        t1 = time.perf_counter()
        model.optimize()
        solve_s = model.Runtime
        result["solve_s"] = round(solve_s, 3)

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
            result["obj_val"] = model.ObjVal
        except Exception:
            pass

        model.dispose()

    except MemoryError:
        result["status"] = "ERR_MEMORYERROR"
        print("  !! Python-level MemoryError caught (not an OS OOM-kill) !!")
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

    return result


def _save_result(result: dict) -> None:
    write_header = not RESULT_PATH.exists()
    with open(RESULT_PATH, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(result.keys()))
        if write_header:
            w.writeheader()
        w.writerow(result)
    print(f"  → result appended to {RESULT_PATH}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Memory canary for T=2500 configs")
    ap.add_argument("--only", type=int, choices=[1, 2], default=None,
                     help="Run only canary 1 or 2 (default: both, in order)")
    args = ap.parse_args()

    order = [args.only] if args.only else [1, 2]

    print(f"Memory log  → {LOG_PATH}")
    print(f"Result log  → {RESULT_PATH}")
    print()

    for idx in order:
        cfg = CANARIES[idx]
        res = run_canary(cfg["T"], cfg["N"], cfg["P"], cfg["label"])
        _save_result(res)
        print()

    print("Canary run(s) complete. Review canary_results.csv and canary_memlog.csv")
    print("before deciding the real cutoff for the T=2500 block.")
