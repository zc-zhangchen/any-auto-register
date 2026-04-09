# Microsoft Mail Import Filtering Design

## Background

The current Microsoft mail import flow accepts plaintext rows and writes them directly into the local account pool. That works for simple ingestion, but it also allows invalid or already-restricted Microsoft accounts to enter the database. In practice, some imported Hotmail / Outlook accounts later fail during OAuth token exchange with:

- `invalid_grant`
- `error_description: User account is found to be in service abuse mode.`

Those accounts should be rejected during import rather than entering the pool and failing later at runtime.

The current backend strategy class is named `OutlookImportStrategy`, but its actual behavior already serves both Outlook and Hotmail imports through the shared `microsoft` provider path. The naming and structure should be updated to reflect that broader responsibility.

## Goals

- Keep Outlook and Hotmail under one shared backend import strategy.
- Rename the strategy to reflect Microsoft-wide scope rather than Outlook-only scope.
- Change Microsoft import from direct plaintext-to-database insertion into a staged pipeline.
- Introduce a rule-based filtering abstraction for Microsoft import records.
- Add a named rule called **微软邮箱可用性检测**.
- Reject accounts during import when Microsoft reports `service abuse mode`.
- Require OAuth credentials (`client_id` and `refresh_token`) for every imported Microsoft account.
- Return explicit per-line failure reasons to the UI.

## Non-Goals

- No redesign of AppleMail import.
- No asynchronous background validation after import.
- No broad frontend redesign beyond using existing result/error rendering.
- No unrelated refactor of the rest of the mail import system.

## User-Facing Behavior

Microsoft import will continue to accept plaintext lines in the existing format:

- `email----password----client_id----refresh_token`

Rows that only provide `email----password` will no longer be accepted for Microsoft import.

When importing Outlook or Hotmail accounts:

1. Each row is parsed into a normalized Microsoft import record.
2. The record is evaluated by the Microsoft import rule engine.
3. Only records that pass all rules are inserted into the database.
4. Rejected rows are reported back in the import response with concrete reasons.

Example rejection reasons:

- `行 2: 缺少 client_id 或 refresh_token，无法通过微软邮箱可用性检测`
- `行 5: 微软邮箱可用性检测未通过，账号处于 service abuse mode`
- `行 8: 邮箱已存在: example@hotmail.com`

The frontend keeps using the existing import result panel and error list rendering.

## Architecture

### Strategy naming

Rename:

- `OutlookImportStrategy` -> `MicrosoftMailImportStrategy`

Rationale:

- The backend provider type is already `microsoft`.
- The strategy is shared by both Outlook and Hotmail.
- The new name matches the actual responsibility boundary.

### Import pipeline

Microsoft import will move to this pipeline:

1. Raw text input
2. Microsoft record parser
3. Microsoft rule filter engine
4. Persistence of passed records
5. Aggregated import response

`MicrosoftMailImportStrategy` remains the orchestration layer and should not directly own all validation details.

### New abstractions

Add a focused rules subsystem under `services/mail_imports/` for Microsoft imports.

Recommended units:

- `MicrosoftMailImportRecord`
  - normalized parsed row model
- `MicrosoftMailImportRule`
  - abstract rule interface
- `MicrosoftMailImportRuleEngine`
  - executes rules for each record
- `MicrosoftMailboxAvailabilityRule`
  - implementation of **微软邮箱可用性检测**

The strategy will:

- parse lines into records
- run the rule engine
- persist only accepted records
- collect failures for the response

## Rules

### Shared Microsoft rules

Both Outlook and Hotmail imports use the same Microsoft rule set.

Minimum rule set:

1. **Basic format rule**
   - email must be present and contain `@`
   - password must be present

2. **OAuth credential completeness rule**
   - `client_id` must be present
   - `refresh_token` must be present
   - missing either value rejects the row

3. **Uniqueness rule**
   - email must not already exist in `OutlookAccountModel`

4. **微软邮箱可用性检测**
   - attempt Microsoft OAuth token validation using the imported credentials
   - if the response indicates `invalid_grant` and the description contains `service abuse mode`, reject the row

### Strict-mode decision

The approved behavior is strict:

- Microsoft rows without OAuth credentials are rejected immediately.
- They are not stored in the database.
- The system does not allow “password-only import now, fail later at runtime” for Microsoft accounts.

## Microsoft mailbox availability check

### Responsibility

The **微软邮箱可用性检测** rule determines whether a Microsoft mailbox is acceptable for import.

### Scope

Applies to:

- Outlook
- Hotmail

Does not apply to:

- AppleMail
- other mail providers

### Detection contract

The rule will reuse the existing Microsoft OAuth token acquisition path rather than inventing a new probe format.

The first required rejection case is:

- OAuth error `invalid_grant`
- and response text or parsed description contains `service abuse mode`

This result means:

- the account is considered unusable for this project
- the row must not be imported

### Error reporting

The import response should normalize that failure into a user-readable message, rather than exposing only raw provider JSON.

Preferred message style:

- `微软邮箱可用性检测未通过，账号处于 service abuse mode`

The original lower-level error can still be logged internally if useful, but the import response should stay concise and actionable.

## Data flow

For each actionable Microsoft import line:

1. Parse plaintext row into fields.
2. Build `MicrosoftMailImportRecord`.
3. Run rule engine.
4. If any rule fails:
   - increment failed count
   - append line-scoped error message
   - do not write to DB
5. If all rules pass:
   - create `OutlookAccountModel`
   - commit to DB
   - include accepted account metadata in response

This keeps parsing, filtering, and persistence as separate steps.

## Frontend impact

No major UI redesign is required.

`MailImportPanel.tsx` already supports:

- showing import success/failure counts
- rendering returned error lines

Optional text updates may be made to the Microsoft import helper text so that it clearly states:

- Microsoft import requires `email----password----client_id----refresh_token`
- Outlook and Hotmail both use Microsoft mailbox availability filtering

## Testing

Add or update tests to cover at least:

1. Microsoft row with full OAuth credentials and successful availability check -> imported
2. Missing `client_id` -> rejected, not imported
3. Missing `refresh_token` -> rejected, not imported
4. Duplicate email -> rejected, not imported
5. OAuth response with `service abuse mode` -> rejected, not imported
6. Outlook and Hotmail rows both use the same rule engine and validation path
7. Import response aggregates mixed success/failure rows correctly

Tests should verify both:

- response summary/error output
- final database state

## File impact

Expected primary files:

- `services/mail_imports/providers.py`
- `services/mail_imports/registry.py`
- `services/mail_imports/base.py`
- `services/mail_imports/schemas.py`
- new Microsoft import rule module(s) under `services/mail_imports/`
- `frontend/src/components/settings/MailImportPanel.tsx` (only if helper text is clarified)
- test files for Microsoft import validation behavior

## Rollout notes

This change tightens Microsoft import acceptance. Existing import text that omits OAuth credentials will start failing, by design. That is acceptable because the goal is to keep unusable Microsoft accounts out of the pool.

## Final design summary

The system will rename the Microsoft import strategy to reflect actual scope, replace direct Microsoft plaintext import with a parser + rule-engine pipeline, and introduce a reusable **微软邮箱可用性检测** rule that rejects abuse-mode Microsoft accounts before they ever enter the local mailbox pool.
