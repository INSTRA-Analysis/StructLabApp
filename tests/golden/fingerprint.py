"""Reduce a solved model to the numbers worth freezing."""

from __future__ import annotations

import warnings

import numpy as np


def fingerprint(model) -> dict:
    """Displacements and reactions at the user's own nodes, plus every member's end forces."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = model.solve()
    cache = result._cache
    dpn = cache["model"].dofs_per_node
    user_ids = [n.id for n in model._state.nodes]
    disp = cache["displacements"].reshape(-1, dpn)[user_ids]
    reac = cache["reactions"].reshape(-1, dpn)[user_ids]
    forces = [r.end_forces for r in cache["member_results"]]
    return {
        "dofs_per_node": dpn,
        "displacements": np.round(disp, 12).tolist(),
        "reactions": np.round(reac, 6).tolist(),
        "member_end_forces": np.round(np.array(forces), 6).tolist(),
    }
