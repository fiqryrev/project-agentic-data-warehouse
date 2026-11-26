# 74: pull Langfuse images from Docker Hub so Dependabot can update them

## Goal

Dependabot could not update the Langfuse images: the update run on 2026-11-26 (run
45774828590) logged `private_source_authentication_failure {source: "docker.langfuse.com"}`.
Move both images to Docker Hub, same version and digests, so the weekly compose group covers
them.

## Plan (as approved)

Approved in chat on 2026-11-26: change `docker.langfuse.com/langfuse/<img>` to
`langfuse/<img>` in `infra/compose.yml`, keep tag and digest; note the move under the M0
versions table in `docs/m0-findings.md`, leaving the M0 record as it was; check the file
parses and both pins resolve; tests and checks.

## Decisions

- **Docker Hub, same digests:** `docker buildx imagetools inspect` on 4.83.0 gave the same
  digest on both registries (`langfuse` `sha256:a91445265d1f...`, `langfuse-worker`
  `sha256:a6eac4bb99df...`), so nothing that runs changes.
- **Short form `langfuse/<img>`**, like the other Docker Hub pins (`postgres`, `redis`).
- **No `docker compose config`:** the Bash guard blocks it (it prints `.env` secrets); the
  file was parsed with `yaml.safe_load` instead.
- **Resolved, not pulled:** Docker was not running, so the pins were resolved on Docker Hub
  with `imagetools inspect`, which needs no daemon.
- No reason for `docker.langfuse.com` was recorded; M8 took it from Langfuse's own compose file.

## Done

- `docker buildx imagetools inspect docker.io/langfuse/<img>:4.83.0` and
  `docker.langfuse.com/langfuse/<img>:4.83.0`, both images: same digests.
- `yaml.safe_load(infra/compose.yml)`: `langfuse-worker` and `langfuse-web` read the new refs.
- `docker buildx imagetools inspect docker.io/<pinned ref>`, both images: resolves to the pinned
  digest, linux/amd64 and linux/arm64.
- `uv run pytest -q`: PASS (411). `uv run ruff check .`: PASS. `make checks`: every checker OK
  up to `check_golden`; `check_worknote` reads committed files, so it runs after the commit.

## Open

- After merge: the next weekly Dependabot run should include the Langfuse images in the
  compose group; Langfuse releases after 4.83.0 then arrive as a normal update PR.
- `make up-obs` on the laptop pulls the images under the new names on the next start.
