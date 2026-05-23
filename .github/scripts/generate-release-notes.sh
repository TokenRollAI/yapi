#!/usr/bin/env bash
# Generate Markdown release notes from git log between previous tag and current tag,
# grouping commits by Conventional Commits type.
#
# Usage:
#   GITHUB_REF_NAME=v0.3.0 GITHUB_REPOSITORY=owner/repo bash generate-release-notes.sh > notes.md
#   bash generate-release-notes.sh v0.3.0 > notes.md         # local run, repo inferred
set -euo pipefail

tag="${GITHUB_REF_NAME:-${1:-}}"
repo="${GITHUB_REPOSITORY:-TokenRollAI/yapi}"
version="${tag#v}"

if [ -z "$tag" ]; then
  echo "usage: $0 <tag>" >&2
  exit 1
fi

prev=$(git tag --list "v*" --sort=-v:refname \
  | awk -v cur="$tag" '$0==cur {found=1; next} found {print; exit}')

if [ -n "$prev" ]; then
  range="${prev}..${tag}"
  changelog_link="https://github.com/${repo}/compare/${prev}...${tag}"
else
  range="$tag"
  changelog_link="https://github.com/${repo}/commits/${tag}"
fi

commits=$(git log "$range" --pretty=format:'%H|%s' --no-merges --reverse)

feat=""; fix=""; perf=""; refactor=""; docs=""; tests=""
build=""; ci=""; chore=""; style=""; other=""

while IFS='|' read -r hash subject; do
  [ -z "$hash" ] && continue
  short="${hash:0:7}"
  line="- ${subject} ([\`${short}\`](https://github.com/${repo}/commit/${hash}))"
  type=$(printf '%s' "$subject" | sed -nE 's/^([a-zA-Z]+)(\([^)]*\))?!?:.*/\1/p' | tr '[:upper:]' '[:lower:]')
  case "$type" in
    feat) feat+="${line}"$'\n' ;;
    fix) fix+="${line}"$'\n' ;;
    perf) perf+="${line}"$'\n' ;;
    refactor) refactor+="${line}"$'\n' ;;
    docs) docs+="${line}"$'\n' ;;
    test) tests+="${line}"$'\n' ;;
    build) build+="${line}"$'\n' ;;
    ci) ci+="${line}"$'\n' ;;
    chore) chore+="${line}"$'\n' ;;
    style) style+="${line}"$'\n' ;;
    *) other+="${line}"$'\n' ;;
  esac
done <<< "$commits"

emit_section() {
  local label="$1" body="$2"
  if [ -n "$body" ]; then
    printf '### %s\n\n%s\n' "$label" "$body"
  fi
}

{
  printf '## Install\n\n```bash\npip install pyyapi==%s\n```\n\n' "$version"
  printf "## What's Changed\n\n"
  emit_section "Features"      "$feat"
  emit_section "Bug Fixes"     "$fix"
  emit_section "Performance"   "$perf"
  emit_section "Refactor"      "$refactor"
  emit_section "Documentation" "$docs"
  emit_section "Tests"         "$tests"
  emit_section "Build"         "$build"
  emit_section "CI"            "$ci"
  emit_section "Chores"        "$chore"
  emit_section "Style"         "$style"
  emit_section "Other"         "$other"
  printf '**Full Changelog**: %s\n' "$changelog_link"
}
