# 06 — Quality gates and testing

`plan.txt` asked whether implementation should stop when a quality gate fails. The answer is **yes for contract violations and no for judgment signals**, and getting that split right is most of what this document is about. A gate model that blocks on everything produces bypass culture — around 54% of engineers report having circumvented a security gate in the past year ([01: 5.4]) — while one that blocks on nothing is decoration.

---

## 1. Four gate classes

Every check declares its class. The class determines what happens when it fails.

### Contract — blocks, halts the agent, no self-override

Binary, objective, and harmful when violated. False positives must be near zero, because these gates stop work.

- Build fails · type check fails
- A previously passing test now fails
- **Test-integrity audit** trips (§4)
- Secret detected in the diff
- Dependency not in the lockfile, or not on the allowlist
- Diff escapes the task's `touches`
- Task marked `done` without a valid verification record
- Memory-hygiene checks: budget exceeded, dangling reference, duplicate ID
- Known-critical CVE introduced

Override is possible but is a **human commit** adding a dated, reasoned entry to `aios/incidents/`. The agent cannot override, cannot ask to override, and cannot edit the override list.

### Ratchet — blocks only regression

"This change may not make the metric worse." Always satisfiable, never blocks legitimate work, monotonically improves. This is the class that solves the threshold problem ([01: 5.5]): a fixed coverage target either blocks good changes or is set low enough to be meaningless, whereas a ratchet does neither.

- Coverage on changed lines
- Shipped artifact size, where the ecosystem has a meaningful notion of one (a JS bundle, a container image, a binary)
- p95 latency on benchmarked paths
- Count of lint suppressions — whatever the chosen linter's escape hatch is spelled as (`eslint-disable`, `# type: ignore`, `@ts-expect-error`, `#[allow(...)]`, `//nolint`)
- Count of `TODO` / `FIXME`
- `AGENTS.md` line count
- Accessibility violations on changed views

The suppression ratchet deserves note: it is the cheapest available defence against an agent silencing a check rather than satisfying it, and it costs one number in CI.

### Advisory — reports, never blocks

Real signal, meaningful false-positive rate, judgment required.

- Complexity and duplication metrics
- Architecture-boundary suggestions
- Performance heuristics
- Most static-analysis "code smell" categories

Advisory findings are posted to the PR and are explicitly not the agent's problem to fix unless a human says so. Google's static-analysis experience is the guide here: adoption depended on effective false-positive rate, not on how many true positives a tool found ([01: 5.5]). A noisy blocking analyser teaches people to ignore analysers.

### Report — measured, surfaced, never acted on automatically

Trend data that informs the humans and drives nothing.

- Requirement/test orphan report
- Review debt
- Rule-count and doc-volume trend
- DORA-shaped delivery metrics

---

## 2. The demotion rule

Any Contract gate that produces **three overrides in 30 days** is automatically demoted to Ratchet, and a report is filed. Any Advisory check ignored 20 times in a row is deleted.

This is the mechanism no surveyed framework has and the one that prevents the slow slide into bypass culture. A gate that is being overridden repeatedly is *already* not blocking — it is just blocking dishonestly, teaching everyone that overrides are normal. Demoting it makes the truth explicit and preserves the credibility of the gates that remain. Deleting ignored advisories is the same logic applied to noise.

The risk is obvious: a genuinely important gate could be demoted because it is inconvenient. Mitigations are that demotion files a report a human must close, that the security subset of Contract gates ([07](07-security-and-agent-containment.md)) is exempt, and that demotion is itself a reviewable commit.

---

## 3. Tier policy

`aios/config.yml` sets `tier`, which promotes or demotes whole groups. The gate *set* is identical across tiers; only the class assignment changes, so raising a tier is a one-line config change rather than a migration.

| Check | prototype | internal | production | regulated |
|---|---|---|---|---|
| Build / types | Contract | Contract | Contract | Contract |
| Test integrity audit | Contract | Contract | Contract | Contract |
| Secrets scan | Contract | Contract | Contract | Contract |
| Lockfile + allowlist | Contract | Contract | Contract | Contract |
| Scope (`touches`) | Advisory | Contract | Contract | Contract |
| Coverage on changed lines | Report | Ratchet | Ratchet | Contract (≥80%) |
| Requirement→test traceability | Report | Report | Ratchet | Contract |
| Accessibility | Report | Ratchet | Ratchet | Contract (WCAG 2.2 AA) |
| Performance budget | Report | Report | Ratchet | Ratchet |
| SAST (high severity) | Advisory | Ratchet | Contract | Contract |
| Doc staleness | Report | Report | Ratchet | Contract |
| Mutation sampling | — | Report | Report | Ratchet |
| Signed commits / provenance | — | — | Ratchet | Contract |

A prototype still runs everything; it just mostly reports. That is deliberate: the trend data exists from day one, so promoting the tier is not a leap into the unknown, and the team can see what would have blocked them before it does.

---

## 4. Test integrity: the audit that makes the rest real

Everything above assumes the tests mean something. Reward hacking is measured, not hypothetical, and it generalises beyond the setting it was learned in ([01: 5.1]). The specific behaviours are enumerable ([01: 5.2]), so the audit is a diff scan for:

- Added `skip` / `xfail` / `.only` / `it.skip` / `@Disabled`
- Assertions weakened (`assertEqual` → `assertIsNotNone`, `toBe` → `toBeTruthy`, `toEqual` → `toBeDefined`)
- Exception handlers broadened around a previously failing call
- The unit under test replaced by a mock
- A test case deleted while its subject code remains
- Timeouts raised
- `--ignore`, `--exclude`, `--passWithNoTests`, `-k 'not ...'` added to a test command
- Coverage thresholds lowered
- New suppression comments on lines the task touched

Any hit is a **Contract** failure. Legitimate cases exist — sometimes a test really should be deleted — and they are handled by a human commit with a reason, which is exactly the visibility the control is for.

This audit only works because of P2a: test files, CI workflows, and gate configuration are outside the agent's write scope and behind CODEOWNERS. Without that, the audit is a suggestion the agent can rewrite. **This is the single most important structural difference between this design and the frameworks surveyed**, all of which let the agent edit its own grader.

---

## 5. Testing strategy

### 5.1 Allocation

Roughly 70% unit, 20% integration, 10% end-to-end, adjusted per project. Conventional, and conventional is correct here — the interesting part is what changes under AI assistance.

### 5.2 What changes when an agent writes the tests

**Agents write plausible tests, which is not the same as adversarial ones.** They cover the path the implementation takes, because they just wrote the implementation. The counters:

- **Acceptance criteria are written before implementation**, in the task file, in EARS form, by planning mode. The test then has an external target rather than an inherited one.
- **Mutation sampling** on critical modules — sampled, not exhaustive, because full mutation runs are too slow to gate on. Line coverage is a poor fault-detection predictor ([01: 5.6]); mutation score is the honest measure, and even a 5% sample surfaces suites that assert nothing.
- **The verifier subagent checks tests against acceptance criteria in fresh context**, which catches the tautological test that the author agent cannot see.

**Coverage is never a target.** It appears as a ratchet on changed lines and as a map of what is untested. Making it a target is the canonical way to produce a suite full of assertion-free execution.

### 5.3 Test naming and traceability

Tests carry `@satisfies <REQ-ID>`. This gives the orphan reports in [04](04-state-and-tasks.md#5-traceability) and, more usefully, gives a failing test a *reason*: not "assertion failed in `search.test.ts:42`" but "SEARCH-2 is violated".

### 5.4 What is not tested

Stated explicitly, so it is a decision rather than an omission: no snapshot tests without a reviewed diff policy (they are the easiest test to update-until-green), no tests of framework behaviour, no tests whose failure would not change anyone's action. A test nobody will act on is a maintenance liability that also slows every CI run.

---

## 6. Feedback speed

DORA's finding that fast feedback is one of the capabilities flipping AI's stability effect from negative to positive ([01: 1.1]) makes latency a first-class requirement, not an optimisation:

- Pre-commit hook, target **<5s**: format, secrets scan, changed-file lint.
- `aios check`, target **<60s**: everything CI runs, locally, identical.
- CI on PR, target **<10min**: full suite plus all gates.
- Nightly: mutation sampling, full dependency audit, staleness sweep, trend reports.

The `aios check` = CI equivalence is a hard requirement. When local and remote checks differ, every failure becomes late feedback and the fast-feedback capability is lost regardless of how quick the individual checks are.
