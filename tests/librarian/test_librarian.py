from cognitive_rpg.experiment.statistics import wilson_interval
from cognitive_rpg.models import Book, Task
from cognitive_rpg.librarian.competence import CapabilityEstimate
from cognitive_rpg.librarian.librarian import _competence_value, route


def _book(capability_tags):
    return Book("b", 1, "Test book", "python", [], capability_tags, [], "procedure", "pattern_x", "", "VERIFIED", 1, 1, [])


def _task(capability_tags):
    return Task("t", "pattern_x", "p", "fn", "src", "test", "KNOWN", [], capability_tags)


def _estimate(capability, mean, n=10):
    successes = round(mean * n)
    return CapabilityEstimate(capability, n, successes, mean, wilson_interval(successes, n))


def test_competence_value_is_one_when_book_shares_no_capability_with_task():
    book = _book(["unrelated-tag"])
    task = _task(["timezone-arithmetic"])
    assert _competence_value(book, task, {"timezone-arithmetic": _estimate("timezone-arithmetic", 0.1)}) == 1.0


def test_competence_value_is_higher_for_low_competence_than_high_competence():
    book = _book(["timezone-arithmetic"])
    task = _task(["timezone-arithmetic"])
    low_competence_value = _competence_value(book, task, {"timezone-arithmetic": _estimate("timezone-arithmetic", 0.1)})
    high_competence_value = _competence_value(book, task, {"timezone-arithmetic": _estimate("timezone-arithmetic", 0.9)})
    assert low_competence_value > high_competence_value
    assert high_competence_value >= 1.0


def test_competence_value_treats_unobserved_and_confirmed_low_as_both_worth_retrieving():
    book = _book(["never-observed-tag"])
    task = _task(["never-observed-tag"])
    unobserved_value = _competence_value(book, task, {})
    known_low_value = _competence_value(book, task, {"never-observed-tag": _estimate("never-observed-tag", 0.0)})
    high_competence_value = _competence_value(book, task, {"never-observed-tag": _estimate("never-observed-tag", 0.95)})
    # Neither "we've never checked" nor "we checked and it's bad" should be
    # silently treated as if competence were high -- both must score well
    # above a confirmed-high-competence estimate. Confirmed-low (real
    # repeated failures) is allowed to score AT LEAST as high as merely
    # unobserved -- 10/10 measured failures is stronger evidence retrieval
    # is worth it than having no data at all.
    assert unobserved_value > high_competence_value
    assert known_low_value >= unobserved_value


def test_route_with_no_competence_profile_matches_original_tag_overlap_behavior():
    task = Task("t", "floating_point_equality", "p", "fn", "src", "test", "KNOWN", [], ["floating-point", "equality-check"])
    baseline = route(task)
    explicit_none = route(task, competence_profile=None)
    assert [b.id for b in baseline.books] == [b.id for b in explicit_none.books]
    assert baseline.coverage == explicit_none.coverage


def test_route_with_competence_profile_does_not_crash_and_keeps_coverage_semantics():
    task = Task("t", "floating_point_equality", "p", "fn", "src", "test", "KNOWN", [], ["floating-point", "equality-check"])
    profile = {"floating-point": _estimate("floating-point", 0.2), "equality-check": _estimate("equality-check", 0.2)}
    result = route(task, competence_profile=profile)
    baseline = route(task)
    # same real Book(s) selected either way here -- this pattern only has one
    # live Book, so re-ranking has nothing to reorder; this test only
    # confirms the competence-aware path runs against the real library
    # without crashing and without changing coverage/membership when there
    # is no actual competition to re-rank.
    assert [b.id for b in result.books] == [b.id for b in baseline.books]
    assert result.coverage == baseline.coverage
