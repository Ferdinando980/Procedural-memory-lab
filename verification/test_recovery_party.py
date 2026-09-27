from dataclasses import dataclass

from .recovery_party import SearchBudget, RecoveryRoute, run_recovery_party


@dataclass
class Verdict:
    passed: bool


def test_party_uses_external_verifier_and_stops_on_first_success():
    routes = [RecoveryRoute("b", "second", 1), RecoveryRoute("a", "first", 2)]
    produced = []

    def produce(evidence, route):
        produced.append(route.id)
        return f"{evidence}:{route.id}", 3

    def verify(candidate):
        verdict = Verdict(candidate.endswith(":b"))
        return verdict, verdict.passed

    outcome = run_recovery_party("failure", routes, produce, verify)
    assert produced == ["a", "b"]
    assert outcome.selected.route.id == "b"
    assert len(outcome.trials) == 2


def test_search_budget_caps_cost_without_accepting_failure():
    routes = [RecoveryRoute(str(i), "route", 3 - i) for i in range(3)]
    outcome = run_recovery_party(
        "failure", routes,
        lambda evidence, route: (route.id, 5),
        lambda candidate: (Verdict(False), False),
        SearchBudget(max_candidates=3, max_cost_units=5),
    )
    assert outcome.selected is None
    assert outcome.exhausted_budget is True
    assert len(outcome.trials) == 1


def test_routes_can_request_evidence_only_context_without_domain_assumptions():
    route = RecoveryRoute("quarantine", "use certified evidence", context_policy="evidence_only")
    assert route.context_policy == "evidence_only"
