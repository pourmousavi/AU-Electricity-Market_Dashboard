"""Re-pull the six vendored dashboards from their upstream repos.

The vendored files under sources/ are never edited by hand. This script is the
only sanctioned way to change them. Run the smoke test afterwards.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES: dict[str, tuple[str, str]] = {
    "week2_consumer_supplier.py": (
        "Electricity-Market-Course---Consumer-Supplier-Model-Elasticity-and-Equilibrium",
        "Dashboard_Week2.py",
    ),
    "week3_pricing_market_power.py": (
        "Electricity-Market-Course---Pricing-marketPower-profitCostRecovery-bidding",
        "Dashboard_Week3.py",
    ),
    "week4_optimisation_tools.py": (
        "Electricity-Market-Course---Basic-Def-Optimisation-Tools-Comparison",
        "Dashboard_Week4.py",
    ),
    "week6_duality.py": (
        "Electricity-Market-Course---Duality-Theory",
        "Dashboard_Week6.py",
    ),
    "week7_ed_viu.py": (
        "Electricity-Market-Course---ED-VIU",
        "Dashboard-week7.py",
    ),
    "week8_pf_auction.py": (
        "Electricity-Market-Course---PF-double-sided-auction",
        "Dashboard-Week8.py",
    ),
}


def _fetch(repo: str, path: str) -> bytes:
    return subprocess.run(
        ["gh", "api", f"repos/pourmousavi/{repo}/contents/{path}",
         "-H", "Accept: application/vnd.github.raw"],
        check=True, capture_output=True,
    ).stdout


def sync(dry_run: bool = False) -> list[str]:
    """Download each upstream file; return names whose content changed."""
    changed: list[str] = []
    for local, (repo, path) in SOURCES.items():
        remote = _fetch(repo, path)
        target = ROOT / "sources" / local
        current = target.read_bytes() if target.exists() else b""
        if hashlib.sha256(remote).digest() != hashlib.sha256(current).digest():
            changed.append(local)
            if not dry_run:
                target.write_bytes(remote)
    return changed


if __name__ == "__main__":
    import sys

    dry = "--dry-run" in sys.argv
    changed = sync(dry_run=dry)
    if not changed:
        print("All six sources are up to date.")
    else:
        verb = "would change" if dry else "updated"
        print(f"{verb}: " + ", ".join(changed))
        print("Run: pytest tests/test_experiments_render.py")
