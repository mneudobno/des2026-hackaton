#!/usr/bin/env bash
# Demo closing slide — overlay the build window's git history on screen.
#
# Usage (T+1:55, immediately before judging):
#   bash scripts/demo_history.sh                    # default: last 2 hours
#   bash scripts/demo_history.sh "2 hours 15 min"   # custom window
#
# Output is plain text; pipe into `pbcopy` (Mac) or paste into the dashboard's
# overlay slot. Two columns: time-ago + subject.

set -euo pipefail

since="${1:-2 hours ago}"
limit="${2:-20}"

cd "$(dirname "$0")/.."

cat <<EOF
Two hours. Three teammates. One pluggable adapter surface.

EOF

git log --since="$since" \
        --pretty=format:'  %cr · %s' \
        --no-merges \
  | head -n "$limit"

echo ""
echo ""
total=$(git log --since="$since" --no-merges --oneline | wc -l | tr -d ' ')
files=$(git log --since="$since" --no-merges --name-only --pretty=format: \
          | awk 'NF>0' | sort -u | wc -l | tr -d ' ')
echo "  $total commits · $files files touched · git log --since=\"$since\""
