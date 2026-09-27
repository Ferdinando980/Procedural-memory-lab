<p align="center">🧠</p>

<h1 align="center">Procedural Memory Lab</h1>

<p align="center">An experimental case study on whether small language models improve by retrieving procedures — or merely by seeing similar answers again.</p>

<p align="center"><b>English</b> · <a href="README.it.md">Italiano</a></p>

![A completed experiment in Cognitive City](docs/images/experiment-city.png)

## The question

Can a cheaper language model move closer to a larger model on a real task when it can retrieve knowledge written during earlier attempts?

That question is easy to answer badly. If a model improves after retrieval, it may have learned a reusable method — or it may simply be copying a nearby example. This project was built to separate those explanations instead of treating any accuracy gain as learning.

The test bed is deliberately concrete: Python functions with real bugs and deterministic `pytest` oracles. The same task is attempted under four configurations:

| Configuration | Solver | Additional context |
|---|---|---|
| A — Expert | larger model | none |
| B — Small | smaller model | none; the baseline |
| F — Skill Library | smaller model | a retrieved general procedure |
| C — Solution Bank | smaller model | a correct solution to a similar case |

Comparing F with B measures whether retrieval helps. Comparing F with C asks the more important question: did the procedure generalise, or was a previous answer enough?

## What the experiment records

Every run keeps the task split (`KNOWN`, `VARIANT`, `NOVEL`), retrieval coverage, model cost, latency, token use, verifier result and the exact stage events needed to reproduce the reported number. Reports are generated from those logs rather than rewritten from memory.

Across the first five complete runs, the Skill Library finished ahead of the small-model baseline in all five. Aggregated accuracy improved by 7.8 percentage points over 116 attempts. That is encouraging, not conclusive: the runs are not clean independent replications, the library changed between some runs, and the benefit is uneven across mechanisms.

The uncomfortable results stay in the repository too. In the largest early run, only two of ten covered patterns were positive under the project's cost/accuracy classification. A library can improve the headline score and still fail to justify most of its individual entries.

## The causal check

The most useful result was methodological. A floating-point skill appeared to choose a tolerance, but it might have been repeating a constant. I changed that constant inside the retrieved procedure and observed the answer move with it: 12/12 times. Changing an irrelevant constant had no effect: 6/6 times.

The model was selecting the right rule but reciting a slot inside it. Rewriting the procedure to require a derivation made it calculate tolerances across seven orders of magnitude. The limitation was not simply model capacity; it was what the instruction made explicit.

![The causal tolerance investigation](docs/images/epsilon-lab.png)

## How it is built

- `domain/` defines tasks, bug families and deterministic verification.
- `agents/` builds the prompt and runs the solver.
- `librarian/` retrieves, budgets, compares and cautiously optimises procedures.
- `cheater/` provides the solution-bank comparison.
- `experiment/` runs matched configurations, checkpoints work and writes evidence.
- `verification/` contains causal probes, holdouts, recovery tests and consistency checks.
- `city/` turns completed evidence into the HTML views shown above.
- `logs/` preserves raw events and generated reports for each run.

The architecture uses RPG names such as Quest, Book and Librarian. They are navigation labels over ordinary retrieval, procedural memory and model-routing concepts, not claims about a game.

## Run it

Requirements: Python 3.11 or newer. Install the dependencies from the parent workspace, then run from that parent so the `cognitive_rpg` package is importable.

```sh
python -m pip install -r requirements.txt
python -m cognitive_rpg.settings_wizard
python -m cognitive_rpg.experiment.experiment_0
```

Mock adapters are available for development without paid model calls. Real runs require provider credentials configured through the wizard; secrets are not stored in this repository.

## From controlled experiment to real use

## Status

This is an ongoing independent research project, not a peer-reviewed paper and not a production framework. Results are presented as case-study evidence with their limitations, raw logs and corrections visible.

## License

Copyright © 2026 Ferdinando Gregorio Fernandez. All rights reserved. The source is visible for portfolio and research evaluation; reuse, redistribution and derivative works are not permitted. See [LICENSE](LICENSE).
