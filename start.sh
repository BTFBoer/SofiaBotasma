#!/usr/bin/env bash
# Sofia — start script for macOS and Linux.
# Usage: open Terminal, type "bash " (with a space), drag this file into the window, press Enter.
set -u
cd "$(dirname "$0")" || exit 1

echo
echo " ==================== Sofia ===================="
echo

fail() {
    echo
    echo " Er ging iets mis. Maak een screenshot van dit venster en vraag om hulp."
    exit 1
}

# 1. Find Python 3.12 or newer
PY=""
for candidate in python3.14 python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
        && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    echo " Python 3.12 of nieuwer is niet gevonden op deze computer."
    echo " Installeer Python via https://www.python.org/downloads/ en start dit script opnieuw."
    (command -v open >/dev/null 2>&1 && open "https://www.python.org/downloads/") || true
    exit 1
fi

# 2. Own Python environment, first time only
if [ ! -x .venv/bin/python ]; then
    echo " Eerste keer: ik maak een eigen Python-omgeving. Even geduld..."
    "$PY" -m venv .venv || fail
fi

# 3. Install or update the building blocks
echo " Onderdelen installeren of bijwerken. Dit kan een paar minuten duren..."
.venv/bin/python -m pip install --disable-pip-version-check --quiet -r requirements.txt || fail

# 4. First-time questions (or forced with: bash start.sh --setup)
if [ "${1:-}" = "--setup" ] || [ ! -f .env ]; then
    .venv/bin/python -m app --setup || fail
    [ -f .env ] || fail
fi

# 5. Start Sofia
echo
echo " Sofia start nu. LAAT DIT VENSTER OPEN STAAN."
echo " Venster dicht = Sofia offline. Opnieuw starten = dit script weer uitvoeren."
echo
.venv/bin/python -m app
echo
echo " Sofia is gestopt."
