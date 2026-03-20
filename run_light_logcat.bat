@echo off
setlocal
cd /d "%~dp0"

rem Python 検出
set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py"
if not defined PYEXE (
  where python >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
  echo Pythonが見つかりません。 https://www.python.org/ からインストールしてください。
  exit /b 1
)

%PYEXE% "%~dp0main_light_logcat.py"
endlocal

