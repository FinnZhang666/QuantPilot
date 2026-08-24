#!/usr/bin/env bash
set -u

TARGET="${1:-quant-win}"
FAILURES=0

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1" >&2; FAILURES=$((FAILURES + 1)); }

TAILSCALE_CLI="$(command -v tailscale 2>/dev/null || true)"
if [ -z "$TAILSCALE_CLI" ] && [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]; then
  TAILSCALE_CLI=/Applications/Tailscale.app/Contents/MacOS/Tailscale
fi

if [ -n "$TAILSCALE_CLI" ]; then
  if "$TAILSCALE_CLI" status >/dev/null 2>&1; then
    pass "Tailscale is running and authenticated"
  else
    fail "Tailscale CLI exists but is not connected. Open Tailscale and sign in."
  fi
else
  fail "Tailscale CLI was not found. Install/login to Tailscale first."
fi

if ssh -G "$TARGET" >/dev/null 2>&1; then
  pass "SSH alias $TARGET can be parsed"
else
  fail "SSH alias $TARGET is missing or invalid in ~/.ssh/config"
fi

SSH_OPTIONS=(-o BatchMode=yes -o ConnectTimeout=8)
if HOSTNAME_OUTPUT=$(ssh "${SSH_OPTIONS[@]}" "$TARGET" hostname 2>&1); then
  pass "Remote hostname: $HOSTNAME_OUTPUT"
else
  fail "Cannot connect to $TARGET: $HOSTNAME_OUTPUT"
fi

if WHOAMI_OUTPUT=$(ssh "${SSH_OPTIONS[@]}" "$TARGET" whoami 2>&1); then
  pass "Remote user: $WHOAMI_OUTPUT"
else
  fail "Cannot run whoami on $TARGET: $WHOAMI_OUTPUT"
fi

if SSHD_OUTPUT=$(ssh "${SSH_OPTIONS[@]}" "$TARGET" 'powershell -NoProfile -Command "Get-Service sshd | Select-Object Name,Status,StartType | Format-List"' 2>&1); then
  pass "Remote sshd service"
  printf '%s\n' "$SSHD_OUTPUT"
else
  fail "Cannot inspect remote sshd: $SSHD_OUTPUT"
fi

if [ "$FAILURES" -gt 0 ]; then
  printf '\n%d check(s) failed. No remote changes were made.\n' "$FAILURES" >&2
  exit 1
fi

printf '\nAll read-only Mac to Windows SSH checks passed.\n'
