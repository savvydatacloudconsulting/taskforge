#!/usr/bin/env bash
# Reproduce the pallets/click results from a fresh checkout, with no AI and no API key.
# Needs Linux (or WSL), git and Python 3.11+ with venv. Internet is used only to fetch click and pytest.
# Usage: bash scripts/reproduce_click.sh [work folder]
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mkdir -p "${1:-$root/taskforge_out/click_repro}" && cd "${1:-$root/taskforge_out/click_repro}" && pwd)"
setting() { python3 -c "import json,sys; v=json.load(open(sys.argv[1]))[sys.argv[2]]; print(' '.join(v) if isinstance(v,list) else v)" "$root/configs/click.json" "$1"; }
commit="$(setting base_commit)"
upstream=08b803cf32ceb2ae6a772c62d5da42757a897d44   # click's main branch on 26 Nov 2026
recipes=quantity_limit,eligibility_gate,validation_rejection,dedup_merge,rule_stacking,threshold_effect,audit_trail

echo "== set up click at $commit"
[ -x "$work/venv/bin/python" ] || python3 -m venv "$work/venv"
# shellcheck disable=SC2046
"$work/venv/bin/pip" install -q --disable-pip-version-check $(setting pip_packages)
[ -d "$work/click" ] || git clone -q https://github.com/pallets/click.git "$work/click"
git -C "$work/click" -c advice.detachedHead=false checkout -q "$commit"
# click reads its own package metadata; the workspaces still import their own src/ folder
"$work/venv/bin/pip" install -q --disable-pip-version-check --no-deps --no-build-isolation "$work/click"

export PYTHONPATH="$root/src" PYTHONDONTWRITEBYTECODE=1
tf() { "$work/venv/bin/python" -m taskforge "$@"; }
cd "$root"
rm -rf "$work/generated" "$work/harbor"

echo "== 1. generate the 5 tasks again from the recorded AI answers"
tf generate "$work/click" --name click -n 5 --seed 6 --recipes "$recipes" \
  --backend replay --replay-dir samples/replay/click --out "$work/generated"
echo "== 2. re-check the committed task packages"
tf check-all samples/tasks/click --repo "$work/click"
echo "== 3. the features must not exist upstream"
tf upstream samples/tasks/click --repo "$work/click" --ref "$upstream"
echo "== 4. export Harbor tasks"
tf export "$work/generated/accepted" --repo "$work/click" --config configs/click.json --out "$work/harbor"
echo "== 5. rehearse Harbor's two checks without Docker"
tf simulate "$work/harbor" --repo "$work/click"
echo "== the exported tasks match the committed ones"
diff -r "$work/harbor" samples/harbor/click && echo "identical"
