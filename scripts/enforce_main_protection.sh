#!/usr/bin/env bash
set -euo pipefail

repo="${1:-$(gh repo view --json nameWithOwner -q '.nameWithOwner')}"
branch="${2:-main}"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required."
  exit 1
fi

echo "Applying repository merge policy for ${repo}..."
gh api --method PATCH "repos/${repo}" --input - <<'JSON'
{
  "allow_merge_commit": false,
  "allow_squash_merge": true,
  "allow_rebase_merge": true,
  "delete_branch_on_merge": true
}
JSON

echo "Applying branch protection for ${repo}:${branch}..."
gh api --method PUT "repos/${repo}/branches/${branch}/protection" --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Workflow Guard",
      "Lint & Format",
      "Type Check",
      "Test",
      "Integration Tests",
      "Security Scan",
      "Build"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
JSON

echo "Verifying protection summary for ${repo}:${branch}..."
gh api "repos/${repo}/branches/${branch}/protection" --jq '{enforce_admins: .enforce_admins.enabled, required_status_checks: .required_status_checks.contexts, required_linear_history: .required_linear_history.enabled, allow_force_pushes: .allow_force_pushes.enabled, allow_deletions: .allow_deletions.enabled}'

echo "Main branch protection is enforced."
