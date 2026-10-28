<h1 align="center">Procedural Memory Lab</h1>

<p align="center">Does a small language model get better by retrieving a procedure, or does it only need to see a similar answer again?</p>

<p align="center"><b>English</b> · <a href="README.it.md">Italiano</a></p>

<p align="center"><img src="docs/images/cognitive-city.gif" width="880" alt="A quest replayed in Cognitive City"></p>

<p align="center"><sub>One quest replayed in Cognitive City, the page that turns a finished run into a small town. The four agents (NPC-A, B, C and F) get the same bug at <i>Casa</i>, the house. C and F stop at the <i>Biblioteca</i>, the library, to look something up (<i>Sto imparando!</i>, "I am learning!"). Then every agent writes a solution at the <i>Negozio</i>, the shop, and runs the tests at the <i>Ospedale</i>, the hospital, before going home with <i>Missione riuscita</i>.</sub></p>

## The question

Can a cheap model get close to an expensive and powerful one on a real task, if it can read knowledge that was written down earlier? And the part that matters more: does that knowledge have to be a general procedure, or is it enough to have shown the model a similar solution once?

The second question is the hard one. A system that seems to learn may just be fetching answers it has already seen. It copies, it does not generalise, and you cannot tell the two apart by counting how many problems it solves. The difference has to be isolated on purpose, with an experiment designed to make it visible.

The vocabulary in the code (Quest, Book, NPC, Librarian) is borrowed from role playing games. It is only a handy label for standard ideas: retrieval, procedural memory and routing between models.

## The test bed: one bug, four ways to attack it

Every task, a quest, is a Python function with a real bug. The verdict is never a matter of opinion. I run `pytest` in a separate subprocess, so a language model never judges another language model and the checker can never be the same thing as the thing being checked.

The same bug goes to four agents with exactly the same base prompt.

| Config | Who solves it | What it also gets | What it should show |
|---|---|---|---|
| **A, Expert** | large, expensive model | nothing | what it would cost to do it well every time |
| **B, Small** | cheap model | nothing | what the bare model is worth, the real baseline |
| **F, Small + Skill Library** | cheap model | a procedure written after an earlier attempt: general, not tied to one case | whether a reusable procedure helps |
| **C, Small + Solution Bank** | cheap model | a correct solution to a similar problem seen before: an example, not a rule | whether having seen a similar case is enough |

C is the piece that is missing from most talk about skill libraries. If F beats B it is tempting to say the library teaches something general. But if C beats B by about the same amount, that gain may have nothing to do with a procedure: having seen a similar case would be enough. Comparing F with C, and not only with B, is the only way to tell the two stories apart.

One honest detail. The earlier solution handed to C is the reference function from the bug catalogue, not a real transcript written by Expert. It is a reasonable stand-in, since Expert usually solves 95 to 100 percent of the cases, but it is not the same thing and I say so here.

## How a run is judged

Each bug belongs to one split:

- **KNOWN** is the canonical example of a bug pattern that a skill or a solution already covers.
- **VARIANT** is the same pattern with a different problem, which tests generalisation.
- **NOVEL** is a pattern that is never covered, on purpose. For three patterns I never write a skill or a solution, so there is always a permanent control group.

Every retrieval, for F and for C, also records its coverage: `NONE` when nothing relevant was found, `FULL` for an exact match, and `PARTIAL` for C when the solution belongs to a different problem of the same family.

I track the two things apart because they answer different questions. If F with nothing found behaves like B, but F with an exact match does better, then it is the retrieved content that moves the needle and not the mere presence of a retrieval mechanism. That gives two numbers:

- **Delta Retrieval** is the accuracy with `FULL` coverage minus the accuracy with `NONE`, inside the same config. It says how much finding something matters.
- **Delta Architecture** is the accuracy of the config with `FULL` coverage minus the accuracy of B. It says how far the whole architecture beats the bare model when retrieval actually works.

For every attempt I also keep cost, latency, token use and the `pytest` verdict, and the reports are built from those records and not from memory.

## Recitation or derivation: the causal check

The most interesting result so far is not an accuracy number. It is a way of not being fooled by a correlation.

While looking into the skill `floating_point_equality`, which teaches how to pick a tolerance (an epsilon) instead of comparing decimal numbers for exact equality, I got suspicious. On a task with no numeric hints, F always answered `1e-9`. Either the model was reasoning about the scale of the problem, or it was mechanically repeating a constant written inside the skill. Watching the correlation cannot separate the two, so I ran a causal test: I changed the constant in the skill directly (`1e-9`, then `2.5e-6`, then `7e-4`) and checked whether the answer moved with it.

- It did, 12 times out of 12, on two unrelated tasks.
- Changing a constant in a different section of the skill, the one about currency, had no effect at all, 6 times out of 6, and the reverse change had none either.

So the model picked the right rule and then copied a number from inside it. It was not deriving the epsilon from the scale of the problem. That is a literal substitution of one precise slot, not a vague habit of quoting examples.

That could have closed the matter, but I rewrote the skill to ask for a derivation instead of a fixed constant, and the model started to derive. It followed the size of the problem across seven orders of magnitude, with a single minor arithmetic slip. The bottleneck was not a missing ability of the model. It was the content of the instruction.

A clean confirmation came on a genuinely different domain, significant digits in a decimal comparison. There the model produced two different epsilons in the same test, each correct for its own decimal structure. Mechanical substitution cannot produce two different correct numbers, and only a real derivation can.

The test lives in `experiment/canary.py`. It uses synthetic tasks that neither the optimiser nor the skill generator ever saw, because otherwise the skill would be written to pass the test, which is the opposite of measuring it. A readable version of the model's answers, transcribed by hand and not regenerated, was kept as a small page.

<p align="center"><img src="docs/images/epsilon-lab.png" width="760" alt="The tolerance check, page view"></p>

## What the five complete runs show

| Run | n | A (Expert) | B (Small) | F (Skill Library) | C (Solution Bank) | F vs B |
|---|---|---|---|---|---|---|
| 1 | 26 | 100.0% | 88.5% | 96.2% | 92.3% | +7.7 |
| 2 | 21 | 95.2% | 95.2% | 100.0% | not run | +4.8 |
| 3 | 26 | 96.2% | 84.6% | 96.2% | 96.2% | +11.5 |
| 4 | 4 | 50.0% | 50.0% | 75.0% | 50.0% | +25.0 |
| 5 | 39 | 97.4% | 92.3% | 97.4% | 97.4% | +5.1 |

F beat B in all five complete runs, never tied and never lost: 7.8 percentage points over 116 attempts in total. Run 4 has four tasks only, so its +25 is mostly noise. The very first run I ever did on this project, smaller and older than any above, showed no benefit. It stayed for a while as the only written conclusion even after the later runs had contradicted it, not because I hid it but because nobody had checked again. I did not erase it from the history. It is just no longer the right conclusion.

Two real limits, not buried under the table.

**These are not clean independent replications.** The runs share most of the same task catalogue, and between runs the optimiser compressed and re-verified the existing skills. Part of F's advantage may reflect a library that sharpens itself on these specific tasks and not generalisation to tasks it never saw.

**The gain is not uniform, mechanism by mechanism.** In the most complete run (the last one, n=39) the Delta Retrieval of F is negative, minus 3.2 points, while the one of C is zero and never negative. The retrieval mechanism does not help in the same way in every config, even when the final accuracy is identical.

On cost, F pays on average between 116 and 343 extra input tokens compared with B to use a skill that is already built. That is the retrieval overhead, and it changes from run to run depending on which skills are retrieved. Building a new skill, which means the optimiser compressing and re-verifying it, costs around 1000 to 2000 tokens once per pattern. Each run report computes a breakeven per pattern, meaning after how many uses the building cost pays back compared with always calling Expert. It also sorts patterns three ways: `ECONOMICALLY_POSITIVE` when it pays in tokens, `ACCURACY_POSITIVE` when it does not pay in tokens but solved something A or B did not, and `NEGATIVE` otherwise. Negative does not mean throw the skill away, since with numbers this small it can have value the two metrics do not capture. In the most complete run, of 10 covered patterns one is economically positive and one is accuracy positive. The other eight are negative. That is an uncomfortable figure and it is more honest to show it than to hide it.

The raw run logs are not part of this public repository, so these numbers are my own reading of them.

## From a controlled experiment to real use

The same ideas were later carried over by hand into Aria, a study app I built for a real user with ADHD. It is not a product for sale. It is the second testing ground for the same question, with real behaviour data instead of synthetic tasks. The two projects stay separate on purpose, and nothing is shared between them at the code level.

Moving from a synthetic setting to a real person changed some choices.

- Skills are no longer generated automatically from conversations. A skill exists only when someone creates it on purpose.
- Text written by the user is never rewritten silently. The only shortening allowed can be undone, and it is kept only if an independent second check confirms that the goal and the success criterion are still intact.
- Not every instruction is a procedure. Only a method, with an expected result and a success criterion, can be judged right or wrong by an outcome. A preference or a binding rule is not right or wrong in that sense.

Real use also changes how you measure. In the experiment I can force half of the cases onto F and half onto B. In the app, the system decides by itself when a skill is relevant, and that biases the sample, so the evidence comes in two strengths. Comparing groups on ordinary use is weak by construction, because the requests that trigger a skill tend to be easier than the rest. The strong version is a blind paired comparison: the same real request answered twice, once with skills and once without, and judged without knowing which is which.

What came out of it so far, with its caveats.

- The causal check described above was reused on eight self-checking mechanisms that verify the model's output independently of what the model says about it. Each one was validated on a known case plus a direct manipulation before it went into use. They all remain candidates: verified once, but not yet watched for long enough in real use.
- On a local Gemma model I compared a behaviour retrieval mechanism against the bare prompt on 22 comparable pairs, judged by the same validators used in production. The result was 17 of 22 (77%) against 13 of 22 (59%). Almost all of the advantage sits in one domain, honesty about the materials (6 of 9 against 2 of 9). On task decomposition and beginner explanations the two approaches are about even. It is one run per cell with no repetitions, so the direction agrees with this project but the exact number is not conclusive.
- A finding from here became a product rule. When writing a skill, name the awkward cases explicitly instead of trusting the model to generalise from a principle. That is the lesson of the tolerance check.

I also stopped one thing on purpose. Automatic sharing of skills between users does not carry over as it stands. A skill born from one person's use is tuned to that person, and it cannot be compared across people the way Python bugs can be compared in the synthetic domain. What real use can add to this research is lasting adaptation of a single agent over time. Knowledge transfer between agents is still tested only here.

## The road of a skill through the code

1. **Born.** `librarian/skill_generator.py` creates a `Book` with status `DRAFT`, or I write one by hand.
2. **Verified.** `librarian/optimizer.py` compresses and re-verifies a Book above a cost threshold, without ever overwriting the original. If the check passes, it saves a new version with status `VERIFIED`.
3. **Deduplicated.** `librarian/similarity.py` compares pairs of Books to see whether the library is piling up duplicates under different names, and `librarian/archive_duplicates.py` archives, never deletes, the superseded ones.
4. **Retrieved.** `librarian/librarian.py` routes by tag overlap, at zero cost and with no embedding calls, and produces a `SkillPackage`.
5. **Fitted to the budget.** `librarian/context_budget.py` enforces a real ceiling on the injected context, based on the model window and on a true token count, never an estimate.
6. **Put in the prompt.** `SkillPackage.as_prompt_context()` joins the text of the selected procedures.
7. **Used.** `agents/worker.py` builds the full prompt, calls the model and extracts the answer.
8. **Measured.** `experiment/events.py` logs every phase as JSONL, and the economics, recap, observer table and knowledge map modules turn those logs into readable reports, at no cost because they only read local files.

A `Book` is a procedure. These are its main fields.

| Field | Meaning |
|---|---|
| `id`, `version`, `title`, `domain` | identity, version and area |
| `problem_tags`, `capability_tags`, `resource_tags` | labels the Librarian uses to match by overlap |
| `procedure_text` | the text that actually goes into the prompt |
| `pattern_id` | the bug pattern the procedure answers |
| `status` | `DRAFT` when freshly generated, `VERIFIED` once the optimiser has re-checked it |
| `confidence`, `verification_count` | numeric trust, and how often and how it was re-verified |
| `derived_from`, `supersedes`, `superseded_by` | genealogy: what it was compressed from and the chain of versions |
| `duplicate_of` | another Book judged to be a duplicate by the similarity checker |
| `generation_method` | `manual`, `compression` or `skill_generator` |

## How the repository is organised

- `domain/` has the tasks, the bug families and the deterministic checks.
- `agents/` builds the prompt and runs the solver.
- `librarian/` retrieves, budgets, compares and carefully optimises procedures.
- `cheater/` is the solution bank used by config C.
- `experiment/` runs the matched configurations, checkpoints the work and writes the evidence.
- `verification/` holds the causal probes, the holdouts, the recovery tests and the consistency checks.
- `city/` turns a finished run into the Cognitive City page shown above.
- `adapters/` connects the model providers, with mock adapters for development.
- `library/books/` is the library of procedures.

## Run it

You need Python 3.11 or newer. Install the dependencies from the parent workspace and run the commands from the folder that contains `cognitive_rpg`, so the package can be imported.

```sh
python -m pip install -r requirements.txt
python -m cognitive_rpg.settings_wizard
python -m cognitive_rpg.experiment.experiment_0
```

For development there are mock adapters that need no paid calls. Real runs need provider keys, which the setup asks for and never stores in the repository.

## Terms in one place

| Term | Meaning |
|---|---|
| Quest | one bug to solve, checked automatically with `pytest` |
| Book | one written procedure, the base unit of the skill library |
| Librarian | the component that routes the relevant skills, by tag overlap, at zero cost |
| Optimizer | compresses and re-verifies a skill and never overwrites the original |
| KNOWN, VARIANT, NOVEL | canonical example, same pattern with another problem, pattern never covered (the control) |
| Coverage | how much retrieval found: `NONE`, `PARTIAL` or `FULL` |
| DRAFT, VERIFIED | life cycle of a skill: freshly generated, then re-verified before it is trusted |

## Status

Ongoing, and not a peer reviewed paper. The results are case study evidence with their limits written next to them.

## License

Copyright © 2026 Ferdinando Gregorio Fernandez. All rights reserved. The source is visible for portfolio and research evaluation. Reuse, redistribution and derivative works are not permitted. See [LICENSE](LICENSE).
