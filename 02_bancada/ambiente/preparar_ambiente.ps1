# LEAKMAP - prepara o ambiente do TSNet no Windows e confere contra as simulacoes gravadas.
#
# Cria um ambiente virtual com Python 3.11 ou 3.12, instala as versoes
# congeladas (requirements-congelado.txt) e roda conferir_ambiente.py.
#
# Uso, no PowerShell, a partir da raiz do repositorio:
#   powershell -ExecutionPolicy Bypass -File 02_bancada\ambiente\preparar_ambiente.ps1
#   powershell -ExecutionPolicy Bypass -File 02_bancada\ambiente\preparar_ambiente.ps1 -Destino D:\leakmap_env -Completo
param(
    [string]$Destino = (Join-Path $env:USERPROFILE "leakmap_env"),
    [switch]$Completo
)
$ErrorActionPreference = "Stop"
$Aqui = Split-Path -Parent $MyInvocation.MyCommand.Path

# o wntr e o NumPy 1.26 nao gostam de caminho com acento
if ($Destino -match "[^\x00-\x7F]") {
    Write-Host "O destino '$Destino' tem acento. Use um caminho sem acento, por exemplo C:\leakmap_env." -ForegroundColor Red
    exit 1
}

# um Python 3.11 ou 3.12: primeiro o lancador py, depois o uv
$Python = $null
foreach ($versao in @("3.11", "3.12")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $caminho = (& py "-$versao" -c "import sys; print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $caminho) { $Python = $caminho.Trim(); break }
        } catch {}
    }
}
if (-not $Python -and (Get-Command uv -ErrorAction SilentlyContinue)) {
    foreach ($versao in @("3.11", "3.12")) {
        try {
            $caminho = (& uv python find $versao 2>$null)
            if ($LASTEXITCODE -eq 0 -and $caminho) { $Python = $caminho.Trim(); break }
        } catch {}
    }
}
if (-not $Python) {
    Write-Host "Nao achei Python 3.11 nem 3.12. Instale um deles (python.org, ou 'uv python install 3.11') e rode de novo." -ForegroundColor Red
    exit 1
}
Write-Host "Python da bancada: $Python"

if (-not (Test-Path (Join-Path $Destino "Scripts\python.exe"))) {
    & $Python -m venv $Destino
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
$Venv = Join-Path $Destino "Scripts\python.exe"
& $Venv -m pip install --upgrade pip --quiet
& $Venv -m pip install -r (Join-Path $Aqui "requirements-congelado.txt")
if ($LASTEXITCODE -ne 0) { exit 1 }

$argumentos = @((Join-Path $Aqui "conferir_ambiente.py"))
if ($Completo) { $argumentos += "--completo" }
& $Venv @argumentos
exit $LASTEXITCODE
