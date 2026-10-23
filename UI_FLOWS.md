# Current UI flows

Reviewed 22 October 2026. See the [manual](docs/USER_MANUAL.md) for browser
instructions and [release readiness](docs/RELEASE_READINESS.md) for open gates.
This replaces the original aspirational flows, not final acceptance evidence.

## Data and scoring

Sign in with an existing account and select an authorized organization. Browse
Assets, Findings and Scans with shared filters/pagination. Import supported files
using configured ingestion profiles. Profile mapping is not a live scanner
connection or a universal native Qualys parser. Dashboard scores are deterministic;
there is no dashboard action that silently sends evidence to Claude.

## Documents

Authorized organization administrators manage organization text/Markdown
documents, versions and indexing. Shared standards are inherited read-only.
Upload, publication, indexing, retirement and deletion are distinct lifecycle
states; upload alone does not make a document retrievable. Review the external
processing disclosure before approving report consent. Framework checkboxes do
not download standards or grant licensing rights. Platform administration and
organization write authority are distinct; read-only access cannot approve consent.

## Reports

Open Reports and select generation mode. The local rule-based test is not an AI
assessment. AI mode requires current organization consent, a configured enabled
provider, usable indexed evidence, healthy worker and quota headroom. Enter title
and frameworks. The current dialog lacks date controls although the API supports dates.

Generation is asynchronous: inspect status and failure details. Cancellation
prevents publication but cannot abort an issued request. Live job status and
cancellation are refreshed before each provider attempt/reservation. Completed reports are saved snapshots, not editable
live dashboards. Authorized members can view and download HTML/PDF subject to retention.

Provider credentials are server configuration, not browser Settings fields.
Demo mode disables real inference: consent alone cannot enable it.

## Proposed, not current promises

Live cloud/scanner discovery, general SSO onboarding, complete remediation
assignment/approval workflows and local generative reporting are not established
by these flows. Consult the plan before treating proposed screens as implemented.
