"""Pure, domain-independent statistics helpers -- no dependency on log
records, adapters, or any project-specific schema, unlike every function in
metrics.py (which is coupled to log.jsonl/events.jsonl's A/B/F/C config
shape). Lives here rather than in metrics.py or verification/ specifically
so it has exactly one home shared by both: metrics.py's own experiment/ ->
library/ dependency note already establishes experiment/ as a shared layer
verification/ is allowed to import from (see substitution_ablation.py's
`from ..experiment.events import emit`).

First need (2026-09-21): every accuracy percentage reported across this
project's experiments (experiment4's 97.4%, calibration's skilled_wins
counts, benchmark_self_consistency's single/majority accuracy) was a single
point estimate with no uncertainty at all -- a real gap found while
comparing against published baselines (Wang et al. 2022 and others report
error bars or multiple runs; this project reported none). This does not fix
the small-n problem itself, but at fixed n it is the cheapest, honest next
step: report HOW uncertain a given n actually leaves the number, instead of
implying false precision with a bare percentage."""

import math


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95%-by-default Wilson score confidence interval for a binomial
    proportion (successes out of n trials). Preferred over the naive
    normal-approximation interval (phat +/- z*sqrt(phat*(1-phat)/n)) because
    the naive form can extend below 0 or above 1 and is known to be poorly
    calibrated exactly at the small-n, extreme-phat regime this project's
    own results live in (e.g. 5/5 or 4/5 on a 5-probe suite) -- Wilson
    stays inside [0, 1] by construction and is the standard textbook
    recommendation for small-sample proportions.

    n=0 returns (0.0, 1.0), the maximally uninformative interval, rather
    than raising -- consistent with this package's fail-closed convention
    of reporting 'we don't know' as data, not an exception a caller must
    handle specially."""
    if n <= 0:
        return (0.0, 1.0)
    phat = successes / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    low = max(0.0, (center - margin) / denom)
    high = min(1.0, (center + margin) / denom)
    return (low, high)
