@echo off
setlocal
set "NF_PY=C:\Users\ltllt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%NF_PY%" (
  echo Bundled Python runtime unavailable: "%NF_PY%" 1>&2
  exit /b 2
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%NF_PY%" "%~dp0engine\native_forge.py" %*
exit /b %ERRORLEVEL%
