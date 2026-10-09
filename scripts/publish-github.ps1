param([string]$Branch)
$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$targetRepo = 'ak91hu/PromptQuest'

function Assert-LastCommand([string]$Action) {
    if ($LASTEXITCODE -ne 0) { throw "$Action failed. No automatic retry will be made." }
}

& (Join-Path $PSScriptRoot 'run-python.ps1') (Join-Path $PSScriptRoot 'check-publication.py')
Assert-LastCommand 'Checking publication for private files and credentials'

# Switch only to the explicitly requested existing account.
& gh auth switch --hostname github.com --user ak91hu
Assert-LastCommand 'Selecting ak91hu'
$actor = & gh api user --jq .login
Assert-LastCommand 'Checking GitHub identity'
if ($actor.Trim() -cne 'ak91hu') { throw 'Publication requires the ak91hu GitHub account.' }
$actorId = & gh api user --jq .id
Assert-LastCommand 'Reading author identity'
if ($actorId.Trim() -notmatch '^\d+$') { throw 'Invalid GitHub account ID.' }
if (-not $Branch) {
    $Branch = & gh api "repos/$targetRepo" --jq .default_branch
    Assert-LastCommand 'Reading repository default branch'
    $Branch = $Branch.Trim()
}
& git check-ref-format --branch $Branch
Assert-LastCommand 'Checking branch name'

$manifest = Get-Content -LiteralPath (Join-Path $sourceRoot 'deploy/publication-files.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$publishDir = Join-Path $sourceRoot ('outputs/PromptQuest-publish-' + [Guid]::NewGuid().ToString('N'))
& git clone "https://github.com/$targetRepo.git" $publishDir
if ($LASTEXITCODE -ne 0) {
    throw 'Clone failed. Check repository access and network connectivity.'
}
foreach ($relative in $manifest.files) {
    if ($relative -match '(^|/)(\.env[^/]*|\.data|\.runtime|\.venv|outputs|node_modules|\.git)(/|$)' -and $relative -ne '.env.example') {
        throw "Excluded path in publication manifest: $relative"
    }
    $from = [IO.Path]::GetFullPath((Join-Path $sourceRoot $relative))
    $to = [IO.Path]::GetFullPath((Join-Path $publishDir $relative))
    if (-not $from.StartsWith($sourceRoot + [IO.Path]::DirectorySeparatorChar) -or
        -not $to.StartsWith($publishDir + [IO.Path]::DirectorySeparatorChar)) {
        throw 'Publication path escaped the workspace.'
    }
    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($to)) -Force | Out-Null
    Copy-Item -LiteralPath $from -Destination $to
}
Push-Location $publishDir
try {
    & git show-ref --verify --quiet "refs/heads/$Branch"
    if ($LASTEXITCODE -eq 0) {
        & git switch $Branch
    } elseif ($LASTEXITCODE -eq 1) {
        & git switch -c $Branch
    } else {
        throw 'Unable to inspect the publication branch.'
    }
    Assert-LastCommand 'Selecting publication branch'
    & git config user.name ak91hu
    Assert-LastCommand 'Setting local author name'
    & git config user.email ($actorId.Trim() + '+ak91hu@users.noreply.github.com')
    Assert-LastCommand 'Setting local author email'
    foreach ($relative in $manifest.files) {
        & git add -- $relative
        Assert-LastCommand "Staging $relative"
    }
    & (Join-Path $PSScriptRoot 'run-python.ps1') (Join-Path $PSScriptRoot 'check-publication.py') --staged-root $publishDir
    Assert-LastCommand 'Checking the complete Git index for private files and credentials'
    & git diff --cached --stat
    Assert-LastCommand 'Checking staged publication'
    & git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'The repository already contains these files.'
        exit 0
    }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to check the staged changes.' }
    & git commit -m 'Add Asterion game, detailed English documentation and Northflank deployment'
    Assert-LastCommand 'Committing publication'
    & git push origin $Branch
    Assert-LastCommand 'Publishing to PromptQuest'
    & git rev-parse HEAD
    Assert-LastCommand 'Reading published commit'
    Write-Host "Published as ak91hu to https://github.com/$targetRepo"
} finally {
    Pop-Location
}
