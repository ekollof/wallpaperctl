#!/bin/sh
# install.sh — bootstrap wallpaperctl with pipx (POSIX sh; Linux + BSDs).
#
# Usage:
#   ./install.sh [--upgrade] [--from <path|git-url>] [--yes]
#   curl -fsSL <raw-url>/install.sh | sh
#
# This script only bootstraps what wallpaperctl needs to run and self-install
# the rest: Python >= 3.10 and pipx. System/theme dependencies (wallust, AUR
# packages, desktop tools) are installed afterwards by wallpaperctl itself:
#
#   wallpaperctl setup install     # desktop deps via the system package manager
#   wallpaperctl setup omarchy     # Omarchy prerequisites + dynamic theme
#   wallpaperctl setup all         # config + themes + check + install + wallust

set -eu

REPO_URL="https://github.com/ekollof/wallpaperctl.git"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=10

UPGRADE=0
ASSUME_YES=0
FROM=""

msg()  { printf '%s\n' "$*"; }
warn() { printf 'Warning: %s\n' "$*" >&2; }
die()  { printf 'Error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: install.sh [options]

Options:
  --upgrade          Reinstall even if wallpaperctl is already installed
  --from PATH|URL    Install from a local checkout or git URL (default: auto-detect)
  --yes, -y          Non-interactive: assume yes for prompts
  -h, --help         Show this help

wallpaperctl itself installs remaining system dependencies:
  wallpaperctl setup all
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --upgrade) UPGRADE=1 ;;
    --yes|-y)  ASSUME_YES=1 ;;
    --from)    [ $# -ge 2 ] || die "--from requires an argument"; FROM="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)         usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

prompt_yes() {
  # prompt_yes "question" — returns 0 on yes. Non-interactive stdin => no.
  if [ "$ASSUME_YES" -eq 1 ]; then
    return 0
  fi
  if [ ! -t 0 ]; then
    return 1
  fi
  printf '%s [y/N] ' "$1"
  read -r answer || answer=n
  case "$answer" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

# ── Python prerequisite ─────────────────────────────────────────────────

if ! command -v python3 >/dev/null 2>&1; then
  die "python3 not found; install Python >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} first"
fi

# Only ask python to print its version; compare in POSIX shell.
PYVER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null) || PYVER=""
if [ -z "$PYVER" ]; then
  die "python3 is not usable ($(python3 --version 2>&1)); wallpaperctl needs >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}"
fi

PY_MAJOR=${PYVER%%.*}
PY_REST=${PYVER#*.}
PY_MINOR=${PY_REST%%.*}
if [ "$PY_MAJOR" -lt "$PYTHON_MIN_MAJOR" ] ||
  { [ "$PY_MAJOR" -eq "$PYTHON_MIN_MAJOR" ] && [ "$PY_MINOR" -lt "$PYTHON_MIN_MINOR" ]; }; then
  die "python3 $PYVER is too old; wallpaperctl needs >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}"
fi
msg "Python: $PYVER"

# ── pipx prerequisite ───────────────────────────────────────────────────

# Elevation helper for system package installs (sudo on Linux, doas on BSD).
elevate() {
  if command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  elif command -v doas >/dev/null 2>&1; then
    doas "$@"
  else
    "$@"
  fi
}

install_pipx() {
  # Installs pipx via the first supported package manager found.
  # Returns 0 only when pipx is actually usable afterwards.
  if command -v apt-get >/dev/null 2>&1; then
    elevate apt-get install -y pipx
  elif command -v dnf >/dev/null 2>&1; then
    elevate dnf install -y pipx
  elif command -v zypper >/dev/null 2>&1; then
    elevate zypper install -y python3-pipx
  elif command -v pacman >/dev/null 2>&1; then
    # Arch names it python-pipx; wallust itself lives in the AUR (wallust-git).
    elevate pacman -S --needed --noconfirm python-pipx
  elif command -v pkg >/dev/null 2>&1; then
    elevate pkg install -y devel/py-pipx
  elif command -v pkg_add >/dev/null 2>&1; then
    elevate pkg_add pipx
  elif command -v brew >/dev/null 2>&1; then
    brew install pipx
  else
    return 1
  fi
  command -v pipx >/dev/null 2>&1
}

if ! command -v pipx >/dev/null 2>&1; then
  msg "pipx not found."
  if prompt_yes "Install pipx with the system package manager?"; then
    if ! install_pipx; then
      warn "Automatic pipx install failed."
      msg "Install it manually, then re-run this script:"
      msg "  python3 -m pip install --user pipx && python3 -m pipx ensurepath"
      exit 1
    fi
  else
    msg "Install pipx manually, then re-run this script:"
    msg "  python3 -m pip install --user pipx && python3 -m pipx ensurepath"
    exit 1
  fi
fi
msg "pipx: $(command -v pipx)"

# ── install source ──────────────────────────────────────────────────────

# When piped (curl | sh), $0 is the shell name and not a file path.
SRC_DIR=""
if [ -f "$0" ]; then
  SRC_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
fi

if [ -n "$FROM" ]; then
  SRC="$FROM"
elif [ -n "$SRC_DIR" ] && [ -f "$SRC_DIR/pyproject.toml" ]; then
  SRC="$SRC_DIR"
  msg "Installing from local checkout: $SRC"
else
  SRC="$REPO_URL"
  msg "Installing from: $SRC"
fi

PIPX_FORCE=""
if [ "$UPGRADE" -eq 1 ]; then
  PIPX_FORCE="--force"
fi

msg "Running: pipx install $PIPX_FORCE $SRC"
if ! pipx install $PIPX_FORCE "$SRC"; then
  die "pipx install failed. Manual command: pipx install $PIPX_FORCE $SRC"
fi

# ── verification ────────────────────────────────────────────────────────

if ! command -v wallpaperctl >/dev/null 2>&1; then
  msg ""
  msg "wallpaperctl is installed but not on PATH (~/.local/bin missing?)."
  if prompt_yes "Run 'pipx ensurepath' to add it to PATH?"; then
    pipx ensurepath || warn "pipx ensurepath failed"
    msg "Restart your shell (or re-source your profile) for PATH changes."
  else
    msg "Add ~/.local/bin to PATH to use the wallpaperctl/wallpaper commands."
  fi
fi

WALLPAPERCTL_BIN=$(command -v wallpaperctl || echo "$HOME/.local/bin/wallpaperctl")
if ! "$WALLPAPERCTL_BIN" --version >/dev/null 2>&1; then
  die "wallpaperctl --version failed after install; check the output above."
fi
msg "Installed: $("$WALLPAPERCTL_BIN" --version)"

# ── post-install setup (wallpaperctl installs its own deps from here) ───

msg ""
msg "Running 'wallpaperctl setup all' (config, themes, dep check + install, wallust)…"
SETUP_ARGS=""
if [ "$ASSUME_YES" -eq 1 ]; then
  SETUP_ARGS="-y"
fi
if ! "$WALLPAPERCTL_BIN" setup all $SETUP_ARGS; then
  warn "setup all reported problems; re-run later with: wallpaperctl setup all"
fi

msg ""
msg "Next steps:"
msg "  wallpaperctl detect            # show detected desktop + tools"
msg "  wallpaperctl random            # pick and set a wallpaper"
if "$WALLPAPERCTL_BIN" detect 2>/dev/null | grep -q "omarchy=True"; then
  msg "  wallpaperctl setup omarchy     # Omarchy 'Dynamic Wallpapers' theme"
fi
msg ""
msg "API keys for remote fetching live in ~/.config/wallpaper/config.sh"
msg "(UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, PIXABAY_API_KEY) — never in the repo."
