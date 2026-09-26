# Test Change Report: root service relocation

- Task: move FastAPI composition from `copia.api.service` to `copia.service` and remove unused root layer packages.
- Report Type: `ACTUAL`
- Risk Level: `MEDIUM`
- Changed Test Files: existing tests importing or monkeypatching `copia.api.service`; 63 existing test files were mechanically updated to `copia.service`.
- Reviewer Verdict: `APPROVED_WITH_NOTES`
- Final Outcome: `PASSED`

## Justification

- Reason Category: `REFACTORING_NO_BEHAVIOR_CHANGE`
- Why The Test Changed: the old module is deleted, so tests must import and patch the new defining module.
- Old Expected Behavior: all existing assertions pass through `copia.api.service`.
- New Expected Behavior: the same assertions pass through `copia.service`.
- Affected Acceptance Criteria: unchanged HTTP contract, route order, runtime configuration, and test behavior.
- Specification Changed: `NO` for behavior; the explicitly requested Python entrypoint path changes.
- Incorrect Artifact: `BOTH` (old composition location and imports coupled to it).

## Coverage

- Existing Test Deleted: `NO`
- Existing Assertion Removed or Weakened: `NO`
- Human Approval Required: `NO`
- Human Approval Status: `NOT_REQUIRED`

## Review

- Is The Justification Valid: `YES`
- Does The Test Still Protect The Same Behavior: `YES`
- Was Production Code Incorrectly Avoided: `NO`
- Should Production Code Have Been Fixed Instead: `NO`

## Evidence

- Baseline OpenAPI, route order, project root, and profile path saved before migration.
- Verification: `./harness/scripts/check.sh` passed with 278 tests; OpenAPI, route order, project root, and profile path match the baseline; all discovered Copia modules import successfully.
