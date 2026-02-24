$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

try {
    & $PythonBin -m PyInstaller --version | Out-Null
}
catch {
    Write-Error "PyInstaller is not installed. Run: $PythonBin -m pip install -r $RootDir/requirements-build.txt"
}

Set-Location $RootDir
& $PythonBin -m PyInstaller --clean --noconfirm packaging/llm_gateway.spec
Write-Output "[OK] Binary created at: $RootDir/dist/llm-gateway.exe"
