#!/usr/bin/env bash
# Fixed regression seeds plus a reproducible rotating corpus; every batch must pass.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
players="${1:?Usage: scripts/daily-simulations.sh <2|3|4> [rotating-seed]}"
seed="${2:-$(date -u +%Y%m%d)}"
case "$players" in 2|3|4) ;; *) echo "Players must be 2, 3 or 4." >&2; exit 2 ;; esac
[[ "$seed" =~ ^[0-9]+$ ]] || { echo "Seed must be a nonnegative integer." >&2; exit 2; }
evidence="daily-evidence/simulations-$players"
mkdir -p "$evidence"
git rev-parse HEAD > "$evidence/commit.txt"
status=0
for corpus in fixed rotating; do
  start=0
  [[ "$corpus" == fixed ]] || start="$seed"
  for kingdom in preset random; do
    for lineup in economy engine attack economy-engine-attack engine-attack-economy attack-economy-engine; do
      IFS=- read -r -a profiles <<< "$lineup"
      name="$corpus-$kingdom-$lineup"
      echo "Players=$players kingdom=$kingdom profiles=$lineup seeds=$start..+24"
      if scripts/simulate.sh --players "$players" --kingdom "$kingdom" \
        --profiles "${profiles[@]}" --games 25 --seed "$start" \
        > "$evidence/$name.json" 2> "$evidence/$name.log"; then
        echo "$name passed"
      else
        echo "$name FAILED; see $evidence/$name.{json,log}" >&2
        status=1
      fi
    done
  done
done
exit "$status"
