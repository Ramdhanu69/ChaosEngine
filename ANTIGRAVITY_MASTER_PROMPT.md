# MASTER PROMPT — ChaosHarness: make results honest, fix live mode, rebuild terminal UI + output filesystem

You are working in the repo root `ChaosHarness/` (Python ≥3.10, Windows PowerShell is the primary platform). Read this whole prompt first, then work through the phases in order. After each phase run `python -m pytest -q -m "not live_ollama"` and `python run.py selftest`; both must stay green. Do not stop to ask questions — where a choice is needed, pick the option described here.

## 0. Ground rules

1. **No target score.** Never tune code, prompts, thresholds or caches to land on a particular percentage. The only goal is that every number printed or written is something a real model actually produced, graded by a deterministic oracle. If gemma4:e2b scores 40% or 90%, both are fine.
2. Do not delete the mock models (`mocks.py`) or `selftest`. They are legitimate test doubles for the *harness itself*. They must just never be reachable from a "live" run.
3. Keep the public CLI surface working: `python run.py ...`, `python -m chaosharness ...`, subcommands `run | compare | selftest | route`.
4. Python files only use stdlib + `requests, rich, pillow, pyyaml, psutil` (pytest for dev). Windows-safe: no unconditional emoji, UTF-8 reconfigure stays, use `pathlib`.
5. Make small, reviewable commits per phase.

## 1. Verified diagnosis (I read the code — trust this over any earlier notes)

The earlier "notes" claimed `cache.py` has `get_cached_response` and that `client.py` silently falls back to `mocks.py`. **Neither exists. Do not apply those patches.** What is actually wrong:

| # | Problem | Where |
|---|---------|-------|
| A | Artificial 100% comes from **replay of a synthetic cache**. `scripts/generate_demo_cache.py` builds `demo_cache/gemma4_e2b.jsonl` from `MockModel` answers; `demo_cache/probe_metadata.json` literally says `"source": "synthetic_mock_demo"` and claims `vision: true, native_tools: true`. README (lines ~172, 356, 373) and `.github/workflows/ci.yml` tell people to run `--cache replay --cache-dir ./demo_cache`, which reports those mock answers under the name `gemma4:e2b`. | `demo_cache/`, README, CI |
| B | The committed `out/gemma4_e2b/*` and `out/compare/mock-*/*` are stale artifacts of that replay and are **internally inconsistent**: every domain 100% but every tier `BLOCKED`, `overall_resilience: null`. They must not ship as if they were results. | `out/` |
| C | Replay mode is broken even for its own demo: `--quick --cache replay` crashes with `CacheMiss` in the vision domain. | `cache.py`, `profiler.py`, `vision.py` |
| D | Ground truth is passed to every client call as `hint={"mock_response": gt}` in `domains/{data,logic,vision,code}.py`. Real `LLMClient` ignores it, but it is hashed into cache keys and it couples oracle data to the transport. Mock-only data must travel on a separate, explicit channel. | `domains/*.py`, `client.py`, `mocks.py` |
| E | **Vision never runs live.** `LLMClient.probe()` hard-codes `vision=False` and `json_mode=False`, so live runs mark vision `N/A`. Also images are sent as a non-standard top-level `"images"` key on `/v1/chat/completions`, which Ollama's OpenAI-compatible endpoint ignores. | `client.py` |
| F | Failures are swallowed instead of recorded: unparsable tool-call `arguments` are silently dropped (`except Exception: pass`); `max_tokens=768` can truncate answers from thinking-style models and then get graded as a model failure; `model_available` matching is loose. | `client.py` |
| G | Terminal output is a basic rich table with no chaos-vector breakdown, no provenance, no failure taxonomy, no confidence intervals. | `cli.py::display_scorecard` |
| H | CLI hygiene: duplicate `--out/--output`; `compare` ignores `--cache`/`--mock` plumbing differences and hard-codes `--quick` true; `--min-tier` logic collapses tiers incorrectly; README/test paths drift. | `cli.py` |

## 2. Phase 1 — Provenance + make live mode trustworthy

1. Add `chaosharness/provenance.py` with `build_provenance(args, client, probe) -> dict` capturing: `mode` (`live` | `replay` | `record` | `mock`), `model`, `endpoint`, `seed`, `trials`, `items`, `temperature`, `utc_timestamp`, `harness_version`, `python_version`, `platform`, and — for live runs — Ollama `/api/version` and the model digest from `/api/tags` (best-effort, never crash). Include `cache_dir` and `cache_source` (read from `probe_metadata.json["source"]` if present).
2. Write that block into `results.json`, `routing_manifest.json`, `EVAL_REPORT.md` header, `report.html` header and the terminal header (Phase 4).
3. **Synthetic guard:** if mode is `replay` and the cache's `probe_metadata.json` source is `synthetic_mock_demo` (or `--mock` is used), set `provenance.synthetic = true`. Then:
   - print a bold red banner in the terminal: `SYNTHETIC DEMO DATA — NOT A MODEL RESULT`;
   - add the same banner to the top of EVAL_REPORT.md and report.html;
   - make the badge say `DEMO` instead of a tier;
   - write outputs to `out/demo/<model>/` instead of `out/<model>/`.
4. **Live isolation:** in `get_client`, if `mock` is set or cache mode ≠ `live`, that's fine, but a run with mode `live` must construct `LLMClient` with `cache=None` (not a `RequestCache` object) so nothing can intercept it. Add a unit test proving live mode never touches the cache or `mocks.py` (monkeypatch `requests.post` and assert it is called; assert `mocks` module not used).
5. `client.py`:
   - Keep the retry/backoff but surface the *final* error text in `Response.error`; never return fake success.
   - Tool calls: if `arguments` fails `json.loads`, keep the call with `args={}` and set `ToolCall.invalid=True` (add field, default False) so `agent.py` counts it in `invalid_calls` and `chaos.py` can label `SCHEMA_CRASH`/`BAD_FORMAT` instead of losing it.
   - `max_tokens`: default to 2048, expose `--max-tokens`. If the response `finish_reason == "length"`, record it on `Response` (`truncated=True`) and have the graders label it `BAD_FORMAT` with detail `"truncated at max_tokens"` — distinct from a wrong answer.
   - Strip `<think>…</think>` blocks and fenced ```json fences from `text` before JSON extraction (add one shared helper `extract_json(text)` in a new `chaosharness/parsing.py` and use it in data/logic/vision/agent — it currently is copy-pasted four times as `find("{")…rfind("}")`).
   - `probe()`: use exact model-name matching (`m == model` or `m == f"{model}:latest"`). **Actually probe vision**: render a tiny 64×64 PNG with a red square, send it via the image path below, and set `vision=True` only if the model answers sensibly (contains "red"); otherwise `False` with a reason string stored in the probe result. Probe `json_mode` with `response_format={"type":"json_object"}`. Probe `native_tools` as today. Store `probe["reasons"]`.
   - Images: send as OpenAI-style content parts: `{"role":"user","content":[{"type":"text","text":...},{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]}` instead of the top-level `"images"` key.
6. Do **not** hard-code vision off. If the probe says no vision, the domain is `N/A` with the real reason in the report — that is an honest result.

## 3. Phase 2 — Remove ground truth from the transport; fix replay

1. Change `chat(..., hint=None)` to `chat(..., hint=None, mock_hint=None)`. `hint` stays as cache-key metadata (`{"vector":..., "scenario":...}` or `{"domain":..., "item_id":...}`); `mock_hint` carries `mock_response` and is **only** read by `MockModel`. `LLMClient` must ignore it and must not include it in the cache key.
2. Update all four domains and `mocks.py`, `agent.py` accordingly. Selftest must still pass.
3. Make `--cache replay` self-consistent: replay a cache recorded with the same `seed/trials/items/quick/vision` settings, and on `CacheMiss` print a clear one-line error (`cache miss: re-record with --cache record using the same flags`) and exit code 3 — no traceback. Store the recording config in `probe_metadata.json` (`recorded_with`) and warn on mismatch before running.
4. Replace `scripts/generate_demo_cache.py` so the demo cache is generated by running the real chaos+domain suite against `MockGood` through the `record` path (so keys always match), and mark it `source: synthetic_mock_demo`, model name `mock-good` — **not** `gemma4:e2b`. Rename files accordingly (`demo_cache/mock-good.jsonl`). Update README + CI to `--model mock-good --cache replay --cache-dir ./demo_cache`, labelled as a CI smoke test of the harness, not a model benchmark.
5. Delete the committed `out/` tree and the stale `perf_metrics.json`; add `out/`, `cache/`, `perf_metrics.json`, `__pycache__/` to `.gitignore`. Keep `.gitkeep` only if needed.

## 4. Phase 3 — Grader correctness (do not loosen, do not tighten arbitrarily)

Review, with tests, that each oracle is strict and deterministic:
- `domains/data.py`: current exact-F1 on flattened keys with type+value equality is correct — keep it. Add handling for models that wrap output in fences/think tags via `extract_json`. Do **not** replace it with a key-presence-only check (that would make it *easier* to pass). Add a test where a model returns right keys / wrong values and must score < 1.0.
- `domains/logic.py`: lists are compared via `str(list)`; switch to element-wise equality so `[2, 3]` vs `[2,3]` formatting differences can't matter.
- `domains/vision.py`: validate types (`int` not `str`) before IoU; guard `parsed` not being a dict.
- `chaos.py`: the undeclared-tool check runs *after* grading and can overwrite a `CLIENT_ERROR`; make `CLIENT_ERROR` episodes keep their label and stay excluded from resilience (as `scoring.py` already intends). Add `SCHEMA_CRASH`/`BAD_FORMAT` handling for `ToolCall.invalid`.
- `tools.py`/`chaos.py`: confirm `phantom_tool_lure`, `prompt_injection` honeypot + canary, and `retry_trap` budgets cannot be passed by an empty reply (a model that says nothing must not "pass" a `max_attempts` rule — require an explicit `error`/`cannot_do`/escalation as already coded; add a test for the empty-reply case).
- Add mutation-style tests in `tests/test_graders_strict.py`: for each domain a deliberately wrong answer must fail.

## 5. Phase 4 — Terminal design (rich, with plain fallback)

Replace `display_scorecard` in `cli.py` with a new module `chaosharness/ui.py` exposing `render_dashboard(manifest, results_summary, provenance, out_dir, console=None)`. Requirements:

- Width-adaptive (`console.width`, min 80), no emoji (use `■ ▲ ●` / ASCII on legacy Windows consoles; detect `console.encoding` and fall back to `#`/`-`).
- Layout, top to bottom:
  1. **Header panel:** `CHAOSHARNESS · runtime fault & domain profiler`; target model, mode badge (`LIVE` green / `REPLAY` yellow / `MOCK` or `SYNTHETIC` red), endpoint, seed, trials/items, elapsed time, Ollama version + model digest (short).
  2. **Engine 1 table — Runtime chaos resilience:** one row per vector (all 9): trials run, passed, pass-rate bar (`█░` ×10), status `PASS ≥75 / WARN 50–75 / FAIL <50`, dominant failure label. Footer: overall resilience, weighted resilience, Wilson LCB, silent-corruption rate. `CLIENT_ERROR` episodes shown separately as "excluded".
  3. **Engine 2 table — Domain competency:** per domain: items, exact passes, mean score, Wilson 95% interval, bar, **tier** (AUTONOMOUS green / SUPERVISED yellow / BLOCKED red / N/A dim) and, for N/A, the real reason.
  4. **Failure taxonomy:** compact horizontal bars of failure-label counts across both engines.
  5. **Verdict panel:** `recommended_route`, routing constraints (from the manifest — never recomputed in the UI, so the UI cannot disagree with `routing_manifest.json`), and `--min-tier` pass/fail if set.
  6. **Artifacts panel:** a tree of the files written in this run with sizes (see Phase 5).
- Add live progress during a run using `rich.progress` (one bar for chaos vectors, one for domain items) with the current vector/item name; non-TTY → plain `[INFO]` lines. Ctrl-C must still preserve partial results (existing behaviour) and the dashboard must label them `PARTIAL`.
- Add `--no-color` and `--json` (machine-readable summary to stdout, nothing else) flags.
- Do **not** invent composite scores or hard-coded verdict thresholds in the UI. Tiers/routes come only from `synthesizer.determine_domain_tier` / `build_routing_manifest`.
- Snapshot test `tests/test_ui.py` renders the dashboard from a fixed manifest using `Console(record=True, width=100)` and asserts key strings and no exceptions with `rich` absent (fallback path).

## 6. Phase 5 — File system / outputs

Target layout (create/adjust code so a run produces exactly this):

```
ChaosHarness/
├── run.py                       # thin entry → chaosharness.run.run_shim
├── requirements.txt / pyproject.toml / README.md / LICENSE
├── chaosharness/
│   ├── cli.py                   # arg parsing + orchestration only
│   ├── ui.py                    # NEW terminal dashboard + progress
│   ├── provenance.py            # NEW run metadata
│   ├── parsing.py               # NEW extract_json, think/fence stripping
│   ├── client.py  agent.py  tools.py  chaos.py  scenarios.py
│   ├── profiler.py  scoring.py  synthesizer.py  cache.py  mocks.py
│   └── domains/ code.py data.py logic.py vision.py sandbox.py
├── scenario_packs/example_pack.yaml
├── demo_cache/                  # synthetic, mock-good only, clearly labelled
├── scripts/generate_demo_cache.py
├── tests/                       # existing + test_graders_strict.py, test_ui.py, test_live_isolation.py
└── out/                         # git-ignored, generated
    ├── <model>/<UTC-timestamp>/ # one folder per run (never overwritten)
    │   ├── results.json         # raw per-episode and per-item data + provenance
    │   ├── routing_manifest.json
    │   ├── EVAL_REPORT.md
    │   ├── report.html
    │   ├── badge.svg
    │   └── run.log              # full console log of the run
    ├── <model>/latest           # copy (or pointer file on Windows) to newest run
    ├── compare/<UTC-timestamp>/leaderboard.{json,md} + one subfolder per model
    └── demo/…                   # only for synthetic/mock runs
```

Implementation notes: `--out` and `--output` become one flag (`--out`, with `--output` kept as a hidden alias). `route --manifest` must accept either a manifest path or a model name (resolving `out/<model>/latest/routing_manifest.json`). Use atomic writes (write temp, `os.replace`). Fix `compare` so it forwards `--cache`, `--mock`, `--items`, `--trials`, `--quick` correctly (quick default must not be forced), writes a `leaderboard.json`/`.md`, and renders a side-by-side terminal table. Fix `--min-tier` so it checks that **every** non-N/A domain meets the requested tier (document this), exit code 1 on failure.

## 7. Phase 6 — Docs and CI

- README: rewrite the "demo/replay" sections to say plainly that the bundled cache is synthetic (`mock-good`), shows what the dashboard looks like, and is *not* a benchmark. Add a "Real run" section: `ollama pull gemma4:e2b` then `python run.py --model gemma4:e2b --endpoint http://localhost:11434`. Add a short "How to read results" with tiers, Wilson intervals, `CLIENT_ERROR` exclusion and the `N/A` rule.
- CI: run `pytest -m "not live_ollama"`, `selftest`, and the mock-good replay smoke test. Keep `live_ollama` tests opt-in.
- Update `tests/test_live_ollama.py` to skip cleanly when Ollama or the model is absent.

## 8. Definition of done (verify and report each)

1. `python run.py selftest` passes; `pytest -m "not live_ollama"` passes (install pytest if missing).
2. `python run.py run --model mock-good --mock good --quick` produces a full dashboard with a visible `MOCK/SYNTHETIC` banner and writes to `out/demo/…`.
3. `python run.py run --model gemma4:e2b --quick` with Ollama **stopped** prints a single clear error and exits 2 — it must never fall back to mocks or cache.
4. With Ollama running (if available in your environment), the same command performs real HTTP calls (confirm via `run.log` latencies > 0.05 s and varied token counts), and `results.json.provenance.mode == "live"`.
5. Grep proves no ground truth reaches `LLMClient`: `grep -rn "mock_response" chaosharness | ` shows it only in domains (as `mock_hint`) and `mocks.py`.
6. No file under `out/` is committed; no `demo_cache` file claims to be `gemma4:e2b`.
7. Finish with a short change log listing each file touched and any item you could not complete and why.
