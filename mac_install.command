#!/bin/bash
#
# mac_install.command — everything PhotoCruller needs, in one command.
#
#   ./mac_install.command
#
# 1. Installs the Python libraries (numpy, pillow, opencv, pillow-heif).
# 2. Builds PhotoCruller.app, the Finder drop target.
#
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"

# Transports like Dropbox and email strip the execute bit. This script may
# have been started with `bash mac_install.command`, so heal everything here.
chmod +x "$HERE/mac_install.command" "$HERE/crull" 2>/dev/null || true

echo "1/3  Python libraries"
pip3 install --quiet numpy pillow opencv-python-headless pillow-heif \
  || pip3 install numpy pillow opencv-python-headless pillow-heif


echo "2/3  PhotoCruller.app"
APP="$HERE/PhotoCruller.app"
SRC="$(mktemp -t photocruller).applescript"

cat > "$SRC" <<'SCRIPT'
on run
	ensureWorkingFolder()
	set chosen to choose folder with prompt "Pick a folder of photos to look through:"
	runCull({POSIX path of chosen}, {})
end run

on ensureWorkingFolder()
	-- The very first question, before anything else: where does PhotoCruller's
	-- output live? Asked once, written to scripts/settings.conf, never again.
	set toolDir to "__TOOLDIR__"
	set conf to toolDir & "/scripts/settings.conf"
	set hasIt to (do shell script "grep -qs '^[[:space:]]*working folder' " & quoted form of conf & " && echo yes || echo no")
	if hasIt is "no" then
		set wf to choose folder with prompt "First, choose PhotoCruller's working folder — it will hold culled photos, reviews and records. Never your photo library itself. (You can create a new folder right here.)"
		do shell script "p=" & quoted form of (POSIX path of wf) & " ; printf 'working folder = %s\n' \"${p%/}\" >> " & quoted form of conf
	end if
end ensureWorkingFolder

on open droppedItems
	-- Folders each become their own job; loose files become one job judged as
	-- a set, so a hand-picked selection can be culled without a folder.
	set folderPaths to {}
	set filePaths to {}
	repeat with anItem in droppedItems
		tell application "System Events"
			set isFolder to (class of (disk item (anItem as text)) is folder)
		end tell
		if isFolder then
			set end of folderPaths to POSIX path of anItem
		else
			set end of filePaths to POSIX path of anItem
		end if
	end repeat
	if (count of folderPaths) > 0 or (count of filePaths) > 0 then
		runCull(folderPaths, filePaths)
	end if
end open

on runCull(folderPaths, filePaths)
	set toolDir to "__TOOLDIR__"
	ensureWorkingFolder()

	-- A queue left over from a dead session must not replay old jobs the moment
	-- a new folder is dropped. If no PhotoCruller window is working, any ticket older
	-- than a minute is from that dead session and is discarded; tickets younger
	-- than that are sibling events of this same drop and are kept.
	set anyBusy to false
	tell application "Terminal"
		repeat with w in windows
			repeat with t in tabs of w
				try
					if custom title of t is "PhotoCruller" and busy of t then set anyBusy to true
				end try
			end repeat
		end repeat
	end tell
	if not anyBusy then
		do shell script "find " & quoted form of (toolDir & "/.queue") & ¬
			" \\( -name '*.path' -o -name '*.paths' \\) -mmin +1 -delete 2>/dev/null ; true"
	end if

	-- Every dropped folder becomes its own small file in .queue. Separate files
	-- mean simultaneous drops cannot overwrite each other, and a folder dropped
	-- while a run is going is picked up when that run finishes.
	repeat with p in folderPaths
		set thePath to (p as text)
		do shell script "mkdir -p " & quoted form of (toolDir & "/.queue") & " && printf '%s' " & ¬
			quoted form of thePath & " > " & quoted form of (toolDir & "/.queue/") & "$(date +%s)-$RANDOM.path"
	end repeat

	-- Loose files travel together as one ticket, one path per line: they were
	-- selected as a set and are judged as one.
	if (count of filePaths) > 0 then
		set fileArgs to ""
		repeat with p in filePaths
			set fileArgs to fileArgs & " " & quoted form of (p as text)
		end repeat
		do shell script "mkdir -p " & quoted form of (toolDir & "/.queue") & " && printf '%s\n'" & ¬
			fileArgs & " > " & quoted form of (toolDir & "/.queue/") & "$(date +%s)-$RANDOM.paths"
	end if

	set cmd to "export PHOTOCRULLER_FROM_APP=1 ; cd " & quoted form of toolDir & " && ./crull --queue"

	tell application "Terminal"
		activate
		-- If a PhotoCruller window is already draining the queue, leave it alone: it
		-- will reach the folders just added. Otherwise use an idle PhotoCruller window,
		-- or open one.
		set busyPhotoCruller to false
		set idleTab to missing value
		set idleWindow to missing value
		repeat with w in windows
			repeat with t in tabs of w
				try
					if custom title of t is "PhotoCruller" then
						if busy of t then
							set busyPhotoCruller to true
						else
							set idleTab to t
							set idleWindow to w
						end if
					end if
				end try
			end repeat
		end repeat

		if busyPhotoCruller then
			return -- the running window will get to them
		else if idleTab is not missing value then
			do script cmd in idleTab
			try
				set index of idleWindow to 1
			end try
		else
			set newTab to do script cmd
			try
				set custom title of newTab to "PhotoCruller"
			end try
		end if
	end tell
end runCull
SCRIPT

python3 - "$SRC" "$HERE" <<'PY'
import sys, pathlib
src, tooldir = pathlib.Path(sys.argv[1]), sys.argv[2]
src.write_text(src.read_text().replace("__TOOLDIR__", tooldir))
PY

rm -rf "$APP"
osacompile -o "$APP" "$SRC"
rm -f "$SRC"
echo "     built: $APP"

echo "3/3  checking the libraries"
"$PY" - <<'PY'
import sys
need = [("numpy", "all image maths"), ("PIL", "reading and writing pictures"),
        ("cv2", "aligning two frames — the core of every decision")]
missing = []
for mod, why in need:
    try:
        __import__(mod)
        print(f"     {mod:<8} ok")
    except ImportError:
        missing.append((mod, why))
        print(f"     {mod:<8} MISSING — {why}")
try:
    __import__("pillow_heif")
    print("     heic     ok")
except ImportError:
    print("     heic     not installed — iPhone HEIC files will be skipped")
sys.exit(1 if missing else 0)
PY
