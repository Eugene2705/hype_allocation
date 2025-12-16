#diff --git a/allocation_model.py b/allocation_model.py
#new file mode 100644
#index 0000000000000000000000000000000000000000..c085dca4c2b54ca1014587573892c56bcde84a82
#--- /dev/null
# b/allocation_model.py
#@@ -0,0 1,295 @@
#"""Gurobi MILP for drop allocation with full size-runs.
#
#This version follows the latest stakeholder specification, which requires the
#model to:

#* use door tiers and SKU heat to look up both the objective score and the
#  per-door/SKU ``max_runs`` cap,
#* enforce supply at the SKU×size level using size-curve ratios,
#* enforce an anti-concentration cap per door tier, and
#* convert full runs to shipped units using the provided ``ratio`` per
#  SKU×size in the exported allocation table.
#The module maximizes the tier/heat score while respecting eligibility, supply,
#and tier capacity constraints, then emits a stakeholder-friendly table of runs
#and units.
#"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple, TYPE_CHECKING

import gurobipy as gp
from gurobipy import GRB

if TYPE_CHECKING:  # pragma: no cover - for static type checking only
    import pandas as pd


Door = str
SKU = str
Size = str


@dataclass(frozen=True)
class AllocationData:
    """Container for the allocation model inputs.

    Attributes:
        doors: Unique door identifiers (store IDs).
        sizes: Available sizes (e.g., numeric or "S/M/L").
        skus: SKU identifiers being allocated.
        door_tier: Mapping from door to its tier ``tier(d)``.
        sku_sizes: Mapping from SKU to the list of sizes in its fixed run curve.
        eligible: Eligibility flag ``Eligible[d, s]`` (1 if door can receive SKU).
        heat: Heat mapping ``heat(s)`` for each SKU.
        score: Score lookup ``Score[tier(d), heat(s)]``.
        max_runs: Max full runs ``MaxRuns[tier(d), heat(s)]`` per door/SKU.
        supply_units: Size-level unit supply ``Supply[s, z]`` per SKU×size.
        ratio: Units-per-run ratio ``ratio[s, z]`` used for output units and supply.
        cap_runs_total: Anti-concentration cap per tier ``CapRunsTotal[tier]``.
    """

    doors: Sequence[Door]
    sizes: Sequence[Size]
    skus: Sequence[SKU]
    door_tier: Mapping[Door, str]
    sku_sizes: Mapping[SKU, Sequence[Size]]
    eligible: Mapping[Tuple[Door, SKU], int]
    heat: Mapping[SKU, str]
    score: Mapping[Tuple[str, str], float]
    max_runs: Mapping[Tuple[str, str], int]
    supply_units: Mapping[Tuple[SKU, Size], int]
    ratio: Mapping[Tuple[SKU, Size], float]
    cap_runs_total: Mapping[str, float]


class AllocationModel:
    """Wrapper around the MILP and its primary variables."""

    def __init__(self, model: gp.Model, runs: gp.tupledict, data: AllocationData):
        self.model = model
        self.runs = runs
        self.data = data

    def optimize(self, **kwargs) -> int:
        """Optimize the model and return the Gurobi status code."""
        for param, value in kwargs.items():
            self.model.setParam(param, value)
        self.model.optimize()
        return self.model.Status

    def summarize_allocations(self, tolerance: float = 1e-6) -> List[Dict[str, object]]:
        """Return allocations in a stakeholder-friendly table.

        Args:
            tolerance: Minimum run quantity to include in the output.

        Returns:
            List of dict rows with door, SKU, size, runs, ratio, score, and heat.
        """
        if self.model.SolCount == 0:
            raise ValueError("Model has no solution to summarize.")

        rows: List[Dict[str, object]] = []
        units_by_door_size: Dict[Tuple[Door, Size], float] = {}

        for door in self.data.doors:
            for sku in self.data.skus:
                value = self.runs[door, sku].X
                if value <= tolerance:
                    continue
                heat = self.data.heat[sku]
                tier = self.data.door_tier[door]
                score = self.data.score[(tier, heat)]
                for size in self.data.sku_sizes[sku]:
                    ratio = self.data.ratio[(sku, size)]
                    units = ratio * value
                    units_by_door_size[(door, size)] = units_by_door_size.get((door, size), 0.0) + units
                    rows.append(
                        {
                            "door": door,
                            "sku": sku,
                            "size": size,
                            "runs": value,
                            "ratio": ratio,
                            "units": units,
                            "score": score,
                            "heat": heat,
                        }
                    )

        for row in rows:
            row["door_size_units"] = units_by_door_size[(row["door"], row["size"])]
        return rows

    def add_solution_pool(self) -> None:
        """Enable solution pool to capture alternatives for stakeholder review."""
        self.model.setParam("PoolSearchMode", 2)
        self.model.setParam("PoolSolutions", 10)

    def constraint_slacks(self) -> List[Dict[str, object]]:
        """Expose constraint slacks to explain limiting factors."""
        if self.model.SolCount == 0:
            raise ValueError("Model has no solution; optimize first.")

        rows: List[Dict[str, object]] = []
        for constr in self.model.getConstrs():
            rows.append(
                {
                    "name": constr.ConstrName,
                    "slack": constr.Slack,
                    "rhs": constr.RHS,
                    "sense": constr.Sense,
                }
            )
        return rows

def build_allocation_model(data: AllocationData, model_name: str = "full_run_allocation") -> AllocationModel:
    """Construct the MILP defined in the tier/heat specification.

    Components:
    * Decision variables ``runs[d, s]``: integer full runs of SKU ``s`` to door ``d``.
    * Objective: maximize ``sum runs[d, s] * Score[tier(d), heat(s)]``.
    * Constraints:
        1. Eligibility  cap: ``runs[d, s] <= Eligible[d, s] * MaxRuns[tier(d), heat(s)]``.
        2. Supply: ``sum_d ratio[s, z] * runs[d, s] <= Supply[s, z]`` for each SKU×size.
        3. Anti-concentration: ``sum_s runs[d, s] <= CapRunsTotal[tier(d)]``.
        4. Integrality and non-negativity: runs are integer full runs.
    """

    model = gp.Model(model_name)

    runs = model.addVars(
        list(data.doors),
        list(data.skus),
        name="runs",
        vtype=GRB.INTEGER,
        lb=0,
    )

    # Objective
    model.setObjective(
        gp.quicksum(
            runs[door, sku]
            * data.score[(data.door_tier[door], data.heat[sku])]
            for door in data.doors
            for sku in data.skus
        ),
        GRB.MAXIMIZE,
    )

    # Eligibility and per-door per-SKU cap
    for door in data.doors:
        for sku in data.skus:
            tier = data.door_tier[door]
            heat = data.heat[sku]
            cap = data.eligible.get((door, sku), 0) * data.max_runs[(tier, heat)]
            model.addConstr(
                runs[door, sku] <= cap,
                name=f"eligibility[{door},{sku}]",
            )

    # Supply feasibility per SKU×size using fixed ratios
    for (sku, size), supply in data.supply_units.items():
        ratio = data.ratio[(sku, size)]
        model.addConstr(
            gp.quicksum(ratio * runs[door, sku] for door in data.doors) <= supply,
            name=f"supply[{sku},{size}]",
        )

    # Anti-concentration per door/size
    for door in data.doors:
        model.addConstr(
            gp.quicksum(runs[door, sku] for sku in data.skus)
            <= data.cap_runs_total.get(data.door_tier[door], GRB.INFINITY),
            name=f"cap_runs_total[{door}]",
        )

    model.update()
    return AllocationModel(model=model, runs=runs, data=data)


def allocation_data_from_tables(
    doors: "pd.DataFrame",
    articles: "pd.DataFrame",
    eligibility: "pd.DataFrame",
    supply: "pd.DataFrame",
    heat: "pd.DataFrame | Mapping[SKU, float]",
    tier_cap_runs: "pd.DataFrame",
    tier_capacity: "pd.DataFrame",
) -> AllocationData:
    """Build :class:`AllocationData` from tabular inputs (CSV/Excel).

    Expected shapes (column names must match):

    * ``doors``: ``door``, ``tier``
    * ``articles``: ``sku``, ``size``
    * ``eligibility``: ``door``, ``sku``, ``eligible`` (0/1)
    * ``supply``: ``sku``, ``size``, ``supply_units``, ``ratio``
    * ``heat``: ``sku``, ``heat`` (mapping accepted)
    * ``tier_cap_runs``: ``tier``, ``heat``, ``max_runs``, ``score``
    * ``tier_capacity``: ``tier``, ``cap_runs_total``
    """

    import pandas as pd  # Local import to keep pandas optional

    def _series_to_mapping(df: pd.DataFrame, key_cols: List[str], value_col: str):
        return {tuple(row[k] for k in key_cols): row[value_col] for row in df.to_dict("records")}

    doors_list = sorted(doors["door"].unique())
    skus = sorted(articles["sku"].unique())
    sizes = sorted(articles["size"].unique())

    sku_sizes: Dict[SKU, List[Size]] = {}
    for row in articles.to_dict("records"):
        sku_sizes.setdefault(row["sku"], []).append(row["size"])
    sku_sizes = {sku: sorted(set(sizes_for_sku)) for sku, sizes_for_sku in sku_sizes.items()}

    door_tier_map = doors.set_index("door")["tier"].to_dict()
    eligible_map = _series_to_mapping(eligibility, ["door", "sku"], "eligible")
    supply_units_map = _series_to_mapping(supply, ["sku", "size"], "supply_units")
    ratio_map = _series_to_mapping(supply, ["sku", "size"], "ratio")
    if isinstance(heat, Mapping):
        heat_map = {sku: str(value) for sku, value in heat.items()}
    else:
        heat_map = heat.set_index("sku")["heat"].astype(str).to_dict()
    max_runs_map = _series_to_mapping(tier_cap_runs, ["tier", "heat"], "max_runs")
    score_map = _series_to_mapping(tier_cap_runs, ["tier", "heat"], "score")
    cap_runs_total_map = tier_capacity.set_index("tier")["cap_runs_total"].to_dict()

    missing_heat = set(skus) - set(heat_map)
    if missing_heat:
        raise ValueError(f"Missing heat entries for SKUs: {sorted(missing_heat)}")

    expected_size_keys = {(sku, size) for sku, sizes_for_sku in sku_sizes.items() for size in sizes_for_sku}
    missing_supply = expected_size_keys - set(supply_units_map)
    if missing_supply:
        raise ValueError(f"Missing supply entries for SKU×size pairs: {sorted(missing_supply)}")

    tiers = set(door_tier_map.values())
    required_pairs = {(tier, heat_map[sku]) for sku in skus for tier in tiers}
    missing_score = required_pairs - set(score_map)
    missing_max_runs = required_pairs - set(max_runs_map)
    if missing_score:
        raise ValueError(f"Missing score entries for tier/heat pairs: {sorted(missing_score)}")
    if missing_max_runs:
        raise ValueError(f"Missing max_runs entries for tier/heat pairs: {sorted(missing_max_runs)}")

    if set(supply_units_map) != set(ratio_map):
        raise ValueError("Supply and ratio tables must share identical (sku, size) keys.")

    return AllocationData(
        doors=doors_list,
        sizes=sizes,
        skus=skus,
        door_tier=door_tier_map,
        sku_sizes=sku_sizes,
        eligible=eligible_map,
        heat=heat_map,
        score=score_map,
        max_runs=max_runs_map,
        supply_units=supply_units_map,
        ratio=ratio_map,
        cap_runs_total=cap_runs_total_map,
    )
