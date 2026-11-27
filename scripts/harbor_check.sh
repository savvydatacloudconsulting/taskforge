#!/usr/bin/env bash
# Run Harbor's own two checks on every task: "nop" must score 0.0 and "oracle" must score 1.0.
# Needs a running Docker and Harbor 0.25.x:  pip install "harbor==0.25.*"
# Usage: bash scripts/harbor_check.sh [tasks folder] [output folder]
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tasks="${1:-$root/samples/harbor/click}"
out="${2:-$root/taskforge_out/harbor_runs}"
harbor="${HARBOR:-harbor}"
command -v "$harbor" >/dev/null || { echo "harbor is not on PATH (or set HARBOR=/path/to/harbor)"; exit 2; }
docker info >/dev/null 2>&1 || { echo "Docker is not running"; exit 2; }
"$harbor" --version
bad=0
rm -rf "$out"
for task in "$tasks"/*/; do
  name="$(basename "$task")"
  mkdir -p "$out/$name"
  for agent in nop oracle; do
    want=0; [ "$agent" = oracle ] && want=1
    "$harbor" run -p "$task" -a "$agent" -k 1 -o "$out/$name/$agent" --no-delete -y >"$out/$name/$agent.log" 2>&1 || true
    # no reward file means the environment failed; report it as null instead of stopping the script
    reward="$(find "$out/$name/$agent" -name reward.txt -exec cat {} + 2>/dev/null | head -n 1 || true)"
    if python3 -c "import sys; sys.exit(0 if sys.argv[1] and float(sys.argv[1]) == float(sys.argv[2]) else 1)" "$reward" "$want"; then
      verdict=OK
    else
      verdict=WRONG; bad=$((bad + 1))
    fi
    printf '%-48s %-7s reward %-6s expected %s.0  %s\n' "$name" "$agent" "${reward:-null}" "$want" "$verdict"
  done
done
[ "$bad" = 0 ] && echo "all checks passed" || { echo "$bad check(s) failed; see the logs in $out"; exit 1; }
