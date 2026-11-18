param(
    [string]$GtaDir = 'C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V',
    [string]$CacheDir = (Join-Path $PSScriptRoot '.cache')
)

$ErrorActionPreference = 'Stop'

$codeWalkerCommit = '485d56bec00262ed7fa472261cce7bbc6202b96e'
$fontUrl = 'https://github.com/google/fonts/raw/4c1db3aec83c67dd223dd82a68c039cab30917a9/ofl/onest/Onest%5Bwght%5D.ttf'
$fontSha256 = '966C5C29B4755DA84B6854D5C21DD4EAA2420225D0E9874DE602DE176D4A9F31'

$resourceDir = Split-Path $PSScriptRoot -Parent
$streamDir = Join-Path $resourceDir 'stream'
$codeWalkerDir = Join-Path $CacheDir 'codewalker'
$fontPath = Join-Path $CacheDir 'font\Onest.ttf'
$binDir = Join-Path $CacheDir 'bin'
$origDir = Join-Path $CacheDir 'orig'
$workDir = Join-Path $CacheDir 'work'
$meshPath = Join-Path $CacheDir 'mesh.tsv'
$rawDir = Join-Path $CacheDir 'raw'
$renderDir = Join-Path $resourceDir 'renders'
$mascotPath = Join-Path $resourceDir '..\..\..\..\branding\mascot\cobalt-owl-dark.png'
$ytdtool = Join-Path $binDir 'ytdtool.exe'

$tiles = foreach ($row in 0..2) { foreach ($col in 0..1) { "minimap_sea_${row}_$col"; "minimap_${row}_$col" } }
$textureDicts = @($tiles) + 'minimap_lod_128'

function Invoke-Checked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "failed: $Command" }
}

if (-not (Test-Path -LiteralPath $codeWalkerDir)) {
    Invoke-Checked { git clone https://github.com/dexyfex/CodeWalker.git $codeWalkerDir }
}
Invoke-Checked { git -C $codeWalkerDir checkout --quiet $codeWalkerCommit }

if (-not (Test-Path -LiteralPath $fontPath)) {
    New-Item -ItemType Directory -Force (Split-Path $fontPath) | Out-Null
    Invoke-WebRequest $fontUrl -OutFile $fontPath
}
if ((Get-FileHash -LiteralPath $fontPath -Algorithm SHA256).Hash -ne $fontSha256) {
    Remove-Item -LiteralPath $fontPath
    throw 'Onest.ttf hash mismatch'
}

Invoke-Checked { dotnet build (Join-Path $PSScriptRoot 'ytdtool\ytdtool.csproj') -c Release -o $binDir -p:CodeWalkerDir=$codeWalkerDir }

Invoke-Checked { & $ytdtool extract $GtaDir $origDir @($textureDicts | ForEach-Object { "$_.ytd" }) }
Invoke-Checked { & $ytdtool mesh $GtaDir $meshPath }
Invoke-Checked { & $ytdtool raw $GtaDir $rawDir popzone.ipl }

Invoke-Checked { python (Join-Path $PSScriptRoot 'build_postals.py') $meshPath (Join-Path $resourceDir 'data\postals.lua') }
Invoke-Checked {
    python (Join-Path $PSScriptRoot 'build_tiles.py') --orig $origDir --mesh $meshPath --popzone (Join-Path $rawDir 'popzone.ipl') `
        --postals (Join-Path $resourceDir 'data\postals.lua') --font $fontPath --mascot $mascotPath `
        --out $workDir --renders $renderDir
}

New-Item -ItemType Directory -Force $streamDir | Out-Null
foreach ($name in $textureDicts) {
    Invoke-Checked { & $ytdtool pack (Join-Path $workDir $name) (Join-Path $streamDir "$name.ytd") }
}
Invoke-Checked { & $ytdtool recolour $GtaDir (Join-Path $workDir 'vertex_colours.tsv') (Join-Path $workDir 'overlay.tsv') (Join-Path $workDir 'knockouts.tsv') $streamDir }
