#!/usr/bin/env bash
#
# codex_image.sh — Drive Codex's built-in image_gen tool to generate or edit one image.
#
# Why this exists: every image request otherwise re-derives the same Codex
# mechanics (the exec flags, where the PNG lands, how to find it). Encapsulating
# them here lets the caller think only about the picture, not the plumbing.
#
# Usage:
#   codex_image.sh generate --prompt "<image description>" [--out <dest.png>] [--cd <dir>]
#   codex_image.sh edit --src <abs source.png> --prompt "<edit instruction>" [--out <dest.png>] [--cd <dir>]
#
# On success prints exactly one line:  IMAGE_PATH=<absolute path to the PNG>
# Codex's own final message (a human-readable summary) is printed above it.

set -euo pipefail

mode="${1:-}"; shift || true
[ "$mode" = "generate" ] || [ "$mode" = "edit" ] || {
  echo "ERROR: first argument must be 'generate' or 'edit'" >&2; exit 2; }

prompt="" src="" out="" cd_dir=""
while [ $# -gt 0 ]; do
  case "$1" in
    --prompt) prompt="$2"; shift 2 ;;
    --src)    src="$2";    shift 2 ;;
    --out)    out="$2";    shift 2 ;;
    --cd)     cd_dir="$2"; shift 2 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -n "$prompt" ] || { echo "ERROR: --prompt is required" >&2; exit 2; }
command -v codex >/dev/null 2>&1 || { echo "ERROR: codex CLI not found on PATH" >&2; exit 3; }

IMG_DIR="${CODEX_HOME:-$HOME/.codex}/generated_images"
mkdir -p "$IMG_DIR"

# A marker whose mtime is "now"; any image newer than it was made by this run.
marker="$(mktemp)"
last_msg="$(mktemp)"
cleanup() { rm -f "$marker" "$last_msg"; }
trap cleanup EXIT

# Boilerplate that turns a creative prompt into a reliable, parseable Codex task.
# The caller never has to remember to say "use image_gen" or "print the path".
read -r -d '' tail <<'EOF' || true
The image_gen tool saves the PNG automatically; do not copy or save it anywhere else.
On the very last line of your reply, print exactly:
IMAGE_PATH=<absolute filesystem path where image_gen saved the PNG>
EOF

cmd=(codex exec --skip-git-repo-check -o "$last_msg")
[ -n "$cd_dir" ] && cmd+=(-C "$cd_dir")

if [ "$mode" = "edit" ]; then
  [ -n "$src" ] || { echo "ERROR: edit mode requires --src" >&2; exit 2; }
  [ -f "$src" ] || { echo "ERROR: source image not found: $src" >&2; exit 2; }
  # Attaching the source with -i makes it visible in Codex's context, which is
  # what the built-in image_gen edit mode needs. We also state the invariant
  # (keep everything not mentioned) so edits don't silently redraw the whole image.
  cmd+=(-i "$src")
  full_prompt="The attached image is the edit target. Use the built-in image_gen tool to edit it.
${prompt}
Change only what is described above; keep everything else unchanged. (The source file is never touched: image_gen always writes a new file.)
${tail}"
else
  full_prompt="Use the built-in image_gen tool to generate one image.
${prompt}
${tail}"
fi

# Run Codex. It typically takes 20-60s. Stderr is forwarded so failures surface.
# The prompt goes via stdin, not as a positional argument, so it can never collide
# with the variadic -i/--image flag (which would otherwise swallow it as an image path).
printf '%s' "$full_prompt" | "${cmd[@]}" >&2

# Canonical retrieval: the newest ig_*.png created during this run. This is more
# robust than parsing stdout, because the path format is stable even if the model
# phrases its summary differently.
newest="$(find "$IMG_DIR" -type f -name 'ig_*.png' -newer "$marker" -print 2>/dev/null \
  | xargs -I{} stat -f '%m %N' {} 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"

if [ -z "$newest" ]; then
  echo "----- Codex final message -----" >&2
  cat "$last_msg" >&2 || true
  echo "ERROR: no new image was produced. See Codex's message above (it may have refused or hit an error)." >&2
  exit 4
fi

# Surface Codex's human-readable summary, then the canonical path line.
echo "----- Codex final message -----"
cat "$last_msg" 2>/dev/null || true
echo "-------------------------------"

final="$newest"
if [ -n "$out" ]; then
  mkdir -p "$(dirname "$out")"
  cp "$newest" "$out"
  final="$out"
fi

echo "IMAGE_PATH=${final}"
