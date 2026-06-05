#!/bin/sh
set -eu

REPO_URL="${UPDATE_REPO_URL:-https://github.com/CyrilPeng/xhh-onebot.git}"
REF="${UPDATE_REF:-main}"
APP_DIR="${APP_DIR:-/app}"
TMP_DIR="$(mktemp -d)"
REPO_DIR="$TMP_DIR/repo"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "[hot-update] starting xhh-onebot update"
echo "[hot-update] repo: $REPO_URL"
echo "[hot-update] ref: $REF"

git clone --depth 1 --branch "$REF" "$REPO_URL" "$REPO_DIR"
COMMIT="$(git -C "$REPO_DIR" rev-parse --short HEAD)"

echo "[hot-update] installing Python dependencies"
python -m pip install -r "$REPO_DIR/requirements.txt"

echo "[hot-update] replacing application files"
rm -rf "$APP_DIR/xhh_onebot"
cp -a "$REPO_DIR/xhh_onebot" "$APP_DIR/xhh_onebot"
cp "$REPO_DIR/pyproject.toml" "$APP_DIR/pyproject.toml"
cp "$REPO_DIR/requirements.txt" "$APP_DIR/requirements.txt"
cp "$REPO_DIR/README.md" "$APP_DIR/README.md"

if [ -d "$REPO_DIR/scripts" ]; then
    mkdir -p "$APP_DIR/scripts"
    cp -a "$REPO_DIR/scripts/." "$APP_DIR/scripts/"
    chmod +x "$APP_DIR/scripts/docker-hot-update.sh" 2>/dev/null || true
fi

echo "[hot-update] refreshing package metadata"
python -m pip install --no-deps "$APP_DIR"

echo "[hot-update] done: $COMMIT"
echo "[hot-update] restart with: docker compose restart xhh-onebot"
