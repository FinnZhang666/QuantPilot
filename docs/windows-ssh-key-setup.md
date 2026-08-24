# Windows SSH Key Setup

This guide connects the QuantPilot Mac development console to the Windows runtime host over Tailscale and OpenSSH.
It does not configure OpenD, Broker execution, databases, or trading.

## 1. Prepare Windows

Run `scripts/setup-windows-remote.ps1` from an elevated Windows PowerShell. Sign in to Tailscale using the same
tailnet as the Mac. Record the reported Windows username, hostname, and Tailscale IPv4 address.

## 2. Copy only the Mac public key

On the Mac, display the public key:

```bash
cat ~/.ssh/id_ed25519.pub
```

Copy the single `ssh-ed25519 ...` line. Never copy or disclose `~/.ssh/id_ed25519`.

## 3A. Standard Windows user

In a PowerShell window running as the target user:

```powershell
New-Item -ItemType Directory -Force "$HOME\.ssh" | Out-Null
notepad "$HOME\.ssh\authorized_keys"
```

Paste the public key as one line, save it, and apply permissions:

```powershell
$account = "${env:USERDOMAIN}\${env:USERNAME}"
icacls "$HOME\.ssh" /inheritance:r /grant:r "${account}:(OI)(CI)F" /grant:r "SYSTEM:(OI)(CI)F"
icacls "$HOME\.ssh\authorized_keys" /inheritance:r /grant:r "${account}:F" /grant:r "SYSTEM:F"
```

## 3B. Target user belongs to Administrators

The default Windows OpenSSH configuration commonly uses `%ProgramData%\ssh\administrators_authorized_keys` for
administrator accounts. In an elevated PowerShell:

```powershell
notepad "$env:ProgramData\ssh\administrators_authorized_keys"
icacls "$env:ProgramData\ssh\administrators_authorized_keys" /inheritance:r /grant:r "*S-1-5-32-544:F" /grant:r "SYSTEM:F"
Restart-Service sshd
```

Paste the public key as one line. Confirm the effective `Match Group administrators` section in
`%ProgramData%\ssh\sshd_config`; do not weaken authentication or enable password login unnecessarily.

## 4. Configure the Mac alias

Replace the placeholders in the `quant-win` block of `~/.ssh/config`:

```sshconfig
Host quant-win
    HostName <TAILSCALE_WINDOWS_HOSTNAME_OR_IP>
    User <WINDOWS_USERNAME>
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

Set file permissions with `chmod 600 ~/.ssh/config`. Prefer a Tailscale MagicDNS hostname when enabled; otherwise
use the stable Tailscale IPv4 address. Do not expose TCP 22 on the public internet or configure router forwarding.

## 5. Verify read-only connectivity

```bash
scripts/test-quant-win.sh
```

The script checks Tailscale, resolves the SSH alias, and remotely runs only `hostname`, `whoami`, and a read-only
`Get-Service sshd` query. Review the host key fingerprint on the first manual connection against the Windows host.
