# cofounder-relay installer (Windows). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# Installs the /discord slash command + relay skill for the current user, pointed
# at THIS repo location. Does not touch secrets — you run `relay init` after.

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
catch { Write-Warning "Python 3.11+ not found on PATH — install it before running relay." }

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. python `"$repo\scripts\relay.py`" init       # enter your identity, bot token, channels"
Write-Host "  2. python `"$repo\scripts\relay.py`" validate   # prove post+read works per channel"
Write-Host "  3. In a live Claude session: /discord send a test"
# 4. Register the resume hook so a bound relay conversation auto-reattaches on /resume
#    (silent for brand-new conversations). Idempotent — skips if already present.
$settingsPath = Join-Path $claude "settings.json"
$hookCmd = "python `"$repo\scripts\resume_hook.py`""
if (Test-Path $settingsPath) {
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
} else {
    $settings = [PSCustomObject]@{}
}
if (-not $settings.PSObject.Properties['hooks']) {
    $settings | Add-Member -NotePropertyName hooks -NotePropertyValue ([PSCustomObject]@{})
}
if (-not $settings.hooks.PSObject.Properties['SessionStart']) {
    $settings.hooks | Add-Member -NotePropertyName SessionStart -NotePropertyValue @()
}
$already = $false
foreach ($entry in @($settings.hooks.SessionStart)) {
    foreach ($h in @($entry.hooks)) { if ($h.command -like '*resume_hook.py*') { $already = $true } }
}
if (-not $already) {
    $newEntry = [PSCustomObject]@{
        matcher = 'resume'
        hooks   = @([PSCustomObject]@{ type = 'command'; command = $hookCmd })
    }
    $settings.hooks.SessionStart = @($settings.hooks.SessionStart) + $newEntry
    ($settings | ConvertTo-Json -Depth 12) | Set-Content -Path $settingsPath -Encoding UTF8
    Write-Host "registered resume hook -> the relay auto-reattaches when you /resume a bound conversation"
} else {
    Write-Host "resume hook already registered"
}
