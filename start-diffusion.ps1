param([switch]$Preview,[long]$Seed=20260927,[string]$Conditions='')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$python=Join-Path $PSScriptRoot 'runtime/venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run tools/setup_diffusion.py and tools/download_model.py first.' }
$env:PYTHONDONTWRITEBYTECODE='1'
$arguments=@('-X','utf8','-B','-m','diffusion','--seed',"$Seed")
if ($Preview) { $arguments+='--preview' }
if ($Conditions) { $arguments+=@('--conditions',$Conditions) }
& $python @arguments
exit $LASTEXITCODE
