#!/bin/bash
# Run on the laptop:  tools/studio.sh deploy | start | stop | status | report
# Code lives in ~/newweb on the studio, the database in /Volumes/4tb-ext/data/newweb.
# Jobs run in screen sessions (nw-*), which do NOT survive a studio reboot: run "start" again after one.
set -u
HOST=${STUDIO:-studioj}
JOBS="hn bluesky gharchive liveness"
case "${1:-}" in
deploy)
  rsync -a --delete --exclude __pycache__ --exclude .git "$(dirname "$0")/../" "$HOST:newweb/"
  ssh "$HOST" 'cd ~/newweb && [ -x venv/bin/python ] || /opt/homebrew/bin/python3.12 -m venv venv && venv/bin/pip -q install websockets && mkdir -p logs /Volumes/4tb-ext/data/newweb'
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
report)
  ssh "$HOST" 'cd ~/newweb && venv/bin/python -m newweb.report'
  ;;
*) echo "usage: $0 deploy|start|stop|status|report"; exit 1 ;;
esac
