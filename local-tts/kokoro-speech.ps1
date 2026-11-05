# Host-side local narration for Autopilot (offline Kokoro-82M, no API key).
#   .\local-tts\kokoro-speech.ps1 --text script.txt --output voice.wav --brand ..\AI-Video-Studio\ideas\<id>\brand.json --words words.json
#   .\local-tts\kokoro-speech.ps1 --text script.txt --output voice.wav --voice af_bella --speed 0.9 --loudnorm -18
# Kokoro venv defaults to the sibling ..\kokoro checkout; override with $env:KOKORO_HOME.
# Default device is CPU so the GPU stays free for ComfyUI / ACE-Step (run GPU jobs one at a time).
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest = @())
$ErrorActionPreference = "Stop"
$kokoroHome = if ($env:KOKORO_HOME) { $env:KOKORO_HOME } else { Join-Path $PSScriptRoot "..\..\kokoro" }
$python = Join-Path $kokoroHome ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Kokoro venv not found at $python (set KOKORO_HOME)" }
$env:PYTHONUTF8 = "1"
& $python -I (Join-Path $PSScriptRoot "kokoro_speech.py") @Rest
exit $LASTEXITCODE
