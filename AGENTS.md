# Research workflow

- Read README.md and the relevant case before changing conclusions.
- Keep the focus on automatically maintained, cross-language project understanding.
- Keep production discovery and linking project independent. Project/module/interface names belong to discovered output and isolated evaluation references, not input whitelists or hardcoded matching. New modules must be discovered and updated without changing business-name rules; new unsupported languages/mechanisms must surface as required gaps. Verify different repository layouts plus module addition, rename and deletion.
- Use plans/project-wide-completion-plan.md and plans/project-wide-acceptance.md as the current implementation scope and completion authority. File inventory, parser support, node/test counts, limited-chain passes and skill packaging do not establish whole-project completion. Required runtime languages/modules/boundary families without semantic extraction or connections keep the overall gate unpassed. Preserve historical evidence within its original scope; historical asset integration remains deferred.
- For historical regression samples, read and follow [the confirmed sample split](datasets/msinsight-regressions/split.md). Sample-driven development is limited to its eight development records. Do not investigate, prepare, execute, score, or tune rules against validation candidates until the user explicitly starts validation. Keep related regressions separate from independent validation; ordinary repository-wide discovery remains allowed as specified in the split.
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
- Keep the upstream GitCode repository and the original downloaded Insight checkout unchanged. Source mutations and runtime instrumentation belong in separate local experimental copies; publish this project's tools and reports only to the research GitHub repository.
