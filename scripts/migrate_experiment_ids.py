"""One-time rename of experiment ids after the standalone-experiments split.

Run ONCE against the live database, immediately before deploying the new code:

    .venv/bin/python scripts/migrate_experiment_ids.py --dry-run
    .venv/bin/python scripts/migrate_experiment_ids.py

Idempotent: ids already migrated are skipped. Ids not in the map are left
alone and reported. Aborts if a new id already exists while its old id also
does -- that means the new code booted before the migration and inserted blank
rows, which must be resolved by hand.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Running this file directly (not via `python -m` or pytest's pythonpath=.)
# puts scripts/ rather than the repo root on sys.path, so the repo-root
# imports below need the root added first.
sys.path.insert(0, str(ROOT))

from sqlalchemy import select, update  # noqa: E402

from hub import db  # noqa: E402

RENAMES = {
    "w2.consumer_model": "consumer_model",
    "w2.consumer_elasticity": "consumer_elasticity",
    "w2.supplier_model": "supplier_model",
    "w2.supplier_elasticity": "supplier_elasticity",
    "w2.market_equilibrium": "market_equilibrium",
    "w3.pool_pricing": "pool_pricing",
    "w3.market_power": "market_power",
    "w3.profit_cost_recovery": "profit_cost_recovery",
    "w3.interactive_clearing": "interactive_clearing",
    "w4.nonlinear_3d": "nonlinear_optimisation_3d",
    "w4.tools_comparison": "modelling_tools_comparison",
    "w6.strong_duality": "strong_duality",
    "w6.weak_duality": "weak_duality",
    "w6.duality_theorems": "duality_theorems",
    "w7.generator_setup": "dispatch_generator_setup",
    "w7.comparison_results": "dispatch_comparison",
    "w7.detailed_analysis": "dispatch_detailed_analysis",
    "w7.individual_generators": "dispatch_individual_generators",
    "w7.pareto": "dispatch_pareto_frontier",
    "w8.market_setup": "auction_market_setup",
    "w8.network_topology": "auction_network_topology",
    "w8.market_results": "auction_market_results",
    "w8.dc_opf_results": "dc_opf_results",
    "w8.market_vs_opf": "auction_vs_dc_opf",
    "w8.theory": "power_flow_theory",
}


def main(dry_run: bool) -> None:
    engine = db.get_engine()
    with engine.begin() as conn:
        present = {r[0] for r in conn.execute(select(db.experiment.c.experiment_id))}

        collisions = [old for old, new in RENAMES.items()
                      if old in present and new in present]
        if collisions:
            raise SystemExit(
                "ABORT: both old and new ids present for: "
                + ", ".join(sorted(collisions))
                + "\nThe new code booted before this migration ran. Resolve by hand."
            )

        renamed = 0
        for old, new in RENAMES.items():
            if old not in present:
                continue
            if not dry_run:
                conn.execute(update(db.experiment)
                             .where(db.experiment.c.experiment_id == old)
                             .values(experiment_id=new))
                conn.execute(update(db.event)
                             .where(db.event.c.experiment_id == old)
                             .values(experiment_id=new))
            print(f"  {old} -> {new}")
            renamed += 1

        unknown = sorted(present - set(RENAMES) - set(RENAMES.values()))
        if unknown:
            print("left alone (not in the rename map): " + ", ".join(unknown))

        verb = "would rename" if dry_run else "renamed"
        print(f"{verb} {renamed} experiment ids")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
