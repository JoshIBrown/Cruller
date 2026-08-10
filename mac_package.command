#!/bin/bash
#
# mac_package.command — build a clean Cruller.zip for giving to someone else.
#
# Double-click it. The zip lands on your Desktop. It contains the tool and the
# user docs only: no settings, no compiled app (their installer rebuilds it),
# no internal project ledgers, no machine litter. Their first run asks where
# their working folder should be.
#
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${HOME}/Desktop"
[ -d "$OUT" ] || OUT="$HERE"
STAGE="$(mktemp -d)/Cruller"
mkdir -p "$STAGE/scripts"

# The tool and the docs a user needs — nothing else.
cp "$HERE/crull" "$HERE/mac_install.command" "$HERE/pc_crull.bat" "$HERE/pc_install.bat" "$HERE/START HERE.md" "$STAGE/"
cp "$HERE"/scripts/*.py "$HERE/scripts/README.md" "$STAGE/scripts/"
mkdir -p "$STAGE/docs"
cp "$HERE/README.md" "$STAGE/"
cp "$HERE"/docs/*.md "$STAGE/docs/"

chmod +x "$STAGE/crull" "$STAGE/mac_install.command"

ZIP="$OUT/Cruller.zip"
rm -f "$ZIP"
if command -v ditto >/dev/null; then
    ditto -c -k --keepParent "$STAGE" "$ZIP"        # preserves permissions
else
    (cd "$(dirname "$STAGE")" && zip -qry "$ZIP" "Cruller")
fi
rm -rf "$(dirname "$STAGE")"
echo "built: $ZIP"
echo "send that. Their setup is: unzip, double-click mac_install.command."
