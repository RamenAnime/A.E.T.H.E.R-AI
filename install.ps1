# A.E.T.H.E.R. Windows setup
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    python -m venv .venv
}
.\.venv\Scripts\pip install -e .
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example"
}
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Install Ollama from https://ollama.com/download"
Write-Host "  2. ollama pull llama3.1:8b"
Write-Host "  3. .\.venv\Scripts\activate"
Write-Host "  4. aether doctor"
Write-Host "  5. aether web"
Write-Host "  6. aether chat `"Hello`""
