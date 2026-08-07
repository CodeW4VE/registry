#!/usr/bin/env bash
# Build docs.w4ve.xyz and push it to the Hetzner box.
#
#   ./deploy_docs.sh            build, then rsync it up
#   ./deploy_docs.sh --dry-run  say what would change, send nothing
#
# The site is static and regenerated whole every time, so there is nothing to
# migrate and nothing to roll back: the previous build is simply gone. The
# nginx vhost lives at /etc/nginx/conf.d/docs.conf and is not touched here.
set -euo pipefail

HOST="${W4VE_DOCS_HOST:-gaturro}"
REMOTE="/usr/share/nginx/docs"
HERE="$(cd "$(dirname "$0")" && pwd)"
SITE="$HERE/site"
CLI="${W4VE_CLI:-$HERE/../w4ve/w4ve.py}"

DRY=()
[[ "${1:-}" == "--dry-run" || "${1:-}" == "-n" ]] && DRY=(--dry-run)

echo "==> rebuilding the site"
if [[ -f "$CLI" ]]; then
  python3 "$HERE/docs.py" --cli "$CLI"
else
  # No local checkout of the CLI: docs.py falls back to the latest release,
  # which is the right source anyway for a machine that is not the author's.
  python3 "$HERE/docs.py"
fi

echo "==> sending it to $HOST:$REMOTE"
# --delete because a piece removed from the catalog has to stop having a page.
rsync -az --delete "${DRY[@]}" \
  --chmod=D755,F644 \
  "$SITE/" "$HOST:$REMOTE/"

if [[ ${#DRY[@]} -eq 0 ]]; then
  echo "==> https://docs.w4ve.xyz/"
fi
