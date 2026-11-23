# 42: dependency alerts, code scanning and image digests

## Goal

Phase 2 of the 2026-11-23 security review, supply chain: S7 (no dependency alerts, no code
scanning, no security policy) and S8 (four images pinned by tag only).

## Plan (as approved)

Approved in chat on 2026-11-23 with phase 2 (issues #42, #43, #44):

- `.github/dependabot.yml`: uv at the root, docker for `airflow/`, docker-compose for `infra/`,
  github-actions; weekly, grouped.
- A CodeQL workflow for Python: read-only token plus `security-events: write`, actions pinned by
  SHA.
- `SECURITY.md`: supported state, how to report, scope.
- S8: digests for `apache/airflow`, `ghcr.io/astral-sh/uv` and both `postgres` images, resolved
  from the registries; a test that every pulled image and Dockerfile base carries a digest.

## Decisions

- **Digests from the registry APIs**, not `docker buildx imagetools inspect`: Docker was not
  running on the agent's machine. Each is the multi-arch index (`application/vnd.oci.image.index.v1+json`),
  the same object `imagetools inspect` reports, so arm64 and amd64 hosts both resolve:
  - `apache/airflow:3.3.2-python3.12@sha256:9df9c8be4096b9cc626bd7cb1f2b8c712eef66c59c615f8c7e6200871ca10bd1`
  - `ghcr.io/astral-sh/uv:0.11.8@sha256:3b7b60a81d3c57ef471703e5c83fd4aaa33abcd403596fb22ab07db85ae91347`
  - `postgres:17.6-alpine@sha256:ef257d85f76e48da1c64832459b59fcaba1a4dac97bf5d7450c77753542eee94`
- **Images built here stay on their own tag** (`wh-airflow`, `adw-auto-ontology*`): they have a
  `build:` and pin their base in the Dockerfile; the compose test exempts only those.
- **Dependabot: docker for `airflow/`, docker-compose for `infra/`**, as the review asked; a
  separate group per ecosystem and a PR limit of 3, so a week is a few PRs. Pins stay pins:
  Dependabot updates the tag and the digest together.
- **CodeQL does not block merges by itself**; it reports to code scanning. `build-mode: none`
  (Python needs no build). It runs on PRs, on `main` and weekly. codeql-action v4.39.4, the
  current major, pinned by SHA like the other actions.
- **CodeQL job also has `actions: read`** (Codex review on #45): GitHub needs it to upload
  results in a private repository. This one is public and the first analysis uploaded without it
  (`refs/pull/45/merge`, 2026-11-23T05:31:34Z); the read-only grant keeps the scan working if the
  visibility ever changes.
- **SECURITY.md lists the accepted risks** decided so far: Airflow without login, the master
  secret in the Airflow tasks (#40), and the keyless rerank route (owner, 2026-11-23, for #44).
  #44 then only touches the README, the gateway comment and the guard, so the two PRs do not
  edit the same file. No reply-time promise: one person answers as time allows.
- **Toolbelt** lists CodeQL and Dependabot (CI only; Dependabot opens PRs, the owner merges).

## Done

- Registry lookups: `auth.docker.io` token, then `HEAD /v2/<repo>/manifests/<tag>` on
  `registry-1.docker.io` and `ghcr.io`; `docker-content-digest` above.
- `gh api repos/github/codeql-action/commits/v4` → `1bd86f2…` = tag v4.39.4.
- No tag-only image left outside `infra/auto-ontology/upstream/` (grep of `image:`, `FROM`,
  `--from=`).
- `uv run pytest -q`: PASS. `make checks`: PASS.

## Open

- OWNER: turn on Dependabot alerts, Dependabot security updates and private vulnerability
  reporting in the repository settings (SECURITY.md points reporters there).
- OWNER: rebuild once (`make up-core`, `make up-obs`) to pull by digest; same images as the tags
  today.
- Knowledge: no new lesson.
