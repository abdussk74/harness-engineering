# ADR 0003: Container build and DeployTarget abstraction

## Status

Accepted (M5, M10).

## Context

The brief requires: the same Docker image runs locally under
`harness dev` and deploys unchanged elsewhere; a `DeployTarget`
interface that assumes neither a cluster nor a laptop; a working local
target from day one and a real (if not necessarily day-one-run) k8s/Helm
target behind the same interface.

Since `a2a-harness` isn't published to a registry, every image build
needs the SDK's own source available at build time, not just the
agent's own files.

## Decision

**One Dockerfile template, three stages**, rendered by
`harness_cli.codegen.dockerfile` (developers never hand-write it):
`builder` (shared uv-installed deps layer), `dev` (extends `builder`,
hot reload via bind mount — what `harness dev` runs), `runtime` (final,
non-root, `HEALTHCHECK`, exec-form CMD — the actual deploy unit, and
what every `DeployTarget` builds).

**Build context is always the Harness workspace root**, not the
agent's own directory — the image installs `a2a-harness` from source
(editable) alongside the agent's module, copied in as a separate layer.
This is a stated simplification: it assumes a monorepo layout where the
SDK and every agent share one workspace root. A published-package
world would let each agent's own `pyproject.toml` declare `a2a-harness`
as a normal dependency and drop this constraint — noted as a future
change, not built now.

**`DeployTarget` protocol** (`harness_cli/deploy_targets/base.py`):
`build`/`deploy`/`status`/`logs`/`teardown`, operating on an
`AgentBuildSpec` in and a `BuildResult`/`DeployResult`/`DeployStatus`
out. Two implementations:

- **`LocalDeployTarget`**: the `runtime`-stage image as a plain
  `docker run` container. Deliberately *not* the `harness dev` compose
  topology — no hot reload, no telemetry stack, since those are the
  dev inner loop's job, not a deploy target's. "Deployed, but on my
  laptop" should look like production minus the cluster, not like dev
  mode.
- **`KubernetesDeployTarget`**: multi-arch `buildx build --push`, then
  `helm upgrade --install` against a generic chart
  (`helm/harness-agent/`) parameterized by image, port, entrypoint, and
  arbitrary env vars.

## Consequences

- Two real bugs surfaced by building this for real (not just designing
  it): a missing `README.md` broke hatchling's build validation inside
  the image (fixed by copying it into the builder stage); the editable
  `a2a-harness` install points back at `/app/src`, which doesn't exist
  in a fresh `runtime` stage unless `src/` is explicitly copied there
  too, not just `.venv`. Both are now baked into the Dockerfile
  template, not left as tribal knowledge.
- `KubernetesDeployTarget` was validated via `helm lint`/`helm template`
  (including confirming the `required` entrypoint guard fires) and unit
  tests asserting the exact `docker`/`helm`/`kubectl` commands it
  constructs — not a live cluster deploy. PLAN.md scoped this
  explicitly ("buildable, even if I don't run it day one"); a
  kind-cluster-plus-registry round trip is real future validation work,
  not done here.
- `LocalDeployTarget` *was* verified live end to end (build → deploy →
  status → teardown against a real container), since it needed no
  registry or cluster to test honestly.
