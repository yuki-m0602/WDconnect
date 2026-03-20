param(
    [switch]$Install
)

Set-Location -LiteralPath $PSScriptRoot

# Python 検出
$pyexe = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $pyexe = 'py' }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pyexe = 'python' }

if (-not $pyexe) {
    Write-Error 'Pythonが見つかりません。 https://www.python.org/ からインストールしてください。'
    exit 1
}

if ($Install) {
    if (Test-Path -LiteralPath 'requirements.txt') {
        & $pyexe -m pip install -r requirements.txt --upgrade --quiet
    }
}

& $pyexe "${PSScriptRoot}\main_light_logcat.py"

