# Full-run Drop Allocation (SKU × Size)

Python/Gurobi implementation of the MILP described in the latest stakeholder
specification. The model maximizes a tier × heat score and enforces eligibility,
SKU×size supply, and anti-concentration caps by door tier.
Python/Gurobi implementation of the MILP described in the allocation spec. The
model maximizes tier × heat score while enforcing eligibility, supply caps, and
anti-concentration rules per door and size.

## Quick start (interactive)

For a notebook or REPL workflow, create the input container, build the model,
and then call the reporting helpers to review allocations and constraint
drivers:

The library exposes two primary entry points:

* ``allocation_model.build_allocation_model`` to construct the MILP using
  structured data inputs.
* ``run_allocation.py`` CLI to load CSV tables, solve the model, and export
  stakeholder-ready CSVs (runs + shipped units and constraint slacks).

## Loading data tables

The CLI keeps data loading separate from this README. Prepare CSV exports with
the following schemas (column names must match):

* ``doors.csv``: ``door``, ``tier``
* ``articles.csv``: ``sku``, ``size``
* ``eligibility.csv``: ``door``, ``sku``, ``eligible`` (0/1)
* ``supply.csv``: ``sku``, ``size``, ``supply_units`` (units available for that size), ``ratio`` (units per run)
* ``heat.csv``: ``sku``, ``heat``
* ``tier_cap_runs.csv``: ``tier``, ``heat``, ``max_runs``, ``score``
* ``tier_capacity.csv``: ``tier``, ``cap_runs_total``

All ``heat`` values must be categorical (e.g., "Hype") and align with the
``heat`` keys present in ``tier_cap_runs.csv`` so scores and caps can be looked
up without defaults.
```python
import gurobipy as gp

from allocation_model import AllocationData, build_allocation_model

## Quick start

```python
import gurobipy as gp
import pandas as pd

from allocation_model import (
    AllocationData,
    allocation_data_from_tables,
    build_allocation_model,
)

# Toy inputs (replace with your data sources)
data = AllocationData(
    doors=["D1", "D2"],
    sizes=["S", "M"],
    skus=["SKU1", "SKU2"],
    sku_size={"SKU1": "S", "SKU2": "M"},
    score={("D1", "S"): 10, ("D1", "M"): 8, ("D2", "S"): 9, ("D2", "M"): 7},
    eligible={("D1", "SKU1"): 1, ("D1", "SKU2"): 1, ("D2", "SKU1"): 1, ("D2", "SKU2"): 0},
    supply={("SKU1", "S"): 5, ("SKU2", "M"): 3},
    max_runs={("SKU1", "S"): 3, ("SKU2", "M"): 2},
    cap_runs={"S": 10, "M": 10},
    heat={"SKU1": 1.0, "SKU2": 1.2},
)

allocation = build_allocation_model(data)
allocation.optimize()

print(allocation.summarize_allocations())
print(allocation.constraint_slacks())
```

This keeps computation in Python while the README stays purely descriptive.

## Loading data tables

The repository includes a runnable script to keep data loading and output
creation separate from this README. Prepare CSV exports with the following
schemas:

* ``score``: columns ``door``, ``size``, ``score``
* ``eligibility``: columns ``door``, ``sku``, ``eligible`` (0/1)
* ``supply``: columns ``sku``, ``size``, ``supply``, ``max_runs``
* ``cap_runs``: columns ``size``, ``cap_runs``
* ``heat``: columns ``sku``, ``heat`` (mapping is also accepted)
* ``min_runs`` (optional): columns ``door``, ``sku``, ``min_runs``

Save those files in a directory (for example ``data/``) and run:

```bash
python run_allocation.py --data-dir data --output-prefix outputs/allocation
```

The script handles reading the tables, building and optimizing the model, and
writing two CSVs:

* ``<output-prefix>_allocations.csv`` — door/SKU runs, units, ratio, score, heat,
  and total shipped units per door/size
* ``<output-prefix>_slacks.csv`` — constraint slacks to explain bottlenecks

## Reviewing results

* ``summarize_allocations()`` returns one row per door/SKU with the run count,
  shipped units (via ``ratio``), tier/heat score, and heat coefficient so you
  can share the allocation in a flat table with stakeholders.
* ``<output-prefix>_allocations.csv`` — door/SKU runs, ratios, score, and heat
* ``<output-prefix>_slacks.csv`` — constraint slacks to explain bottlenecks

# Stakeholder-friendly table
rows = allocation.summarize_allocations()
for row in rows:
    print(row)

# Constraint slack report (useful for explaining bottlenecks)
slacks = allocation.constraint_slacks()
```

## Loading data tables

If your inputs live in CSV/Excel, read them with pandas and turn them into an
``AllocationData`` in one step:

```python
score = pd.read_csv("score.csv")           # columns: door,size,score
eligibility = pd.read_csv("eligibility.csv")  # columns: door,sku,eligible
supply = pd.read_csv("supply.csv")         # columns: sku,size,supply,max_runs
cap_runs = pd.read_csv("cap_runs.csv")     # columns: size,cap_runs
heat = pd.read_csv("heat.csv")             # columns: sku,heat
min_runs = pd.read_csv("min_runs.csv")     # optional columns: door,sku,min_runs

data = allocation_data_from_tables(
    score=score,
    eligibility=eligibility,
    supply=supply,
    cap_runs=cap_runs,
    heat=heat,
    min_runs=min_runs,
)

allocation = build_allocation_model(data)
allocation.optimize()

print(pd.DataFrame(allocation.summarize_allocations()))
```

## Reviewing results

* ``summarize_allocations()`` returns one row per door/SKU with the run count,
  supply ratio, tier/heat score, and heat coefficient so you can share the
  allocation in a flat table with stakeholders.
* ``constraint_slacks()`` reports the slack for supply, eligibility, and
  anti-concentration constraints to highlight what limited each decision.
* ``add_solution_pool()`` can be called before optimization if you want
  alternative allocations (set ``PoolSolutions`` to a higher number if needed).

### Output calculation (runs → units)

The solver decides ``runs[door, sku]`` as integer full size-runs. The
allocation export derives shipped units using the provided ``ratio[sku, size]``:

* ``units[door, sku, size] = ratio[sku, size] * runs[door, sku]``
* ``door_size_units[door, size]`` aggregates shipped units over all SKUs of that
  size for the door.

## Modeling notes

* **Objective**: maximize \(\sum_{d,s} runs_{d,s} \times Score_{tier(d), heat(s)}\).
* **Eligibility + cap**: \(runs_{d,s} \le Eligible_{d,s} \times MaxRuns_{tier(d), heat(s)}\).
* **Supply**: \(\sum_d ratio_{s,z} \times runs_{d,s} \le Supply_{s,z}\) for every SKU×size (units capped using the fixed size-curve ratios).
* **Anti-concentration**: \(\sum_s runs_{d,s} \le CapRunsTotal_{tier(d)}\).
* **Integrality**: runs are integer and non-negative.
## Modeling notes

* **Objective**: maximize \(\sum_{d,s} runs_{d,s} \times Score_{d, z(s)}\).
* **Eligibility + cap**: \(runs_{d,s} \le Eligible_{d,s} \times MaxRuns_{s,z(s)}\).
* **Supply**: \(\sum_d runs_{d,s} \le Supply_{s, z(s)}\).
* **Anti-concentration**: for each door/size, \(\sum_{s: z(s)=z} h(s)\, runs_{d,s} \le CapRuns_z\).
* **Integrality**: runs are integer and non-negative.
* **Optional**: ``min_runs`` can enforce a floor per door/SKU.

Use ``AllocationModel.add_solution_pool()`` before calling ``optimize`` to gather
alternative solutions for stakeholder review.
