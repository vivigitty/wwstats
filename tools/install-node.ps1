$ErrorActionPreference = 'Stop'
$tools = Join-Path $env:USERPROFILE '.tools'
New-Item -ItemType Directory -Force -Path $tools | Out-Null

$index = Invoke-RestMethod 'https://nodejs.org/dist/index.json'
$version = ($index | Where-Object { $_.lts } | Select-Object -First 1).version
$name = "node-$version-win-x64"
$target = Join-Path $tools $name

if (-not (Test-Path (Join-Path $target 'node.exe'))) {
    $zip = Join-Path $tools "$name.zip"
    Write-Host "Downloading Node $version..."
    Invoke-WebRequest "https://nodejs.org/dist/$version/$name.zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath $tools -Force
    Remove-Item $zip
}

$env:Path = "$target;$env:Path"
Write-Host "NODE_HOME=$target"
node --version
npm --version
