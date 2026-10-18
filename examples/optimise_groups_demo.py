"""Re-profile the angle groups of a .slab model to a utilisation target (EN 1993-1-1 buckling check).

    python examples/optimise_groups_demo.py examples/l8c_d30_tower_seminar_optimised.slab out.slab
    python examples/optimise_groups_demo.py model.slab out.slab --target 0.9 --min "L 50×5" --slenderness 200

The ULS combinations are regenerated from the load cases (EN 1990 Table A1.2(B)), the sections are
chosen per group, and the result is saved to the second file. The input file is not changed.
Leg groups named "Leg 1 (base)" ... "Leg 4 (top)", when present, are kept in size order.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui_qt.combinations import auto_generate_en1990
from ui_qt.io import load_model, save_model
from ui_qt.optimise import optimise_groups

LEGS = ["Leg 1 (base)", "Leg 2", "Leg 3", "Leg 4 (top)"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("output")
    ap.add_argument("--target", type=float, default=0.85, help="utilisation every member stays under")
    ap.add_argument("--min", dest="min_section", default=None, help='smallest allowed section, e.g. "L 50×5"')
    ap.add_argument("--slenderness", type=float, default=None, help="L / i_v limit (yours, not a code's)")
    ap.add_argument("--crossing-braces", action="store_true", help="treat crossing bracing as connected")
    args = ap.parse_args()

    state = load_model(args.model)
    if args.crossing_braces:
        state.crossing_braces = True
    auto_generate_en1990(state)
    chains = [LEGS] if all(any(m.group == g for m in state.members) for g in LEGS) else None
    result = optimise_groups(state, state.combinations, target=args.target, min_section=args.min_section,
                             max_slenderness=args.slenderness, ordered=chains)
    print(result.table())
    save_model(state, args.output)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
