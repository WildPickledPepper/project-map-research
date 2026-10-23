# Research workflow

- Read README.md and the relevant case before changing conclusions.
- Keep the focus on automatically maintained, cross-language project understanding.
- Label evidence: executed experiment, source inspection, documentation claim, proposal, unknown.
- Cite a source and pinned version for concrete tool behavior. Do not turn README claims into measured results.
- Do not call manually assembled reference data an automatically extracted graph.
- Do not treat missing graph edges as proof of independence, or runtime observations as exhaustive coverage.
- Prefer existing implementations; prototype only the gap an experiment establishes.
- Keep third-party checkouts, environments, binaries, graph databases and raw traces outside Git.
- Never commit credentials, personal workspace paths or private profiler inputs.
- When parallel agents are explicitly authorized, isolate their inputs and outputs. They must not read or send each other intermediate conclusions; the coordinator aggregates after completion. A shared filesystem is not a security boundary, so document the isolation actually achieved.
- Run `python scripts/check_research.py` before committing research changes.
- User preference: do not re-verify file hashes. Track Git revisions/tool versions and run behavior tests; preserve historical hash records without recomputing them.
