"""DeployTarget: the seam between `harness deploy` and where an agent
actually runs. Same image, same interface, different backend -- v1
ships `local` (docker compose) and `k8s` (generic Helm chart)."""
