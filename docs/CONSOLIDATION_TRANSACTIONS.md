# Consolidation metadata transaction component

Current follow-up: [Stage A release review](CONSOLIDATION_RELEASE_REVIEW.md) describes the local default-off proof/lifecycle/publication/UI implementation under final verification. The earlier checkpoint below retains its historical scope. No normal-data activation has occurred.

PB-1.3 Stage A internal checkpoint, 12 November 2026.

This increment adds an internal transaction component on schema `0052`. It does
not enable consolidation. No route calls it, the production `publish` entry point
unconditionally refuses publication, and no setting/client parameter can bypass
that gate. The existing public pair preview remains diagnostic and read-only.

## Transaction contract

The private staging primitive uses the caller's existing read-committed Session.
It opens a savepoint and never commits. The future integrated publisher must
perform visibility, proof, invalidation and audit work in the same outer
transaction before committing. Do not expose a metadata-only writer.

1. Reject pending ORM work and require explicit confirmation.
2. Acquire try-only existing job-admission and organization-publication advisory
   locks, in that order. Reuse the audited namespaces; allocate no new namespace.
3. Lock and refresh the organization, actual membership and account. Only active
   organization admins without a pending password change qualify; platform-only
   access does not qualify. Row locks use NOWAIT.
4. Check an organization-scoped request ID after fresh authorization. Identical
   actor/request retries return the original receipt. Changed reuse conflicts.
5. Discard cached reads, lock the two finding rows in UUID order, and recompute
   the complete metadata admission context under the fences.
6. Compare the actor-bound internal token and expected group version. Public
   foundation fingerprints are not accepted as this internal token.
7. Stage the root generation, decision, exact two members and typed dependencies
   in one savepoint. Failure rolls back every metadata write and keeps the caller
   Session usable. Re-admission retains prior receipts/dependency generations.

Unique/FK index conflicts can wait even when row locks use NOWAIT. The component
therefore caps lock waits at 750 ms, honors smaller caller timeouts and restores
the previous setting. Savepoint failure also restores the original timeout.
Unknown database errors propagate; identified lock/unique/FK conflicts become 409.

## Context and source guards

Admission reuses bounded native Nessus pair validation and the source manifest.
It additionally checks independently reviewed third findings with the same native
identity, using only latest binding decisions and then revalidating source context.
Revoked or stale identity history is not current authority. Candidate reads are
bounded; excessive matches fail closed. No observation payload is selected for
this identity scan.

Related pending/running archive/restore/purge work blocks admission, including
manifest sources beyond the two original finding owners. Pending/running imports
in the organization also cause a prompt conflict. Existing workflow updates are
unchanged and do not acquire these new private staging semantics.

The internal plan uses `consolidation-metadata-admission-v1`. It is not an enabled
publication contract: it lacks the final feature-policy and consumer integration
context. Future production publication must bind those gates explicitly and must
not accept these internal plans as a release bypass.

## Preservation and remaining release gates

The primitive never changes finding UUID/source ownership, workflow, verification,
visibility, counts, Dashboard, scoring, import matching or source lifecycle. Its
receipt is metadata history, not an Activity assertion that consolidation was
published. There is no production undo action yet; tests seed the proper undone
ledger shape solely to exercise safe re-admission.

Before enabling publication, finish all consumer visibility/revision changes,
group-aware proof, source lifecycle/reappearance guards, final authorization and
feature-policy admission, Activity events and guarded Preview/Apply/Undo UI.
The existing evidence-qualified/status-aware scoring settings are unchanged.

## Verification

Validation for this component completed locally:

- 71 foundation/dependency/admission regression checks passed before the final
  bounded-index-wait guard.
- All 82 final transaction, canonical, identity-comparison and preview performance
  checks passed in 155.11 seconds.
- All 31 final unit/transaction checks passed in 50.97 seconds. These overlap the
  broader runs; their counts are not a distinct-test total.
- Tests reproduce an uncommitted uniqueness conflict, verify prompt 409 handling,
  preserve stricter caller timeouts, and exercise competing connections and
  actor-bound review tokens.
- The final high-severity Bandit gate exited 0 (no high findings); existing
  23 medium and 12 low findings remain. Whitespace checks passed.
- Static call-site inspection confirms no running application route or service
  calls this private staging component. No normal data was staged or published.

The preceding foundation was committed through `112646f`; all four hosted Linux jobs passed in
[run 43275574591](https://github.com/shalisarakkal/AuditMind/actions/runs/43275574591).
That hosted result covers the preceding foundation only. Hosted CI must also be
verified for the pushed transaction-component checkpoint. No migration or
application restart is required for this step.

Tests exercise atomic rollback, caller-owned commit, idempotency and changed reuse,
stale/role/account/source checks, competing connections, generation history,
actor-bound plans, bounded waits and the closed production gate. Disposable
PostgreSQL uses system temporary storage with both application/test URLs isolated;
normal application data is not used as a fixture. No migration or restart is
required for this internal-only component.

See [foundation review](CONSOLIDATION_FOUNDATION_REVIEW.md) and
[the staged design](REVIEWED_FINDING_PUBLICATION_DESIGN.md).


Subsequent internal integration: [visibility/count/scoring changes](CONSOLIDATION_VISIBILITY.md).
The metadata-only primitive retains its original behavior; the new private
wrapper adds atomic visibility effects. Neither is exposed as publication.
The transaction checkpoint `1d5c86b` passed all four hosted Linux jobs in
[run 43292318027](https://github.com/shalisarakkal/AuditMind/actions/runs/43292318027).
