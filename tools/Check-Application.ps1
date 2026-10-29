param(
    [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot),
    [switch]$RequireReady
)
$ErrorActionPreference = 'Stop'
$toolRoot = Split-Path -Parent $PSScriptRoot
$settingsPath = Join-Path $toolRoot '.runtime/application-dev.json'
if (-not (Test-Path -LiteralPath $settingsPath)) {
    throw 'Configure .runtime/application-dev.json with linux_python, core_source and frontend_root; see docs/APPLICATION_DEVELOPMENT.md.'
}
$settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
foreach ($name in @('linux_python', 'core_source', 'frontend_root')) {
    if (-not $settings.$name) { throw "Missing development setting: $name" }
}
$resolvedProject = (Resolve-Path -LiteralPath $ProjectPath).Path
$linuxProject = (& wsl.exe -e wslpath -a -u $resolvedProject).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the project directory in WSL.' }
$arguments = @('-e', 'env', 'PYTHONDONTWRITEBYTECODE=1', [string]$settings.linux_python,
    "$linuxProject/tools/check_application.py", '--project', $linuxProject,
    '--core-source', [string]$settings.core_source, '--frontend-root', [string]$settings.frontend_root)
if ($RequireReady) { $arguments += '--require-ready' }
& wsl.exe @arguments
exit $LASTEXITCODE
