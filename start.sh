#!/usr/bin/env bash
# Sofia — start script for macOS and Linux.
# Usage: open Terminal, type "bash " (with a space), drag this file into the window, press Enter.
# Redo the setup questions: bash start.sh --setup
set -u
cd "$(dirname "$0")" || exit 1

echo
echo " ==================== Sofia ===================="
echo

fail() {
    echo
    echo " Er ging iets mis. Controleer of je internet werkt en probeer het opnieuw (handleiding, Deel F)."
    echo " Lukt het weer niet? Maak een screenshot van dit venster en vraag om hulp."
    exit 1
}

PY_OK='import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)'

# 1. Find Python 3.14, 3.13 or 3.12 (3.15 is still too new for some building blocks)
PY=""
for candidate in python3.14 python3.13 python3.12 python3; do
    path="$(command -v "$candidate" 2>/dev/null)" || continue
    # On a Mac without developer tools, /usr/bin/python3 only pops up an Apple install dialog.
    if [ "$path" = "/usr/bin/python3" ] && [ "$(uname)" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then
        continue
    fi
    if "$path" -c "$PY_OK" >/dev/null 2>&1; then
        PY="$path"
        break
    fi
done
if [ -z "$PY" ]; then
    echo " Python 3.14 is niet gevonden op deze computer."
    echo " Let op: Python 3.15 of nieuwer werkt nog NIET met Sofia."
    echo " Installeer Python 3.14 zoals in de handleiding (Deel D) en start Sofia daarna opnieuw."
    if [ "$(uname)" = "Darwin" ]; then
        open "https://www.python.org/ftp/python/3.14.7/python-3.14.7-macos11.pkg" 2>/dev/null || true
    fi
    exit 1
fi

# 2. Own Python environment (rebuilt when it was made with an unsuitable or removed Python)
if [ -e .venv ] && ! .venv/bin/python -c "import pip; $PY_OK" >/dev/null 2>&1; then
    rm -rf .venv
fi
if [ ! -x .venv/bin/python ]; then
    echo " Eerste keer: ik maak een eigen Python-omgeving. Even geduld..."
    "$PY" -m venv .venv || fail
fi

# 3. Install or update the building blocks
echo " Onderdelen installeren. De eerste keer kan dit 5 minuten duren."
echo " Je ziet dan niets gebeuren. Dat is normaal."
.venv/bin/python -m pip install --disable-pip-version-check --quiet -r requirements.txt || fail

# 4. First-time questions (or forced with: bash start.sh --setup)
if [ "${1:-}" = "--setup" ] || [ ! -f .env ]; then
    if ! .venv/bin/python -m app --setup || [ ! -f .env ]; then
        echo
        echo " Het instellen is gestopt. Lees hierboven de regel die begint met STOP."
        echo " Doe wat daar staat. Start Sofia daarna opnieuw (handleiding, Deel F)."
        exit 1
    fi
fi

# 5. Double-click launchers next to this script (macOS), so Terminal isn't needed next time.
#    Created locally, so macOS doesn't treat them as downloaded files.
if [ "$(uname)" = "Darwin" ]; then
    if [ ! -f "Sofia starten.command" ]; then
        printf '#!/bin/bash\ncd "$(dirname "$0")" && bash start.sh\n' > "Sofia starten.command" \
            && chmod +x "Sofia starten.command"
    fi
    if [ ! -f "Sofia opnieuw instellen.command" ]; then
        printf '#!/bin/bash\ncd "$(dirname "$0")" && bash start.sh --setup\n' > "Sofia opnieuw instellen.command" \
            && chmod +x "Sofia opnieuw instellen.command"
    fi
fi

# 6. Start Sofia
echo
echo " Sofia start nu. LAAT DIT VENSTER OPEN STAAN."
echo " Venster dicht = Sofia offline. Stoppen: druk op control+C (niet Cmd)."
echo
.venv/bin/python -m app
echo
echo " Sofia is gestopt."
