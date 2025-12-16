"""CLI for loading allocation data and writing stakeholder outputs.

This script keeps data ingestion and result export separate from the README so
you can run the optimizer directly from CSV tables.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import gurobipy as gp
import pandas as pd

from allocation_model import allocation_data_from_tables, build_allocation_model


def _read_table(path: Path, *, required: bool = True) -> Optional[pd.DataFrame]:
    if path.exists():
        return pd.read_csv(path)
    if required:
        raise FileNotFoundError(f"Missing required input table: {path}")
    return None


def run(data_dir: Path, output_prefix: Path, use_solution_pool: bool) -> None:
    doors = _read_table(data_dir / "doors.csv")
    articles = _read_table(data_dir / "articles.csv")
    eligibility = _read_table(data_dir / "eligibility.csv")
    supply = _read_table(data_dir / "supply.csv")
    heat = _read_table(data_dir / "heat.csv")
    tier_cap_runs = _read_table(data_dir / "tier_cap_runs.csv")
    tier_capacity = _read_table(data_dir / "tier_capacity.csv")

    data = allocation_data_from_tables(
        doors=doors,
        articles=articles,
        eligibility=eligibility,
        supply=supply,
        heat=heat,
        tier_cap_runs=tier_cap_runs,
        tier_capacity=tier_capacity,
    score = _read_table(data_dir / "score.csv")
    eligibility = _read_table(data_dir / "eligibility.csv")
    supply = _read_table(data_dir / "supply.csv")
    cap_runs = _read_table(data_dir / "cap_runs.csv")
    heat = _read_table(data_dir / "heat.csv")
    min_runs = _read_table(data_dir / "min_runs.csv", required=False)

    data = allocation_data_from_tables(
        score=score,
        eligibility=eligibility,
        supply=supply,
        cap_runs=cap_runs,
        heat=heat,
        min_runs=min_runs,
    )

    allocation = build_allocation_model(data)
    if use_solution_pool:
        allocation.add_solution_pool()

    status = allocation.optimize()
    if status not in {gp.GRB.OPTIMAL, gp.GRB.INTERRUPTED, gp.GRB.TIME_LIMIT}:
        raise RuntimeError(f"Model did not solve successfully (status={status}).")

    allocation_rows = allocation.summarize_allocations()
    slack_rows = allocation.constraint_slacks()

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(allocation_rows).to_csv(f"{output_prefix}_allocations.csv", index=False)
    pd.DataFrame(slack_rows).to_csv(f"{output_prefix}_slacks.csv", index=False)

    print(f"Wrote allocations to {output_prefix}_allocations.csv")
    print(f"Wrote constraint slacks to {output_prefix}_slacks.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing CSV inputs (doors, articles, eligibility, supply, heat, tier_cap_runs, tier_capacity).",
        help="Directory containing CSV inputs (score, eligibility, supply, cap_runs, heat, optional min_runs).",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=Path("outputs/allocation"),
        help="Prefix for output CSVs (allocations and constraint slacks).",
    )
    parser.add_argument(
        "--solution-pool",
        action="store_true",
        help="Enable Gurobi solution pool to capture alternative allocations.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(args.data_dir, args.output_prefix, args.solution_pool)


if __name__ == "__main__":
    main()
