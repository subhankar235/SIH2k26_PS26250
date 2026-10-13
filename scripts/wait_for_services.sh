#!/usr/bin/env sh
set -eu
host="${1:-localhost}"
port="${2:-8000}"
attempts="${3:-30}"
while [ "$attempts" -gt 0 ]; do
  if python -c "import socket; socket.create_connection(('$host', $port), timeout=1).close()" 2>/dev/null; then
    echo "Service $host:$port is available."
    exit 0
  fi
  attempts=$((attempts - 1))
  sleep 2
exit 1
