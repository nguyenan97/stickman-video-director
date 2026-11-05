# Wrapper for the Dockerized Autopilot runtime.
#   .\docker\run.ps1 build                       # build image
#   .\docker\run.ps1 doctor                      # dependency/font/key-presence check (no network)
#   .\docker\run.ps1 autopilot init <idea-id>/stickman --style B1
#   .\docker\run.ps1 gemini speech --text ... --output ... --model ... --voice ... --allow-network
#   .\docker\run.ps1 captions <audio> --output <words.json> [--allow-model-download]
#   .\docker\run.ps1 shell
# Paths are relative to /work = AI-Video-Studio/ideas (or $env:STICKMAN_WORK).
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("build", "doctor", "autopilot", "gemini", "captions", "shell")]
    [string]$Tool,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest = @()
)
$ErrorActionPreference = "Stop"
$compose = Join-Path $PSScriptRoot "compose.yaml"

switch ($Tool) {
    "build"     { docker compose -f $compose build; break }
    "doctor"    { docker compose -f $compose run --rm stickman node /opt/skill/scripts/autopilot.mjs doctor; break }
    "autopilot" { docker compose -f $compose run --rm stickman node /opt/skill/scripts/autopilot.mjs @Rest; break }
    "gemini"    { docker compose -f $compose run --rm stickman node /opt/skill/scripts/gemini-media.mjs @Rest; break }
    "captions"  { docker compose -f $compose run --rm stickman python3 /opt/skill/scripts/align_captions.py @Rest; break }
    "shell"     { docker compose -f $compose run --rm stickman bash; break }
}
exit $LASTEXITCODE
