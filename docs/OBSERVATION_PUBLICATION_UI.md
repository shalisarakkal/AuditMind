# Read-only publication provenance and scanner-field preview

Current local successor: [guarded publication actions](OBSERVATION_PUBLICATION_ACTIONS.md) adds a separate default-off authorized HTTP/UI surface using the integrated consumer contract. The checkpoint description below is historical; legacy private entry points remain closed. Database activation remains separate.

Read-only checkpoint reviewed on 15 November 2026, following hosted-verified
integration `7e20935`. This increment remains unactivated. No public Publish/Undo
or publication-setting writer is added. No database migration is added here;
normal schema remains 0055, and migrations 0056-0058 still need coordinated
activation. The normal application has not been restarted for this increment.

## Finding workflow display

For a single finding, open Findings > Workflow > **Show publication history**.
The panel loads only when opened. It distinguishes no recorded publication,
recorded publication, completed Undo, unavailable history and recovery required.
It lists at most 20 decisions per page, newest first, with version-based navigation.
The current recorded generation remains visible when browsing an older page.

Each decision shows actor label, browser-local recorded time, reason, decision
source import, observation retention and before/after snapshot presence for Publish
receipts. Original owner import and decision source are separate; original Finding
UUID, asset/import ownership, workflow and creation time are not transferred.
UUIDs and contract names are under Technical source references. Undo receipts do
not claim to contain a new pair of source payload snapshots.

Members may read their organization's history. Only actual organization admins can
request the existing native scanner-field preview. Foreign tenant access is denied;
foreign source pointers cannot disclose another organization's filename. Publication
history responses are no-store and use a read-only repeatable-read transaction.

If storage migrations are absent or only reserved storage 0056 is installed,
the panel explains that scheduled database activation is required. It does not fabricate an empty history or raise an internal
server error solely because that storage is absent.

## Scanner-field comparison

For a supported native observation, open **Show source observations**, then
**Preview scanner-field differences**. This calls only the existing read-only
preview endpoint with an empty request. There are no replacement fields, apply
flags, write confirmation controls or publication buttons.

The panel shows original owner import, compared observation import, server recording
time and source-observed time (or Not provided). Only changed allowlisted fields
appear, with Current and Observation values. Null removal and shortened display
are explicit; full-value byte counts and hashes remain available in details.
The server limits displayed summaries, and React renders source strings as text.
Closing an in-flight preview ignores its late result. Retry/reload performs a fresh
read, and prerequisite failures clear the previous comparison.

## Recovery semantics and limits

Retention metadata is not eligibility or proof approval. It does not validate
current identity, materialized scanner-field equality or snapshot contents, and
never authorizes Publish/Undo. A future write must obtain a fresh authorized review.

Missing current generations, unsupported receipt contracts/mappings, unavailable
original owners or active-source observations, and missing/misowned snapshot pairs
produce explicit recovery messages. Historical source purge after Undo does not
pretend the decision can restore purged data. A retained observation reference can
outlive its original owner; the display distinguishes those conditions.

History reads project bounded ledger and ownership metadata only. They do not
select, hash, size or deserialize stored observation/snapshot payloads. No count,
Dashboard, workflow, scoring, Activity or source-field mutation is performed by
these views. Existing snapshot/retention policy and saved reports remain unchanged.

## Verification

Accepted verification on isolated application/database fixtures:

- Backend regression: **117 tests passed in 271.82 seconds**, covering publication
  reads, private consumers, native preview, identity binding, migrations and public
  write gates. Final focused read-only scope: **18 passed in 32.30 seconds**,
  including database-enforced read-only mode and pending-change preservation.
- Frontend: **595 tests across 62 files passed in 50.22 seconds**; lint passed.
- Complete installed-Chrome acceptance: **107 checks passed**; real native imports,
  role restrictions, unchanged Finding/workflow fields, mobile width and scoped Axe
  checks passed with no AI calls or page errors. Artifacts:
  `temp/testing/finding-workflow/phase3_browser_0dd64ddeb2b2`.
- The focused provenance Chrome run also passed. The initial full browser run
  reached 105 checks before a new fixture locator failed: Windows converted its
  separator to a question mark. A new UI separator regression test reproduced the
  display problem before the fix and passed afterward (10 component checks).
  The full browser rerun above uses the corrected source/locator.
- An initial backend assertion incorrectly assumed scan deletion removed its
  observation; the existing FK can retain the reference while clearing its owner.
  The read model and display now explicitly distinguish reference/owner retention.
- Isolated production build, high-severity Bandit, compilation and tracked/new-file
  secret/whitespace checks passed. Normal frontend chunks, database and processes
  were retained; generated acceptance type paths were restored after verification.

15 November check-in review reproduced HTTP 500 with reserved storage 0056 present
but the 0057 receipt columns absent. The failing regression was captured before
the fix. Availability checks now inspect catalog columns before selecting the
current ORM receipt contract. The post-fix backend regression passed **120 checks in 251.39 seconds**
(4 minutes 11 seconds), including the new partial-migration regression. Frontend/Chrome results above precede this narrow server
compatibility fix; they are not presented as reruns of it. High-severity security,
compilation and secret/whitespace checks passed again.

Exact-commit hosted Linux CI follows the push; its result is recorded in the
delivery confirmation. Local results do not authorize future write actions.

Still pending after this read-only increment: public provenance/recovery decisions
for exceptional histories, default-off organization setting, authorized guarded
Publish/Undo actions, unknown-outcome behavior, write-action Chrome acceptance,
write-feature review, regression/Chrome acceptance, exact-commit Linux CI and
coordinated activation.


### Guarded publication actions - local checkpoint, 2026-11-15

See [guarded scanner-field publication](OBSERVATION_PUBLICATION_ACTIONS.md) for the separate default-off organization setting, fresh single-finding Publish/Undo reviews, atomic invalidation and uncertain-outcome handling. Normal database activation remains pending; legacy private entry points remain closed. Verified locally: 94 post-fix backend checks, 117 broader backend checks, 602 frontend tests and 108 full Chrome checks passed. TypeScript, ESLint and the isolated production build passed. Commit/push, hosted CI and coordinated activation remain pending.
