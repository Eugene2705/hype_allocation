
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import gurobipy as gp
import pandas as pd

from allocation_model import allocation_data_from_tables, build_allocation_model


def _read_table(path: Path, *, required: bool = True) -> Optional[pd.DataFrame]:
    if path.exists():
        return pd.read_excel(path)
    if required:
        raise FileNotFoundError(f"Missing required input table: {path}")
    return None


def run(data_dir: Path, output_prefix: Path, use_solution_pool: bool) -> None:
    doors = _read_table(data_dir / r"C:\Users\popovyeh\OneDrive - adidas\Documents\hype_allocation\hype_allocation\doors.xlsx")
    articles = _read_table(data_dir / r"C:\Users\popovyeh\OneDrive - adidas\Documents\hype_allocation\hype_allocation\articles.xlsx")
    eligibility = _read_table(data_dir / r"C:\Users\popovyeh\OneDrive - adidas\Documents\hype_allocation\hype_allocation\eligibility.xlsx")
    supply = _read_table(data_dir / r"C:\Users\popovyeh\OneDrive - adidas\Documents\hype_allocation\hype_allocation\supply.xlsx")
    heat = _read_table(data_dir / r"C:\Users\popovyeh\OneDrive - adidas\Documents\hype_allocation\hype_allocation\heat.xlsx")
    tier_cap_runs = _read_table(data_dir / r"C:\Users\popovyeh\OneDrive - adidas\Documents\hype_allocation\hype_allocation\tier_cap_runs.xlsx")
    tier_capacity = _read_table(data_dir / r"C:\Users\popovyeh\OneDrive - adidas\Documents\hype_allocation\hype_allocation\tier_capacity.xlsx")

    data = allocation_data_from_tables(
        doors=doors,
        articles=articles,
        eligibility=eligibility,
        supply=supply,
        heat=heat,
        tier_cap_runs=tier_cap_runs,
        tier_capacity=tier_capacity,
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
