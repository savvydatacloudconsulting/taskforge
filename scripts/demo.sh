#!/usr/bin/env bash
# Short commands for recording the demo video (see docs/DEMO_SCRIPT.md). Linux or WSL with Docker.
# Each step prints the real command it runs, so the viewer can see it.
#   bash scripts/demo.sh setup      once, before recording
#   bash scripts/demo.sh read | generate | task | harbor | cheat | results
set -euo pipefail
cd "$(dirname "$0")/.."
work="$HOME/tf-demo"      # click clone and tool environments (never printed)
out=/tmp/tf-demo          # everything the steps write, so no user name appears on screen
task=click__eligibility_gate__04
recipes=quantity_limit,eligibility_gate,validation_rejection,dedup_merge,rule_stacking,threshold_effect,audit_trail
python="$work/venv/bin/python"
click="$work/click"
harbor="${HARBOR:-$(command -v harbor || echo "$work/harbor-venv/bin/harbor")}"
export PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1
mkdir -p "$out"

show() { printf '\n\033[1;36m$ %s\033[0m\n' "$*"; }
pause() { if [ -t 0 ]; then read -rs _; fi; }
clear_screen() { if [ -t 1 ]; then clear; fi; }

need_setup() {
  [ -x "$python" ] && [ -d "$click" ] && [ -x "$harbor" ] || { echo "run first: bash scripts/demo.sh setup"; exit 2; }
}

harbor_run() {  # harbor_run <nop|oracle>
  rm -rf "$out/harbor-$1"
  show "harbor run -p samples/harbor/click/$task -a $1 -k 1 -o $out/harbor-$1 --no-delete -y"
  "$harbor" run -p "samples/harbor/click/$task" -a "$1" -k 1 -o "$out/harbor-$1" --no-delete -y
  printf '\033[1;33mreward (%s): %s\033[0m\n' "$1" "$(find "$out/harbor-$1" -name reward.txt -exec cat {} +)"
}

case "${1:-}" in
  setup)
    bash scripts/reproduce_click.sh "$work" >"$out/setup.log" 2>&1 || { tail -n 20 "$out/setup.log"; exit 1; }
    echo "click and the checks are ready"
    if [ ! -x "$harbor" ]; then
      python3 -m venv "$work/harbor-venv"
      "$work/harbor-venv/bin/pip" install -q --disable-pip-version-check 'harbor==0.25.*'
      harbor="$work/harbor-venv/bin/harbor"
    fi
    echo "building the task image once, so that recording is not slowed down"
    harbor_run oracle >"$out/warmup.log" 2>&1 || { tail -n 20 "$out/warmup.log"; exit 1; }
    tail -n 1 "$out/warmup.log"
    echo "ready to record"
    ;;
  read)
    need_setup
    show "taskforge analyze click --name click"
    "$python" -m taskforge analyze "$click" --name click
    show "cat configs/click.json"
    head -n 5 configs/click.json
    ;;
  generate)
    need_setup
    rm -rf "$out/video"
    show "taskforge generate click -n 5 --seed 6 --backend replay --replay-dir samples/replay/click"
    "$python" -m taskforge generate "$click" --name click -n 5 --seed 6 --recipes "$recipes" \
      --backend replay --replay-dir samples/replay/click --out "$out/video"
    ;;
  task)  # three screens; press Enter to move on
    folder="samples/harbor/click/$task"
    show "ls $folder"
    (cd "$folder" && find . -type f | sed 's#^\./##' | sort)
    pause
    clear_screen
    show "cat $folder/instruction.md"
    sed -n '/^## Requirements/,/^## Public interface/p' "$folder/instruction.md" | sed '$d'
    pause
    clear_screen
    show "grep -A8 'if not self.allow_dash' $folder/solution/solution.patch"
    grep -A8 'if not self.allow_dash' "$folder/solution/solution.patch"
    ;;
  harbor)
    need_setup
    harbor_run nop
    harbor_run oracle
    ;;
  cheat)
    need_setup
    show "python scripts/click_negative_controls.py click --only $task"
    "$python" scripts/click_negative_controls.py "$click" --only "$task" || true
    ;;
  results)
    show "cat evidence/click/harbor_docker.log"
    cat evidence/click/harbor_docker.log
    ;;
  *)
    sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
