#!/bin/sh
# Restart loop. The hosted refresh worker stages a new snapshot and then stops the server on
# purpose (SIGTERM to itself); the next start activates the staged file before anything opens
# the index, carrying watches and application records over. Any other exit is also restarted.
while true; do
  ohp serve --transport streamable-http --host 0.0.0.0 --port "${PORT:-7860}"
  echo "openhire: server exited with status $?; restarting in 2 s" >&2
  sleep 2
done
