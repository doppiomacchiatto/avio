#!/usr/bin/env bash
# Avio: clean the build outputs, then build the installers.
# Works on macOS, Linux and Git Bash on Windows. On Windows you can also use clean-build.bat.
#
# Usage: ./clean-build.sh [--full] [--deps] [--no-build]
#   --full      also run "cargo clean" (the whole Rust target folder; the next build takes much longer)
#   --deps      also reinstall dependencies (npm ci, and pip install into backend/.venv)
#   --no-build  clean only, do not build
set -euo pipefail

cd "$(dirname "$0")"

FULL=0; DEPS=0; BUILD=1
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    --deps) DEPS=1 ;;
    --no-build) BUILD=0 ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) WIN=1 ;;
  *) WIN=0 ;;
esac

if [ "$WIN" = 1 ]; then
  VENV_PY="backend/.venv/Scripts/python.exe"
else
  VENV_PY="backend/.venv/bin/python"
fi

step() { printf '\n== %s\n' "$1"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1 is not on PATH." >&2; exit 1; }; }

need node
need npm
need cargo

# A running Avio holds its files open, and the build would fail halfway.
step "Checking that Avio is not running"
if [ "$WIN" = 1 ]; then
  for exe in avio.exe sf_backend.exe; do
    if tasklist.exe //FI "IMAGENAME eq $exe" 2>/dev/null | grep -qi "$exe"; then
      echo "$exe is running. Close Avio first." >&2; exit 1
    fi
  done
else
  for p in avio sf_backend; do
    if pgrep -xi "$p" >/dev/null 2>&1; then
      echo "$p is running. Close Avio first." >&2; exit 1
    fi
  done
fi
echo "OK"

step "Cleaning build outputs"
for d in frontend/dist backend/dist backend/build backend/__pycache__ dist src-tauri/target/release/bundle; do
  if [ -e "$d" ]; then
    rm -rf "$d"
    echo "removed $d"
  fi
done

if [ "$FULL" = 1 ]; then
  step "cargo clean (full Rust clean)"
  (cd src-tauri && cargo clean)
fi

if [ "$DEPS" = 1 ]; then
  step "Reinstalling Node dependencies"
  npm ci
  (cd frontend && npm ci)

  step "Reinstalling Python dependencies"
  if [ ! -x "$VENV_PY" ]; then
    PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
    "$PY" -m venv backend/.venv
  fi
  "$VENV_PY" -m pip install --upgrade pip
  "$VENV_PY" -m pip install -r backend/requirements.txt
fi

if [ "$BUILD" = 0 ]; then
  step "Clean done (--no-build)"
  exit 0
fi

[ -d node_modules ] && [ -d frontend/node_modules ] || { echo "node_modules missing: run again with --deps" >&2; exit 1; }
[ -x "$VENV_PY" ] || { echo "Python venv missing ($VENV_PY): run again with --deps" >&2; exit 1; }

# Keep the build machine's home path out of the binaries.
if [ "$WIN" = 1 ] && [ -n "${USERPROFILE:-}" ]; then
  export RUSTFLAGS="--remap-path-prefix=$USERPROFILE=~"
else
  export RUSTFLAGS="--remap-path-prefix=$HOME=~"
fi

step "Building (backend, frontend, Tauri bundle)"
START=$(date +%s)
npm run tauri:build
END=$(date +%s)

step "Installers ($(( (END - START) / 60 )) min $(( (END - START) % 60 )) s)"
if command -v sha256sum >/dev/null 2>&1; then HASH="sha256sum"; else HASH="shasum -a 256"; fi
found=0
for f in src-tauri/target/release/bundle/*/*; do
  case "$f" in
    *.exe|*.msi|*.dmg|*.AppImage|*.deb|*.rpm)
      $HASH "$f" | awk '{ print toupper($1) "  " }' | tr -d '\n'
      echo "$f"
      found=1 ;;
  esac
done
[ "$found" = 1 ] || echo "No installers found under src-tauri/target/release/bundle" >&2
