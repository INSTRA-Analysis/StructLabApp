"""StructLab Benchmark Runner — Phase 8.

Runs all 20 benchmark cases (B1–B7, F1–F3, T1–T2, 3D1–3D8),
prints a console summary, and optionally generates the PDF report.

Usage:
    python benchmarks/run_all.py               # console + PDF
    python benchmarks/run_all.py --no-pdf      # console only
    python benchmarks/run_all.py --pdf-only    # skip console, generate PDF
"""
from __future__ import annotations

import sys
import os
import time
import argparse

# Force UTF-8 output on Windows (avoids cp1252 encode errors for Greek/super chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarks.result import BenchResult, TOL

PASS_CLR = "\033[32m"
FAIL_CLR = "\033[31m"
BOLD     = "\033[1m"
CYAN     = "\033[36m"
RESET    = "\033[0m"
DIM      = "\033[2m"


def _pct(v: float) -> str:
    return f"{v * 100:.4f}%"


def _status(passed: bool) -> str:
    if passed:
        return f"{PASS_CLR}PASS{RESET}"
    return f"{FAIL_CLR}FAIL{RESET}"


def print_result(br: BenchResult) -> None:
    hdr = f"  [{br.case_id}] {br.title}"
    print(f"\n{CYAN}{BOLD}{hdr}{RESET}")
    print(f"{DIM}  {br.description[:90]}{RESET}")
    for q in br.quantities:
        err_str = _pct(q.rel_error)
        ref_tag = f"[vs {q.reference_type}]"
        print(f"    {q.label:<35s}  SL={q.structlab:>10.4f} {q.unit:<6s}  "
              f"Ref={q.reference:>10.4f} {q.unit:<6s}  "
              f"err={err_str:>8s}  {ref_tag:<20s}  [{_status(q.passed)}]")
    overall = f"{PASS_CLR}{BOLD}ALL PASS{RESET}" if br.passed else \
              f"{FAIL_CLR}{BOLD}{br.n_total - br.n_pass}/{br.n_total} FAIL{RESET}"
    print(f"  → {overall}   max err = {br.max_error_pct:.4f}%")


def print_summary(results: list[BenchResult]) -> None:
    print()
    print("=" * 72)
    print(f"  {BOLD}SUMMARY — StructLab Benchmark Suite{RESET}")
    print("=" * 72)

    cats = ["2D Beams", "2D Frames", "2D Trusses", "3D Frames"]
    total_cases = len(results)
    total_pass  = sum(r.passed for r in results)
    total_q     = sum(r.n_total for r in results)
    total_qpass = sum(r.n_pass  for r in results)

    for cat in cats:
        cat_results = [r for r in results if r.category == cat]
        if not cat_results:
            continue
        n_p = sum(r.passed for r in cat_results)
        n_t = len(cat_results)
        print(f"\n  {cat}")
        for r in cat_results:
            icon = "+" if r.passed else "x"
            col  = PASS_CLR if r.passed else FAIL_CLR
            print(f"    {col}{icon}{RESET}  {r.case_id:<5s}  {r.title:<50s}  "
                  f"max err {r.max_error_pct:.4f}%")
        sub_status = f"{PASS_CLR}ALL PASS{RESET}" if n_p == n_t else \
                     f"{FAIL_CLR}{n_t - n_p} FAILED{RESET}"
        print(f"    {sub_status} ({n_p}/{n_t})")

    print()
    print("-" * 72)
    all_ok = total_pass == total_cases
    banner = f"{PASS_CLR}{BOLD}ALL {total_cases} CASES PASSED -- {total_qpass}/{total_q} quantities <= {TOL*100:.1f}%{RESET}" \
             if all_ok else \
             f"{FAIL_CLR}{BOLD}{total_cases - total_pass}/{total_cases} CASES FAILED{RESET}"
    print(f"  {banner}")
    print("-" * 72)


def run_cases(verbose: bool = True) -> list[BenchResult]:
    from benchmarks.cases.beams_2d   import run_all as beams
    from benchmarks.cases.frames_2d  import run_all as frames2d
    from benchmarks.cases.trusses_2d import run_all as trusses
    from benchmarks.cases.frames_3d  import run_all as frames3d

    groups = [
        ("2D Beams",   beams),
        ("2D Frames",  frames2d),
        ("2D Trusses", trusses),
        ("3D Frames",  frames3d),
    ]

    all_results: list[BenchResult] = []

    for section, fn in groups:
        if verbose:
            print()
            print(f"{BOLD}{'='*72}{RESET}")
            print(f"{BOLD}  {section}{RESET}")
            print(f"{BOLD}{'='*72}{RESET}")
        t0 = time.perf_counter()
        results = fn()
        elapsed = time.perf_counter() - t0
        if verbose:
            for r in results:
                print_result(r)
            print(f"\n  {DIM}Section elapsed: {elapsed:.2f}s{RESET}")
        all_results.extend(results)

    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description="StructLab benchmark runner")
    parser.add_argument("--no-pdf",   action="store_true", help="Skip PDF generation")
    parser.add_argument("--pdf-only", action="store_true", help="Skip console, generate PDF only")
    args = parser.parse_args()

    verbose = not args.pdf_only

    print(f"\n{BOLD}StructLab Phase 8 — Benchmark Suite{RESET}")
    print(f"Running 20 cases: B1-B7, F1-F3, T1-T2, 3D1-3D8\n")

    t_start = time.perf_counter()
    results = run_cases(verbose=verbose)
    t_total = time.perf_counter() - t_start

    if verbose:
        print_summary(results)
        print(f"\n  Total elapsed: {t_total:.1f}s\n")

    if not args.no_pdf:
        try:
            rpt_dir = os.path.join(os.path.dirname(__file__), "..", "Benchmark report")
            sys.path.insert(0, rpt_dir)
            from generate_report import generate  # type: ignore
            out = generate(results)
            print(f"\n  PDF report: {out}")
        except ImportError as e:
            print(f"\n  [Warning] PDF generation skipped: {e}")
        except Exception as e:
            print(f"\n  [Error] PDF generation failed: {e}")

    # Exit code: 0 if all pass, 1 if any fail
    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == "__main__":
    main()
