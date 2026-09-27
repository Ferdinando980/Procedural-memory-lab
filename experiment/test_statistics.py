from .statistics import wilson_interval


def test_wilson_interval_matches_known_reference_values():
    # Reference values cross-checked against the standard Wilson score
    # formula (e.g. Wikipedia "binomial proportion confidence interval",
    # Wilson score interval, z=1.96) for round, easily-verified inputs.
    low, high = wilson_interval(5, 5)  # 100% on n=5 -- should NOT be (1.0, 1.0)
    assert low > 0.4 and low < 0.6
    assert high == 1.0

    low, high = wilson_interval(0, 5)  # 0% on n=5 -- symmetric to the above
    assert low == 0.0
    assert high > 0.4 and high < 0.6

    low, high = wilson_interval(50, 100)  # 50% on n=100, well-known ~[0.404, 0.596]
    assert abs(low - 0.404) < 0.01
    assert abs(high - 0.596) < 0.01


def test_wilson_interval_always_stays_inside_unit_range():
    for successes, n in [(0, 1), (1, 1), (3, 5), (39, 39), (0, 39)]:
        low, high = wilson_interval(successes, n)
        assert 0.0 <= low <= high <= 1.0


def test_wilson_interval_wider_at_smaller_n_same_proportion():
    # Same 80% proportion, less data should mean a wider (more honest) interval.
    low_small, high_small = wilson_interval(4, 5)
    low_big, high_big = wilson_interval(80, 100)
    assert (high_small - low_small) > (high_big - low_big)


def test_wilson_interval_zero_n_is_maximally_uninformative_not_an_error():
    assert wilson_interval(0, 0) == (0.0, 1.0)
