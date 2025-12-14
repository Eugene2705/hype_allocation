# Full-run Drop Allocation (SKU × Size)

Python/Gurobi implementation of the MILP described in the allocation spec. The
model maximizes tier × heat score while enforcing eligibility, supply caps, and
anti-concentration rules per door and size.

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

## Modeling notes

* **Objective**: maximize \(\sum_{d,s} runs_{d,s} \times Score_{d, z(s)}\).
* **Eligibility + cap**: \(runs_{d,s} \le Eligible_{d,s} \times MaxRuns_{s,z(s)}\).
* **Supply**: \(\sum_d runs_{d,s} \le Supply_{s, z(s)}\).
* **Anti-concentration**: for each door/size, \(\sum_{s: z(s)=z} h(s)\, runs_{d,s} \le CapRuns_z\).
* **Integrality**: runs are integer and non-negative.
* **Optional**: ``min_runs`` can enforce a floor per door/SKU.

Use ``AllocationModel.add_solution_pool()`` before calling ``optimize`` to gather
alternative solutions for stakeholder review.
