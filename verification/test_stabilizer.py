from .stabilizer import extract_json_object, majority_vote


def test_extract_json_object_parses_plain_object():
    assert extract_json_object('{"winner": "A", "score_a": 1}') == {"winner": "A", "score_a": 1}


def test_extract_json_object_skips_leading_prose():
    text = 'Sure, here is my verdict:\n{"winner": "B", "reason": "clear"}'
    assert extract_json_object(text) == {"winner": "B", "reason": "clear"}


def test_extract_json_object_handles_braces_inside_string_values():
    # The confirmed cause of 'invalid Qwen verdict' (TODO.md, 2026-09-21):
    # a judge quoting a response that itself mentions a dict/brace example
    # inside the 'reason' field. The old naive text[index('{'):rindex('}')+1]
    # slice would grab from the FIRST '{' (possibly inside the quoted
    # example) to the LAST '}' in the whole text, producing invalid JSON.
    text = (
        'Some reasoning first, mentioning {this is not json} as an aside.\n'
        '{"winner": "A", "score_a": 8, "score_b": 2, '
        '"reason": "response B described a dict like {\\"key\\": \\"value\\"} incorrectly"}'
    )
    data = extract_json_object(text)
    assert data is not None
    assert data["winner"] == "A"
    assert data["reason"] == 'response B described a dict like {"key": "value"} incorrectly'


def test_extract_json_object_handles_nested_objects():
    text = '{"winner": "A", "meta": {"confidence": 0.9, "notes": "ok"}}'
    data = extract_json_object(text)
    assert data == {"winner": "A", "meta": {"confidence": 0.9, "notes": "ok"}}


def test_extract_json_object_returns_none_for_unbalanced_or_absent_json():
    assert extract_json_object("no json here at all") is None
    assert extract_json_object('{"winner": "A"') is None  # truncated, e.g. by a max_tokens cutoff


def test_extract_json_object_returns_none_for_a_json_array_not_object():
    assert extract_json_object('["A", "B"]') is None


def test_majority_vote_still_works_unchanged():
    assert majority_vote(["A", "A", "B"]) == "A"
    assert majority_vote(["A", "B", "C"]) is None  # genuine three-way tie
    assert majority_vote([]) is None
