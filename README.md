<h1 align="center">Procedural Memory Lab</h1>

<p align="center">Does a small language model get better by retrieving a procedure, or does it only need to see a similar answer again?</p>

<p align="center"><b>English</b> · <a href="README.it.md">Italiano</a></p>

<p align="center"><img src="docs/images/cognitive-city.gif" width="880" alt="A quest replayed in Cognitive City"></p>

<p align="center"><sub>One quest replayed in Cognitive City, the page that turns a finished run into a small town. The four agents (NPC-A, B, C and F) get the same bug at <i>Casa</i>, the house. C and F stop at the <i>Biblioteca</i>, the library, to look something up (<i>Sto imparando!</i>, "I am learning!"). Then every agent writes a solution at the <i>Negozio</i>, the shop, and runs the tests at the <i>Ospedale</i>, the hospital, before going home with <i>Missione riuscita</i>.</sub></p>

## In short

- **The question.** Does a cheap model improve because it has a general procedure, or only because it has already seen a similar solution?
- **The reference result** (one clean run, 39 tasks). The small model alone solves 36, with a procedure 38, with the solution of a similar case 38, and those last two solved the same tasks. That is three failures recovered: a direction, not a statistically significant effect.
- **Reasoning or copying?** Changing a constant inside the procedure made the model's answer follow it 12 times out of 12. Asking it to derive the value instead, the model computed tolerances across seven orders of magnitude.
- **Is it always needed?** On 27 of the 31 tasks where the small model was given a procedure, it would have solved the task anyway.

## The question

Can a cheap model get close to a more powerful one if we let it retrieve knowledge written down earlier?

And above all: **does that knowledge have to be a general procedure, or is it enough to show it the solution of a similar problem?**

The second question is the one I really cared about.

A system that seems to learn may simply be remembering an answer. It may solve more problems, cost less and even look as if it reasons better. But which part of the improvement comes from the knowledge we gave it? And did that knowledge teach it a method, or did it hand it something to copy?

Counting successes is not enough to tell the two possibilities apart.

I built Procedural Memory Lab to try to separate them, with controlled experiments, an automatic checker and a comparison that is often missing when people talk about Skills: the one against a ready-made earlier solution.

Over time, though, the lab started to answer other questions as well.

**When is a procedure really useful? When is it only a cost? Can it even make a model worse when it would have solved the problem without help? And how do I know my test is measuring the right thing?**

These are questions that came out of the results, including the ones I did not expect.

The project borrows its vocabulary from role playing games: Quest, Book, NPC, Librarian. The names are a narrative choice; underneath there are ordinary problems of procedural memory, knowledge retrieval, evaluation and routing between models.

## One bug, four ways to attack it

Every Quest is a Python function with a bug introduced in the experimental catalogue.

The same request is given to four configurations. What changes is the model, or the extra knowledge it can consult.

| Configuration | Who solves it | What it receives |
|---|---|---|
| **A — Expert** | The more powerful model | No help |
| **B — Small** | The cheap model | No help |
| **F — Skill Library** | The same cheap model | A general procedure retrieved from the library |
| **C — Solution Bank** | The same cheap model | The correct solution of a similar problem |

B is the starting point: what can the model do on its own?

F tests whether a procedure written earlier can help it.

C raises the most important doubt: **what if the advantage of F had nothing to do with having a procedure?**

If F beats B, we know something improved. But if C gets the same result, we cannot attribute that improvement to procedural generalisation.

The comparison of F against C exists precisely to put this interpretation under pressure.

There is one limit to declare: the solution given to C is the catalogue's reference function, not an answer actually produced by Expert in an earlier run. It is a useful proxy, but it is not the same as a memory of real experiences.

### How do I check the answers?

I do not ask another language model to decide whether the code is correct.

The solution is run through `pytest`, in a separate subprocess, and gets a verifiable verdict.

This avoids leaving the judgement to the preference of another LLM. It does not make the checker infallible, though: tests can be incomplete or wrong too. During the research I found concrete examples of exactly that problem.

The tasks are also split into three groups:

- **KNOWN:** the canonical case of a pattern that is already covered.
- **VARIANT:** the same kind of error, in a different problem.
- **NOVEL:** a pattern the library never covers, used as a control.

For some NOVEL patterns a Skill is never created and no earlier solution is added.

When the Librarian retrieves something I also record the coverage: `NONE`, `FULL` or `PARTIAL`, the last one used for partial matches in the Solution Bank.

I do not only want to know whether F won. I want to know **what it was actually given when it won**.

## Do procedures really work?

The reference run is `experiment4`: 39 tasks, four configurations and 156 attempts.

It was executed in a single session, with one provider and one model per configuration: `gemini-3.7-flash` for Expert and `gemini-3.1-flash-lite` for Small.

| Configuration | Solved | Accuracy |
|---|---:|---:|
| A — Expert | 38/39 | 97.4% |
| B — Small | 36/39 | 92.3% |
| F — Skill Library | 38/39 | 97.4% |
| C — Solution Bank | 38/39 | 97.4% |

At first glance the result looks simple.

The small model, with a procedure, reaches Expert. But the one with an earlier solution reaches Expert too.

Here is the problem: **F and C solved exactly the same tasks**.

This run does not show that a general procedure is better than a concrete example.

F gained three wins over B, but lost one task on which a flawed test was identified. Leaving that case out, the comparison is three wins to none over 38 tasks. The exact McNemar test returns `p = 0.25`.

It is an interesting direction, not a statistically significant difference.

I do not want to turn three solved problems into a conclusion much bigger than the data allow.

### What about the earlier runs?

Before `experiment4` there are other numbered runs. I do not use them for any result: in some of them the provider or the model changed halfway through, one used a different Expert, another had only four tasks. I archived them as logs. They help reconstruct the history of the research, not support a conclusion.

The very first run, earlier still, showed no benefit.

For a while that conclusion stayed written down even after newer results. I did not remove it from the history: it simply was no longer enough to describe the project.

That is why today I keep the reference result, the exploratory observations and the later checks separate.

## Is the model reasoning or copying?

This is probably the finding that changed the most how I think about procedures.

I was studying `floating_point_equality`, a Skill that teaches how to avoid exact comparisons between decimal numbers by using a tolerance, called epsilon.

On a task with no numeric hints, the model always answered:

`1e-9`

But why that number?

It may have deduced that it was appropriate. Or it may simply have read it in the Skill and repeated it.

I decided to change the constant inside the procedure directly.

First `1e-9`, then `2.5e-6`, then `7e-4`.

**The model's answer followed the change 12 times out of 12**, on two unrelated tasks.

I also changed a constant in an unrelated section of the Skill, the one about currency. In that case nothing changed, 6 times out of 6.

The model was not copying just any number. It was selecting the relevant section and taking the value it found there.

Then I ran a second test.

Instead of supplying a fixed constant, I rewrote the procedure to ask the model to derive the tolerance from the scale of the problem.

The behaviour changed. The model started producing values that depended on the problem, across seven orders of magnitude, with a single arithmetic error observed.

In one case on significant digits it even produced two different epsilons in the same test, both correct for their own decimal structure.

This does not let us observe the model's internal processes directly. It does let us tell two behaviours apart: repeating a prescribed value and computing different values as a function of the inputs.

**The model was capable of producing the requested solution. The first instruction was steering it towards a more rigid behaviour.**

The check is implemented in `experiment/canary.py`, with synthetic tasks that were never used to build or optimise the Skills. A readable version of the model's answers, transcribed by hand and not regenerated, was kept as a small page.

<p align="center"><img src="docs/images/epsilon-lab.png" width="760" alt="The tolerance check, page view"></p>

## What if a Skill made things worse?

This is where the research took a direction I had not planned.

The idea of a general rule that is always available seems reasonable. If a procedure is useful, why not show it to the model even before it needs it?

I checked what happened with an always-on generic Skill. It is an exploratory observation, made with a local model (Gemma) and outside the reference run.

On the same 33 tasks:

| Condition | Successes |
|---|---:|
| Without the generic Skill | 28/33 — 84.8% |
| With the generic Skill | 21/33 — 63.6% |

In a later check, after removing that Skill, successes went back to 29/33.

It is a single execution per condition. Repeating the same condition I saw swings of one or two tasks: the seven-task difference is larger than that, but a test like this cannot say how robust it is.

The damage is observable. Its precise cause has not been isolated.

One possible explanation is that the instruction pushed the model to look for hidden problems even where none existed. But I did not experimentally separate the effects of length, wording, structure and indiscriminate activation.

So I cannot say that all global rules are harmful.

I can say something narrower but useful: **in an exploratory test, a seemingly reasonable procedure made worse tasks the model already knew how to solve**.

This changes the question to ask before adding a new Skill.

Not only: "Could it be useful?"

Also: "What happens to the problems the model was already solving without it?"

## Is it really necessary to retrieve a procedure every time?

Another result struck me for the opposite reason.

In the reference run, on 27 of the 31 tasks where F received a Skill, model B solved the task anyway without help (28 if the flawed task is counted too).

In many cases, then, retrieval added text to the prompt without changing the outcome.

That is not automatically useless. It may have effects that accuracy alone does not capture. But those tokens are consumed all the same.

I also tried a policy that avoided retrieving the procedures belonging to eight patterns that had turned out to be of little use in earlier runs.

In the second reference, `experiment_totale_2026_09_18`, injections go from 31 to 6, while B, C and F solve the same tasks as in the reference run. The Expert and the execution mode, in parallel, also change there, so I use it only for B, C and F.

I do not consider this an independent replication: it uses the same tasks and a nearly deterministic decoding behaviour. It does show that, in that comparison, the 25 injections that were dropped did not change the outcomes.

At that point a new question arises.

**Perhaps the problem is not only finding the right procedure. It is understanding when the model needs no procedure at all.**

The Librarian retrieves by tag overlap. The fact that a procedure is relevant to the problem does not show that it is also necessary.

Relevance and usefulness are two different things.

## What does it cost to teach something the model can already do?

A Skill is not free, not even when it already exists.

In `experiment4`, F uses on average 145 more input tokens than B to use the library.

The overall average consumption recorded per attempt is:

| Configuration | Average tokens |
|---|---:|
| A — Expert | 593 |
| B — Small | 221 |
| C — Solution Bank | 308 |
| F — Skill Library | 370 |

For A most of the tokens are the model's hidden reasoning, which the log counts separately but which is included here.

Building a Skill has a cost too.

In the run's log, 18 compressions and 66 re-verifications used 35,269 tokens in total, about 1,959 per Skill by the count used.

And that does not include the whole historical cost accumulated during the research.

In the economics report of the most complete run, out of ten covered patterns, one is classified as economically positive, one as positive on accuracy and eight as negative under the criteria adopted.

That does not mean eight procedures have no value. The samples per pattern are small, and a procedure might become worthwhile after more uses.

It means that **having a library of knowledge is not automatically cheaper than solving the problem directly**.

That is why the project looks at the break-even point, the building cost, the cost per use and the result obtained.

In the reference run I do not report reliable monetary costs: the price variables were not configured and the recorded values read zero. Tokens and latency, on the other hand, are available.

## What if the checker is the one that is wrong?

There is something I do not like about benchmarks: how easy it is to trust a number only because a program produced it.

At the beginning I chose `pytest` precisely to avoid subjective judgements between models.

It was a useful choice, but not a sufficient one.

During the research, six bugs in the verification infrastructure and two flawed tasks were found.

In one case the test did not really check the behaviour it was written for: `temperature_reached`, which also appears in the reference run. In another, the real defect was not the declared one: an incidental `.upper()` call in the body of the loop made the task fail, and fixing only the indicated problem was not enough to make it pass.

A model could therefore receive a success without having solved the problem I meant to measure, or a failure for a reason other than the one I meant to measure.

The consequence is simple: **a deterministic checker can return a result that is repeatable and still wrong**.

There is also the problem of fitting to the tests.

In an exploratory test from the September series, a historical result of 195 successes out of 195, obtained with test suites that had served as an oracle during the research, did not hold on a small set of six fresh cases: four were passed.

Six cases are not enough to estimate a new general accuracy, and they are not directly comparable with the whole historical sample. They are enough, though, to show that a perfect result on the cases used during development can be fragile.

Today, when a test looks too convincing, I first try to understand **what might be making it misleading**.

## Does knowing what the problem is mean knowing how to solve it?

Not always.

I also ran small exploratory tests to separate recognising the problem from the procedure proposed to solve it.

In some cases the diagnosis was enough to unblock the model.

In others, adding a complete procedure did not improve the result or made it worse. A placebo procedure, with no useful content, even took a `flatten_list` case from three successes out of three to zero out of three.

These are tiny samples: three repetitions on one or two tasks per pattern. They do not allow general conclusions.

But they point to a distinction worth keeping.

A model can fail because it does not recognise the problem. Or it can recognise it correctly and not know how to act. Or it can already know how to act, but be pushed off course by extra instructions.

These three errors do not necessarily call for the same kind of knowledge.

## From a controlled experiment to real use

I also carried some of the lab's ideas into Aria, a study app I built for a real user with ADHD.

It is not a product for sale, and the two projects stay separate at the code level.

Real use imposed different criteria.

Skills are not generated automatically from conversations. A procedure comes from an explicit choice. Text written by the user is never silently rewritten. Shortenings must be reversible and checked.

Above all, I had to tell a verifiable procedure apart from a personal preference and from a binding rule.

Not everything a person asks to remember can be treated as a method to reward or penalise on the strength of a test.

Evaluation changes too.

In the lab I can give the same task to two configurations. In real use it is the system that chooses when to retrieve a Skill. The requests that trigger it may therefore be different, and easier, than the ones that do not.

To reduce this problem you need a paired comparison and, when possible, a blind one.

In a preliminary check with a local Gemma model, on 22 comparable pairs, the behaviour retrieval mechanism scored 17 successes against 13 for the prompt without support.

Almost all of the advantage was concentrated in one domain, honesty about the materials. In the other domains the results were much closer.

One run per condition does not allow definitive conclusions, and this check sits outside the lab's reference data.

What the move to real use taught me most is that **a procedure born for one person does not automatically become a good procedure for everyone else**.

## How does procedural memory work in the code?

The unit of the library is called a `Book`.

A Book holds a procedure, its identity, the retrieval tags, its verification status and information about earlier versions.

Its path is this:

1. **It is born.** `librarian/skill_generator.py` creates a procedure in `DRAFT` state, or it is written by hand.
2. **It is verified.** `librarian/optimizer.py` can compress and re-verify it without overwriting the original. A version that passes the checks becomes `VERIFIED`.
3. **It is compared.** `librarian/similarity.py` looks for possible duplicates; `archive_duplicates.py` archives superseded versions without deleting them.
4. **It is retrieved.** `librarian/librarian.py` uses tag overlap and returns a `SkillPackage`, with no embedding calls.
5. **It enters the budget.** `librarian/context_budget.py` controls how many tokens can be put into the context.
6. **It enters the prompt.** `SkillPackage.as_prompt_context()` assembles the selected procedures.
7. **It is used.** `agents/worker.py` builds the prompt and queries the model.
8. **It is measured.** `experiment/events.py` records the steps in JSONL, from which the reports are generated.

The whole process is traceable, even when the result is negative.

### Where is what?

| Directory | Role |
|---|---|
| `domain/` | Bugs, task families and checkers |
| `agents/` | Prompts and model calls |
| `librarian/` | Retrieval, management, comparison and optimisation of procedures |
| `library/books/` | The library of Skills |
| `cheater/` | The Solution Bank of configuration C |
| `experiment/` | Running the comparisons and recording the results |
| `verification/` | Causal checks, holdouts and verification, with scripts in `benchmarks/`, `runners/` and `validation/` |
| `tests/` | The lab's automated tests |
| `city/` | Visualisation of Quests in Cognitive City |
| `adapters/` | Connection to the providers, and mock adapters |

## How to try it

You need Python 3.11 or newer.

Clone the repository into a directory called `cognitive_rpg`, then run the commands from the folder that contains it.

```bash
python -m pip install -r cognitive_rpg/requirements.txt
python -m cognitive_rpg.settings_wizard
python -m cognitive_rpg.experiment.experiment_0
```

Mock adapters let you develop without paid calls. Runs with real models need the keys of the respective providers.

The package tests can be run from the parent directory with:

```bash
python -m pytest cognitive_rpg
```

## What can I conclude?

Not that Skills are always useful.

Not that a small model, with a good library, can in general replace a more powerful one.

And not even that a procedure is necessarily better than an earlier example.

The results allow a narrower conclusion.

**External knowledge can concretely change a model's behaviour. But its benefit depends on the task, on what the model can already do, on what the procedure contains and on when it is retrieved.**

In some cases the procedure helps. In others the example gets the same result. In many nothing is needed. And in one exploratory test an added rule made performance noticeably worse.

The causal check on the tolerance also shows that a procedure can steer the model towards copying a value or towards a derivation that depends on the problem.

These are results observed in the context of the lab. They do not automatically show how an agent's instruction files, its Skills or more complex Context Engineering systems should be organised.

They do give a method for studying them: paired comparisons, negative controls, causal edits, unseen cases and checkers that are themselves put to the test.

## The questions that remain

There is a question I find even more interesting than the one I started from:

**How can we know that a model needs a procedure before we give it one?**

If retrieval happens only by similarity, we find relevant knowledge. But not necessarily useful knowledge.

And if a procedure solves a problem, how do we tell a transferable method from a shortcut that only works on cases already seen?

How much of the advantage depends on the content? How much on the diagnosis? How much on the selection? How much on the model's ability?

Finally: should a procedural memory try to remember everything that worked, or also learn when it is better not to intervene?

I do not have general answers to these questions yet.

The lab, however, has already shown why they are worth asking.

## Status of the research and limits

Procedural Memory Lab is an independent research project that is still ongoing, not a peer-reviewed paper.

The main run covers 39 synthetic Python repair tasks, with one attempt per configuration and a single family of models. The complementary checks sometimes use even smaller samples.

The earlier numbered runs are archived as logs and feed no result. Some evaluations were used during the development of the procedures. The tests in Aria belong to a different context and should not be aggregated with the lab's.

No raw log is present in the public repository. The numbers reported here come from the research's local artefacts, recomputed from `log.jsonl`; they are therefore not independently reproducible from the public version alone.

I prefer to state these limits next to the results rather than leave seemingly precise numbers without explaining where they come from.

## License

Copyright © 2026 Ferdinando Gregorio Fernandez.

All rights reserved. The source is visible for portfolio and research evaluation. Reuse, redistribution and derivative works are not permitted. See [LICENSE](LICENSE).
