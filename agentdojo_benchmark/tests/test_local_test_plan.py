"""Tests for the phase 6 test plan (no GPU or network needed)."""

from collections import Counter

from agentdojo_benchmark.local_test_plan import DEFAULT_ATTACKS, build_test_plan


def test_default_plan_has_50_attacked_and_18_baseline_runs():
    plan = build_test_plan()
    attacked = [test for test in plan if not test.is_baseline]
    baseline = [test for test in plan if test.is_baseline]
    assert len(attacked) == 50
    assert len(baseline) == 18


def test_banking_is_never_used():
    assert all(test.suite != "banking" for test in build_test_plan())


def test_attack_styles_are_used_about_equally():
    counts = Counter(test.attack for test in build_test_plan() if not test.is_baseline)
    assert set(counts) == set(DEFAULT_ATTACKS)
    assert max(counts.values()) - min(counts.values()) <= 1


def test_no_test_is_repeated():
    plan = build_test_plan()
    assert len(plan) == len(set(plan))


def test_every_attacked_user_task_also_has_a_baseline_run():
    plan = build_test_plan()
    baseline = {(t.suite, t.user_task) for t in plan if t.is_baseline}
    assert all((t.suite, t.user_task) in baseline for t in plan if not t.is_baseline)


def test_same_seed_gives_same_plan_and_other_seed_does_not():
    assert build_test_plan(seed=0) == build_test_plan(seed=0)
    assert build_test_plan(seed=0) != build_test_plan(seed=1)
