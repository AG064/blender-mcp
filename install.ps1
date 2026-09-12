# Install the Aurum Blender MCP.
#
#     pwsh -File install.ps1                       # add-on + configs for every client found
#     pwsh -File install.ps1 -Codex                # only write Codex's config
#     pwsh -File install.ps1 -Blender "A:\...\blender.exe"
#
# It copies the add-on into Blender, enables it, and writes the MCP client
# configuration for whichever agents are installed. Nothing is installed that
# the machine did not already have: no Python packages, no runtime, no build.

[CmdletBinding()]
param(
    [string]$Blender,
    # Where .mcp.json is written and where relative exports land. Defaults to
    # this folder; point it at a game project to have its agent find the server.
    [string]$Project = $PSScriptRoot,
    [int]$Port = 9081,
    [string]$Token = '',
    [switch]$SkipClients,
    [switch]$Uninstall,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot

function Write-Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    $text" -ForegroundColor DarkGray }

# ── find Blender ─────────────────────────────────────────────────────────────

function Find-Blender {
    param([string]$Explicit)
    if ($Explicit) {
        if (-not (Test-Path $Explicit)) { throw "no Blender at $Explicit" }
        return (Resolve-Path $Explicit).Path
    }
    $onPath = Get-Command blender -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    $roots = @(
        "$env:ProgramFiles\Blender Foundation",
        "A:\SteamLibrary\steamapps\common\Blender",
        "A:\programms",
        "C:\Program Files\Blender Foundation"
    )
    $found = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $found += Get-ChildItem $root -Recurse -Filter 'blender.exe' -ErrorAction SilentlyContinue -Depth 3
    }
    if ($found.Count -eq 0) { throw "no Blender found. Pass -Blender <path>." }

    # Newest wins: an add-on written for 3.6 works in 5.x, and the reverse is
    # not guaranteed, so picking the oldest Blender on the machine is the wrong
    # default when there is a choice.
    $best = $found | ForEach-Object {
        $version = (& $_.FullName --version 2>&1 | Select-Object -First 1) -replace '^Blender\s+', '' -replace '\s.*$', ''
        [pscustomobject]@{ Path = $_.FullName; Version = $version }
    } | Sort-Object { [version]($_.Version -replace '[^0-9.]', '') } -Descending | Select-Object -First 1
    return $best.Path
}

$blender = Find-Blender -Explicit $Blender
$version = (& $blender --version 2>&1 | Select-Object -First 1)
Write-Step "Blender: $blender"
Write-Ok $version

$blenderVersion = (& $blender --version 2>&1 | Select-Object -First 1) -replace '^Blender\s+', '' -replace '\s.*$', ''
$short = ($blenderVersion -split '\.')[0..1] -join '.'

# ── add-on directory ─────────────────────────────────────────────────────────

$configHome = if ($env:BLENDER_USER_CONFIG) { $env:BLENDER_USER_CONFIG } else {
    Join-Path $env:APPDATA 'Blender Foundation\Blender'
}
$addonRoot = Join-Path $configHome "$short\scripts\addons"
$target = Join-Path $addonRoot 'aurum_blender_mcp'

if ($Uninstall) {
    Write-Step "Removing the add-on"
    if (Test-Path $target) {
        if ($WhatIf) { Write-Ok "would remove $target" } else { Remove-Item $target -Recurse -Force; Write-Ok "removed $target" }
    } else {
        Write-Ok "not installed"
    }
    return
}

Write-Step "Installing the add-on"
Write-Ok "$target"
if (-not $WhatIf) {
    New-Item -ItemType Directory -Force -Path $addonRoot | Out-Null
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Copy-Item (Join-Path $here 'addon\aurum_blender_mcp') $target -Recurse
    # Blender caches compiled bytecode next to the source; a stale .pyc from an
    # older copy is the classic reason a change appears not to have taken.
    Get-ChildItem $target -Recurse -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

# ── enable it ────────────────────────────────────────────────────────────────

Write-Step "Enabling it in Blender"
$enable = @"
import addon_utils, bpy
addon_utils.enable('aurum_blender_mcp', default_set=True, persistent=True)
bpy.ops.wm.save_userpref()
print('AURUM_ADDON_ENABLED')
"@
if ($WhatIf) {
    Write-Ok "would enable aurum_blender_mcp and save preferences"
} else {
    $output = & $blender --background --python-expr $enable 2>&1
    if ($output -match 'AURUM_ADDON_ENABLED') {
        Write-Ok "enabled, and set to load with Blender"
    } else {
        Write-Warning "Blender did not confirm the add-on was enabled:"
        $output | Select-Object -Last 12 | ForEach-Object { Write-Host "      $_" }
    }
}

# ── MCP client configuration ─────────────────────────────────────────────────

$serverScript = Join-Path $here 'server\aurum_blender_mcp.py'
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    # Blender carries a Python, but it is not on PATH and running the server
    # under it means starting Blender to serve a socket. Any Python 3 will do.
    $python = 'python'
}

$serverArgs = @($serverScript, '--port', $Port, '--root', $Project, '--blender', $blender)
if ($Token) { $serverArgs += @('--token', $Token) }

function Write-JsonFile {
    param([string]$Path, [hashtable]$Object)
    if ($WhatIf) { Write-Ok "would write $Path"; return }
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    ($Object | ConvertTo-Json -Depth 12) | Set-Content $Path -Encoding utf8
    Write-Ok $Path
}

if (-not $SkipClients) {
    Write-Step "Registering the server with the agents on this machine"

    $entry = @{
        command = $python
        args    = $serverArgs
    }

    # Codex reads ~/.codex/config.toml. Written as TOML text because the file
    # holds other people's settings and a JSON round-trip would rewrite them.
    $codexConfig = Join-Path $env:USERPROFILE '.codex\config.toml'
    $codexDir = Split-Path -Parent $codexConfig
    if (Test-Path $codexDir) {
        $argsToml = ($serverArgs | ForEach-Object { '"' + ($_ -replace '\\', '\\') + '"' }) -join ', '
        $block = @"

[mcp_servers.aurum-blender]
command = "$($python -replace '\\', '\\')"
args = [$argsToml]
"@
        if ($WhatIf) {
            Write-Ok "would append [mcp_servers.aurum-blender] to $codexConfig"
        } else {
            $existing = if (Test-Path $codexConfig) { Get-Content $codexConfig -Raw } else { '' }
            if ($existing -match '\[mcp_servers\.aurum-blender\]') {
                Write-Ok "Codex already knows about it: $codexConfig"
            } else {
                Add-Content -Path $codexConfig -Value $block -Encoding utf8
                Write-Ok "Codex: $codexConfig"
            }
        }
    }

    # Claude Code and several other clients read .mcp.json from the project.
    Write-JsonFile -Path (Join-Path $Project '.mcp.json') -Object @{
        mcpServers = @{ 'aurum-blender' = $entry }
    }

    # Cursor keeps a per-user map of servers.
    $cursor = Join-Path $env:USERPROFILE '.cursor\mcp.json'
    if (Test-Path (Split-Path -Parent $cursor)) {
        Write-JsonFile -Path $cursor -Object @{ mcpServers = @{ 'aurum-blender' = $entry } }
    }

    # Claude Desktop.
    $claude = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'
    if (Test-Path (Split-Path -Parent $claude)) {
        Write-JsonFile -Path $claude -Object @{ mcpServers = @{ 'aurum-blender' = $entry } }
    }
}

Write-Host ''
Write-Host 'Installed.' -ForegroundColor Green
Write-Host "  Add-on   $target"
Write-Host "  Server   $serverScript"
Write-Host "  Reload   restart Blender, or press Start Bridge in the Aurum MCP sidebar panel"
Write-Host ''
Write-Host 'Any MCP client can run the server directly:' -ForegroundColor Green
Write-Host "  $python `"$serverScript`" --root `"$Project`" --blender `"$blender`""
