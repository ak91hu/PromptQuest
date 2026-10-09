$PythonArgs = $args
$runtimeRoot = Join-Path $PSScriptRoot '..\.runtime'
$localRuntime = Join-Path $runtimeRoot 'python.exe'
$venvPython = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
if (Test-Path -LiteralPath (Join-Path $runtimeRoot 'config.json')) {
    $runtimeConfig = Get-Content -LiteralPath (Join-Path $runtimeRoot 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $env:PYTHONHOME = $runtimeConfig.home
    $env:PYTHONPATH = (Join-Path $runtimeRoot 'DLLs') + ';' + $runtimeConfig.packages
    & $localRuntime @PythonArgs
} elseif (Test-Path -LiteralPath $venvPython) {
    & $venvPython @PythonArgs
} else {
    py -3.13 @PythonArgs
}
exit $LASTEXITCODE

