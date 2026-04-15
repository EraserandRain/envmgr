#!/usr/bin/env bash
set -euo pipefail

install -d -m 0755 /var/run/sshd
install -d -m 0700 -o envmgr -g envmgr /home/envmgr/.ssh

if [[ -n "${AUTHORIZED_KEYS:-}" ]]; then
  printf '%s\n' "$AUTHORIZED_KEYS" > /home/envmgr/.ssh/authorized_keys
  chown envmgr:envmgr /home/envmgr/.ssh/authorized_keys
  chmod 0600 /home/envmgr/.ssh/authorized_keys
fi

exec /usr/sbin/sshd -D -e
