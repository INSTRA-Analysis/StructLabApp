"""Benchmark utilities: comparison table printer and tolerance checker.

Used by bench_beams.py, bench_frames.py, bench_trusses.py.
"""

from __future__ import annotations

PASS_COLOR = "\033[32m"  # green
FAIL_COLOR = "\033[31m"  # red
RESET      = "\033[0m"
BOLD       = "\033[1m"

DEFAULT_TOL = 0.001  # 0.1 %


def print_header(title: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_case(label: str) -> None:
    print(f"\n  --- {label} ---")


def compare(
    quantity: str,
    structlab: float,
    reference: float,
    unit: str = "",
    tol: float = DEFAULT_TOL,
) -> bool:
    """Print one comparison row and return True if within tolerance."""
    if abs(reference) > 1e-12:
        rel_err = abs(structlab - reference) / abs(reference)
    else:
        rel_err = abs(structlab - reference)

    passed = rel_err <= tol
    status = f"{PASS_COLOR}PASS{RESET}" if passed else f"{FAIL_COLOR}FAIL{RESET}"
    err_str = f"{rel_err * 100:.4f}%"

    unit_str = f" {unit}" if unit else ""
    print(
        f"    {quantity:<32s}  SL={structlab:>12.4f}{unit_str}  "
        f"Ref={reference:>12.4f}{unit_str}  err={err_str:>8s}  [{status}]"
    )
    return passed


def compare_table(
    rows: list[tuple[str, float, float, str]],
    tol: float = DEFAULT_TOL,
) -> bool:
    """Run a list of (quantity, structlab, reference, unit) rows.

    Returns True only when every row passes.
    """
    results = [compare(q, sl, ref, u, tol) for q, sl, ref, u in rows]
    n_pass = sum(results)
    n_total = len(results)
    overall = all(results)
    marker = f"{PASS_COLOR}{BOLD}ALL PASS{RESET}" if overall else f"{FAIL_COLOR}{BOLD}FAILURES: {n_total - n_pass}/{n_total}{RESET}"
    print(f"    Result: {marker}")
    return overall
