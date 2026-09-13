#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/configure.py
mkdir -p bin
if [ ! -f bin/developer_key.der ]; then
  umask 077
  openssl genrsa -out bin/developer_key.pem 4096 2>/dev/null
  openssl pkcs8 -topk8 -inform PEM -outform DER -in bin/developer_key.pem -out bin/developer_key.der -nocrypt
fi
monkeyc -f monkey.jungle -d venu2 -y bin/developer_key.der -o bin/BioTwin.prg -w
