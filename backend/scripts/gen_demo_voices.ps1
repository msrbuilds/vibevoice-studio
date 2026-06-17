# Generate 4 short mono WAV reference clips using Windows' built-in
# System.Speech synthesizer. Output is 16 kHz mono PCM_16 — the 1.5B
# model accepts any sample rate between 8 kHz and 48 kHz.
#
# Run with: powershell -ExecutionPolicy Bypass -File gen_demo_voices.ps1

param(
    [string]$OutDir = "$PSScriptRoot\..\voices"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$OutDir = (Resolve-Path $OutDir).Path
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

# Try preferred voices, fall back to default.
$voiceMap = @{
    "en-Emma_woman"  = @("Microsoft Zira Desktop", "Microsoft Hazel Desktop")
    "en-Carter_man"  = @("Microsoft David Desktop")
    "en-Frank_man"   = @("Microsoft Mark - English (United States)")
    "en-Grace_woman" = @()
}

$text = @"
Hello, my name is a generic speaker. I will be reading a short passage about everyday life.
The weather today is calm, and people are going about their routines.
It is a perfectly ordinary morning, and I am happy to share this moment with you.
This recording will be used as a voice reference for a text-to-speech system.
"@

$installed = (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() |
    Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name }

Write-Host "Installed SAPI voices:"
$installed | ForEach-Object { Write-Host "  $_" }
Write-Host ""

$ss = New-Object System.Speech.Synthesis.SpeechSynthesizer
$ss.Rate = -1   # slightly slower for naturalness

$ok = 0
foreach ($name in $voiceMap.Keys) {
    $path = Join-Path $OutDir "$name.wav"
    $chosen = $null
    foreach ($candidate in $voiceMap[$name]) {
        if ($installed -contains $candidate) { $chosen = $candidate; break }
    }
    if ($chosen) {
        try {
            $ss.SelectVoice($chosen)
            Write-Host "  $name -> $chosen"
        } catch {
            Write-Host "  $name -> default (SelectVoice failed: $_)"
        }
    } else {
        Write-Host "  $name -> default (no preferred voice installed)"
    }
    try {
        $ss.SetOutputToWaveFile($path)
        $ss.Speak($text)
        $ss.SetOutputToDefaultAudioDevice() | Out-Null
        $size = (Get-Item $path).Length
        Write-Host "    wrote $path ($size bytes)"
        $ok++
    } catch {
        Write-Host "    FAILED: $_"
        if (Test-Path $path) { Remove-Item $path }
    }
}

$ss.Dispose()

if ($ok -eq 0) {
    Write-Host ""
    Write-Host "No voices generated. The Windows speech engine may not be available."
    Write-Host "Use the UI upload button instead (+ next to 'My voices')."
    exit 1
}
Write-Host ""
Write-Host "Generated $ok voices. Restart the backend to pick them up."
