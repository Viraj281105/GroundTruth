# Renders every narration sentence to a WAV with the local Windows voice (System.Speech, no network,
# no installation). Usage: powershell -File tts.ps1 -Narration narration.json -OutDir <dir>
param([string]$Narration, [string]$OutDir, [int]$Rate = -1)
Add-Type -AssemblyName System.Speech
$doc = Get-Content -Raw -Encoding UTF8 $Narration | ConvertFrom-Json
New-Item -ItemType Directory -Force $OutDir | Out-Null
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice($doc.voice)
$synth.Rate = $Rate
foreach ($scene in $doc.scenes) {
  for ($i = 0; $i -lt $scene.sentences.Count; $i++) {
    $file = Join-Path $OutDir ("{0}-{1}.wav" -f $scene.id, ($i + 1))
    $synth.SetOutputToWaveFile($file)
    $synth.Speak($scene.sentences[$i])
    $synth.SetOutputToNull()
  }
}
$synth.Dispose()
Write-Output "rendered to $OutDir"
