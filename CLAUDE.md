# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Working rules

1. **Commit after every major modification.** When a feature, fix, refactor or other significant change is complete
   and its quick checks pass, commit it on the current branch before starting the next one. Keep commits focused, with a
   message that says what changed and why. Do not push unless asked.
2. **Ask before running tests.** After finishing a code modification, give an estimated time for each relevant test or
   check and ask whether to run it. Never start a run expected to take more than 1 hour without explicit approval.
   Rough times on the development Mac (Apple M2, 8 GB):

   | Check | Command | About |
   | --- | --- | --- |
   | Front-end type check and unit tests | `cd frontend && npx vue-tsc --noEmit && npx vitest run` | 1 min |
   | Back-end tests | `.venv/bin/python manage.py test` (with `.env` loaded) | 1 min |
   | Browser end-to-end test | `scripts/e2e.sh` (with the 8-photo reconstruction where COLMAP is installed) | 6–10 min |
   | Reconstruction benchmark, 10 photos | `scripts/reconstruct_by_hand.py --count 10 …` | 2 min |
   | Reconstruction benchmark, 50 photos | `scripts/reconstruct_by_hand.py --count 50 …` | 25–35 min |
   | Reconstruction benchmark, 100 photos | `scripts/reconstruct_by_hand.py --count 100 …` | 40–75 min, can exceed 1 hour |

   The Mac has 8 GB of memory: run one heavy job at a time (a reconstruction, the e2e test, a headless browser), or
   processes get stopped for low memory and timings become meaningless.

## Project pointers

- Architecture, dependency rules and extension points: README, "Architecture" section; `core/test_architecture.py`
  enforces which app may import which.
- Load `.env` before Django or Celery commands: `set -a; source .env; set +a`.
- Reconstruction tools and data live outside the repo, in `../recon-tools/` and `../recon-data/`; work folders in
  `../recon-work/`.
