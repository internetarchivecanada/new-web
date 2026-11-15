#!/bin/bash
# Run on the laptop:  tools/studio.sh deploy | start | stop | status | report
# Code lives in ~/newweb on the studio, the database in /Volumes/4tb-ext/data/newweb.
# Jobs run in screen sessions (nw-*), which do NOT survive a studio reboot: run "start" again after one.
set -u
HOST=${STUDIO:-studioj}
JOBS="hn bluesky gharchive liveness spn listing shots"
case "${1:-}" in
deploy)
  rsync -a --delete --exclude __pycache__ --exclude .git --exclude venv --exclude logs "$(dirname "$0")/../" "$HOST:newweb/"
  ssh "$HOST" 'cd ~/newweb && [ -x venv/bin/python ] || /opt/homebrew/bin/python3.12 -m venv venv && venv/bin/pip -q install websockets playwright pillow && mkdir -p logs /Volumes/4tb-ext/data/newweb'
  ;;
start)
  for j in $JOBS; do
    ssh "$HOST" "cd ~/newweb && screen -ls | grep -q '\.nw-$j\s' && echo 'nw-$j already running' || { screen -dmS nw-$j bash -c 'while true; do venv/bin/python -m newweb.$j >> logs/$j.log 2>&1; echo restart >> logs/$j.log; sleep 30; done'; echo 'started nw-$j'; }"
  done
  ;;
stop)
  # Quitting a screen can leave the Python child running, so kill both.
  ssh "$HOST" "for j in $JOBS; do screen -S nw-\$j -X quit 2>/dev/null; done; pkill -f 'venv/bin/python -m newweb\.' ; screen -ls | grep nw- || echo stopped"
  ;;
status)
  ssh "$HOST" "screen -ls | grep nw-; pgrep -fl 'python -m newweb\.'; cd ~/newweb && tail -n 2 logs/*.log"
  ;;
list)
  # Copy the running list of found sites (index.html + sites.tsv) to the laptop.
  DEST=${2:-$HOME/tmp/epa/wayback-labs-archive/new-sites}
  mkdir -p "$DEST" && rsync -a "$HOST:/Volumes/4tb-ext/data/newweb/list/" "$DEST/" && echo "$DEST/index.html"
  ;;
spncheck)
  # Does Save Page Now accept the project's keys? Prints which key file and the answer, never the keys.
  ssh "$HOST" 'cd ~/newweb && venv/bin/python -c "
from newweb import spn
import urllib.error
f = spn.load_keys(); print(\"keys from\", f)
try: print(\"Save Page Now:\", spn.call(\"https://web.archive.org/save/status/user\"))
except urllib.error.HTTPError as e: print(\"Save Page Now: HTTP\", e.code, e.read(200))
"'
  ;;
report)
  ssh "$HOST" 'cd ~/newweb && venv/bin/python -m newweb.report'
  ;;
*) echo "usage: $0 deploy|start|stop|status|list|spncheck|report"; exit 1 ;;
esac
