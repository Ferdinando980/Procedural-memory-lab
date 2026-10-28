<h1 align="center">Procedural Memory Lab</h1>

<p align="center">Do small language models get better by retrieving procedures, or do they just see a similar answer again?</p>

<p align="center"><b>English</b> · <a href="README.it.md">Italiano</a></p>

<p align="center"><img src="docs/images/cognitive-city.gif" width="760" alt="A quest replayed in Cognitive City"></p>

<p align="center"><sub>One quest replayed in Cognitive City. Four agents get the same bug at home. The two that use retrieval stop at the library first, then everyone writes a solution at the shop and runs the tests at the hospital.</sub></p>

## What this is

An independent research project. I wanted to know if a cheaper model can get closer to a larger one when it can look up what was learned in earlier attempts, and how to tell real learning from plain copying.

The test bed is small on purpose: Python functions with real bugs, checked by `pytest`. Every task is run four ways.

| Configuration | Solver | Extra context |
|---|---|---|
| A, Expert | larger model | none |
| B, Small | smaller model | none (the baseline) |
| F, Skill Library | smaller model | a general procedure retrieved from the library |
| C, Solution Bank | smaller model | a correct solution to a similar case |

F against B tells me if retrieval helps. F against C tells me why: if the procedure generalises, F should hold up where a copied answer would not.

## What I found

In the first five complete runs the Skill Library finished ahead of the small baseline every time, with 7.8 points more accuracy over 116 attempts. That is encouraging and nothing more. The runs are not clean replications, the library changed along the way, and the gain is uneven between skills. In the biggest early run only two of ten covered patterns paid off.

The most useful result was a check, not a score. A skill about floating point comparison seemed to pick a tolerance, but it could have been repeating a number written in the procedure. I changed that number and the answer followed 12 times out of 12. Changing an unrelated number did nothing, 6 out of 6. The model was choosing the right rule and then reciting one value from it. After I rewrote the procedure to ask for a derivation, it computed tolerances across seven orders of magnitude.

<p align="center"><img src="docs/images/epsilon-lab.png" width="760" alt="The tolerance check"></p>

## How it is organised

- `domain/` has the tasks, the bug families and the checks.
- `agents/` builds the prompt and runs the solver.
- `librarian/` retrieves, budgets and compares procedures.
- `cheater/` is the solution bank.
- `experiment/` runs the configurations side by side.
- `verification/` holds the checks that tell learning from copying.
- `city/` turns a finished run into the page shown above.
- `library/books/` is the procedure library.

The RPG names (Quest, Book, Librarian) are only labels for ordinary ideas: tasks, stored procedures and retrieval.

## Run it

You need Python 3.11 or newer. Install the dependencies from the parent workspace and run the commands from the folder that contains `cognitive_rpg`, so the package can be imported.

```sh
python -m pip install -r requirements.txt
python -m cognitive_rpg.settings_wizard
python -m cognitive_rpg.experiment.experiment_0
```

For development there are mock adapters that need no paid calls. Real runs need provider keys, which the setup asks for and never stores in the repository.

## Status

Ongoing, and not a peer reviewed paper. The raw run logs are not part of this public repository, so the numbers above are my own reading of them.

## License

Copyright © 2026 Ferdinando Gregorio Fernandez. All rights reserved. The source is visible for portfolio and research evaluation. Reuse, redistribution and derivative works are not permitted. See [LICENSE](LICENSE).
