# Acquired standards source archive

Review synchronization (2026-10-22): Source acquisition does not establish complete framework coverage. Current installed NIST content is distinct from CIS/ISO reference-only entries. Vendored license text is unchanged; its upstream-relative CONTRIBUTING link is not a missing local product file.
See [current code review and release gates](../RELEASE_READINESS.md).

Keep original acquired standards here, with source, version, hash, and licensing information. Do not add credentials, private organization documents, or licensed standards whose terms do not permit repository storage/distribution.

## NIST CSF 2.0

- File: [nist_csf_2_catalog.json](nist-csf-2.0/nist_csf_2_catalog.json)
- Format: official NIST OSCAL JSON catalog, not a PDF of the publication.
- Framework edition: CSF 2.0; electronic catalog version: 1.2.0.
- Acquired: 2026-10-08.
- Source: https://github.com/usnistgov/oscal-content/blob/78650f02ad9321bb7b817846f8fbd4f2bcd620de/nist.gov/CSF/v2.0/json/NIST_CSF_v2.0_catalog.json
- Source commit: `78650f02ad9321bb7b817846f8fbd4f2bcd620de`.
- SHA-256: `4836943f21d393f2821df85ada4e6f3c0617243b4ddf44263fe68205400210b4`.
- License: [upstream license](nist-csf-2.0/LICENSE.md), US government public domain / CC0 dedication. No NIST endorsement implied.
- Application copy: [backend catalog](../../backend/app/data/nist_csf_2_catalog.json). Hashes were verified identical when this archive was created. Update the archive, application copy, source revision, and hash together when adopting a new catalog version.

## CIS and ISO

No official full-text CIS or ISO standard has been acquired. The current implementation provides source references and an authorized upload path. Do not mistake those references for complete indexed standards. Any future acquired copy must be stored only where its license and organization access restrictions permit; this repository is not an appropriate default for restricted material.

## Runtime models are separate

The BGE-M3 model is a runtime dependency, not a standards document. Model weights are stored in the configured Hugging Face cache, not in this repository. The pinned model revision and explicit download/smoke-test command are maintained by the embedding setup script.
