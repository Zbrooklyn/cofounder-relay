# cofounder-relay installer (Windows). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# Installs the /discord slash command + relay skill for the current user, pointed
# at THIS repo location, and registers the resume hook. Does not touch secrets --
# you run `relay init` after. (ASCII-only on purpose: non-ASCII in a .ps1 crashes
# Windows PowerShell 5.1.)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$claude = Join-Path $env:USERPROFILE ".claude"

# 1. /discord slash command (substitute this repo's path into the template)
$cmdDir = Join-Path $claude "commands"
New-Item -ItemType Directory -Force -Path $cmdDir | Out-Null
$tpl = Get-Content (Join-Path $repo "commands\discord.md") -Raw
$tpl = $tpl.Replace("{{RELAY_REPO}}", $repo)
Set-Content -Path (Join-Path $cmdDir "discord.md") -Value $tpl -Encoding UTF8
Write-Host "installed /discord -> $cmdDir\discord.md"

# 2. relay skill (so the live Claude auto-discovers it)
$skillDir = Join-Path $claude "skills\relay"
New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
Copy-Item (Join-Path $repo "skill\SKILL.md") (Join-Path $skillDir "SKILL.md") -Force
Write-Host "installed relay skill -> $skillDir\SKILL.md"

# 3. Python check
try { python --version | Out-Null; Write-Host "python: OK" }
catch { Write-Warning "Python 3.11+ not found on PATH. Install it before running relay." }

# 4. Register the resume hook (auto-reattach a bound relay conversation on /resume,
#    silent for brand-new ones). Done in Python so it won't mangle existing settings.
try { python (Join-Path $repo "scripts\register_hook.py") }
catch { Write-Warning "could not register the resume hook automatically: $_" }

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. python `"$repo\scripts\relay.py`" init       # your identity, bot token, channels"
Write-Host "  2. python `"$repo\scripts\relay.py`" validate   # prove post+read works per channel"
Write-Host "  3. In a live Claude session: /discord send a test"
