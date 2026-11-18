#!/usr/bin/env bash
# Install what the PCB sync check needs from KiCad 10 (pcbnew and its Python module, and the
# stock footprints) on a GitHub Ubuntu runner, keeping apt's package lists and downloaded .debs
# in a directory the workflow caches between runs (default ~/apt-cache).
#
# Launchpad (the KiCad PPA and its API) and the Ubuntu mirrors are each slow or down at times, so:
# - The PPA's signing key is committed (ci/kicad-ppa.asc) and the source written here, instead of
#   `add-apt-repository`, which asks Launchpad's API for the key on every run.
# - With a cache from the last 7 days, the install runs from it with no network at all
#   (`--no-download`). If packages are missing (a run that timed out partway), it downloads just
#   those against the cached lists, and runs a fresh `apt-get update` only if that fails.
#   An older cache is refreshed first (picking up KiCad point releases), and used as-is if the
#   refresh fails.
# - The workflow saves the cache even when this step fails or times out, so every .deb that
#   finished downloading carries over and a slow day's runs make progress instead of restarting.
#
# Writes changed=true|false to $GITHUB_OUTPUT: whether the cache contents changed. A failed or
# timed-out run writes nothing, which the workflow also treats as changed.
set -euo pipefail

CACHE=${1:-$HOME/apt-cache}
PKGS=(kicad kicad-footprints)
HERE=$(cd "$(dirname "$0")" && pwd)

sudo install -D -m 644 "$HERE/kicad-ppa.asc" /etc/apt/keyrings/kicad-ppa.asc
sudo tee /etc/apt/sources.list.d/kicad-10.0-releases.sources > /dev/null <<'EOF'
Types: deb
URIs: https://ppa.launchpadcontent.net/kicad/kicad-10.0-releases/ubuntu/
Suites: noble
Components: main
Signed-By: /etc/apt/keyrings/kicad-ppa.asc
EOF

mkdir -p "$CACHE/archives/partial" "$CACHE/lists/partial"
APT=(-o "Dir::Cache::archives=$CACHE/archives" -o "Dir::State::Lists=$CACHE/lists"
     -o Acquire::Retries=5 -o Acquire::Languages=none)
# apt dates downloaded lists by the server's Last-Modified, so the lists' age comes from a stamp
# written after each successful `apt-get update`.
STAMP=$CACHE/updated
manifest() { (cd "$CACHE" && find . -type f ! -name lock -printf '%p %s %T@\n' | sort); }
before=$(manifest)

offline() {
    echo "Installing from the cache (no downloads)"
    sudo apt-get install -y --no-install-recommends --no-download "${APT[@]}" "${PKGS[@]}"
}
missing() {
    echo "Downloading only the packages the cache is missing"
    sudo apt-get install -y --no-install-recommends "${APT[@]}" "${PKGS[@]}"
}
online() {
    echo "Refreshing the package lists"
    sudo apt-get update --error-on=any "${APT[@]}" && touch "$STAMP" &&
        sudo apt-get install -y --no-install-recommends "${APT[@]}" "${PKGS[@]}"
}

if [ -n "$(find "$STAMP" -mtime -7 -print 2> /dev/null)" ]; then
    offline || missing || online
elif [ -e "$STAMP" ]; then
    online || offline
else
    online
fi

sudo apt-get autoclean "${APT[@]}"
if [ "$(manifest)" = "$before" ]; then changed=false; else changed=true; fi
echo "Cache changed: $changed"
echo "changed=$changed" >> "${GITHUB_OUTPUT:-/dev/null}"
