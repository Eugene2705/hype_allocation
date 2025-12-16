# Full-run Drop Allocation (SKU × Size)

Python/Gurobi implementation of the MILP described in the latest stakeholder
specification. The model maximizes a tier × heat score and enforces eligibility,
SKU×size supply, and anti-concentration caps by door tier.

## Quick start (interactive)

For a notebook or REPL workflow, create the input container, build the model,
and then call the reporting helpers to review allocations and constraint
drivers:

The library exposes two primary entry points:

* ``allocation_model.build_allocation_model`` to construct the MILP using
  structured data inputs.
* ``run_allocation.py`` CLI to load Excel tables, solve the model, and export
  stakeholder-ready CSVs (runs + shipped units and constraint slacks).

## Loading data tables

The CLI keeps data loading separate from this README. Prepare Excel files with
the following schemas (column names must match):

* ``doors.xlsx``: ``door``, ``tier``
* ``articles.xlsx``: ``sku``, ``size``
* ``eligibility.xlsx``: ``door``, ``sku``, ``eligible`` (0/1)
* ``supply.xlsx``: ``sku``, ``size``, ``supply_units`` (units available for that size), ``ratio`` (units per run)
* ``heat.xlsx``: ``sku``, ``heat``
* ``tier_cap_runs.xlsx``: ``tier``, ``heat``, ``max_runs``, ``score``
* ``tier_capacity.xlsx``: ``tier``, ``cap_runs_total``

All ``heat`` values must be categorical (e.g., "Hype") and align with the
``heat`` keys present in ``tier_cap_runs.xlsx`` so scores and caps can be looked
up without defaults.

The repository includes an empty ``data/`` directory so you can drop your Excel
inputs in-place. By default, the CLI reads from that folder without extra
arguments, keeping ingestion self-contained within the cloned repo.

Save those Excel files under the repository's ``data/`` directory (the CLI
defaults to that location) and run:

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

Use ``AllocationModel.add_solution_pool()`` before calling ``optimize`` to gather
alternative solutions for stakeholder review.
