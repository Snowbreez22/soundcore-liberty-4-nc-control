#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
  /usr/bin/xcode-select --install
  printf '\nWhen Command Line Tools finish installing, run this launcher again.\n'
  exit 1
fi
build_dir="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/soundcore-control.XXXXXXXX")"
trap '/bin/rm -r -- "$build_dir"' EXIT
/usr/bin/clang -fobjc-arc -framework Foundation -framework IOBluetooth \
  -Wl,-sectcreate,__TEXT,__info_plist,Bluetooth.plist Bluetooth.m -o "$build_dir/earbud-link"
/usr/bin/python3 control.py --helper "$build_dir/earbud-link"
