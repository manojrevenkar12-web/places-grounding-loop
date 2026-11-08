# Working on places-grounding-loop

## Fast feedback

| What | Command | Time |
|---|---|---|
| Lint and format | `ruff check src tests scripts && ruff format --check src tests scripts` | ~1 s |
| All tests (Spark starts once, ~15 s) | `make test` | ~35 s |
| Gate a harness change | `make gate` (or `python scripts/gate.py "<name>"`) | ~1 min |
| Development evaluation | `make eval` | ~9 min |
| Dashboard | `cd web && npm test && npm run dev` | ~3 s |

## Invariants

1. **Nothing that serves reads the truth.** `src/pgl/pipeline`, `servers` and `agents` never read `data/truth/` or
   `evalcases/` and never import `pgl.evals`. The matcher's training labels are read only by `pgl.training`.
   `tests/test_isolation.py` checks it. The production log holds what production saw and no verdicts.
2. **Arguments come from the request or a tool.** A coordinate pair or a place id the model proposes has to appear in
   an earlier tool result; the harness rejects it otherwise. Plans refer to earlier results instead of copying them.
3. **Facts carry their data version.** Every tool result says which version it was read at; a turn starts by reading
   the current version, drops older facts, and the cache key includes the version.
4. **Place ids survive a refresh.** A release that would change more than `max_id_loss_share` of ids is blocked.
   Closing a place needs two independent kinds of signal.
5. **The gate decides.** A harness change ships only if `scripts/gate.py` passes it: task success on the development
   tasks (paired lower bound), every regression case the current harness passes, and the latency and cost budgets.
   Confirmed production failures become regression cases; they are not deleted to make a change pass.
6. **Settings in config.** Rates, prices, budgets, thresholds and the gate live in `config/pgl.toml`; the dashboard's
   visual constants in `web/src/theme/tokens.ts`.
7. **Generated reports.** `reports/results.json`, `reports/RESULTS.md`, the README results block and
   `web/public/data` come from `make report`.

## The held-out rule

The world data, including the east area and its tasks, is pinned in `config/heldout.sha256`, recorded before any
pipeline or agent code existed. `scripts/heldout.py` refuses to run if the data changed, if the code is not
committed, or if it has run before. When the held-out run shows a problem, publish it, fix it with a test on
development data, and do not rerun the held-out set to improve the number.
