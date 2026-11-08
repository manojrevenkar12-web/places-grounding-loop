from pgl.agents.harness import GUARDED, PLAIN
from pgl.evals import feedback
from pgl.evals.tasks import Evaluator, load_tasks


def test_a_case_replays_the_failure_it_was_found_in_and_the_guards_fix_most(s, releases):
    _, r2 = releases
    ev = Evaluator(r2, s)
    tasks, truth = load_tasks("dev")
    tasks = tasks[:30]
    log, runs = feedback.production(ev, PLAIN, tasks, truth, s, days=1)
    tri = feedback.triage(log, runs)
    assert tri["confirmed"] + tri["false_reports"] == tri["reported"]
    assert tri["cases"], "a day of the plain loop should produce reported failures"
    again = feedback.replay(ev, PLAIN, tri["cases"], tasks, truth, s)
    assert not any(again.values()), "a case must fail again on the harness it was found on"
    fixed = feedback.replay(ev, GUARDED, tri["cases"], tasks, truth, s)
    assert sum(fixed.values()) >= len(fixed) / 2


def test_the_log_holds_what_production_saw_and_nothing_more(s, releases):
    _, r2 = releases
    ev = Evaluator(r2, s)
    tasks, truth = load_tasks("dev")
    log, _ = feedback.production(ev, PLAIN, tasks[:5], truth, s, days=1)
    assert set(log[0]) == {"request", "task", "seed_repeat", "turns", "now", "answers", "trace", "user_report"}
