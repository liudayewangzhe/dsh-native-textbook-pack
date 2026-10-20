@echo off
rem ===================================================================
rem  Native Chinese textbook pack - one-click installer
rem  Double-click this file, or run it from a terminal.
rem
rem  NOTE: install.ps1 contains Chinese text and MUST stay UTF-8 *with BOM*,
rem  otherwise Windows PowerShell 5.1 decodes it as ANSI/GBK and fails to parse.
rem  The block below re-adds the BOM if it is missing.
rem ===================================================================
setlocal
cd /d "%~dp0"

if not exist "%~dp0install.ps1" (
  echo [ERROR] install.ps1 not found next to this file.
  echo         Run this from the fully extracted pack directory.
  pause
  exit /b 2
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%~dp0install.ps1'; $b=[IO.File]::ReadAllBytes($p); if(-not ($b.Length -ge 3 -and $b[0] -eq 239 -and $b[1] -eq 187 -and $b[2] -eq 191)) { $bom=[byte[]](239,187,191); [IO.File]::WriteAllBytes($p, ($bom + $b)); Write-Host 'install.ps1: UTF-8 BOM restored.' }"

set "PS=pwsh.exe"
where pwsh.exe >nul 2>nul || set "PS=powershell.exe"

echo Using %PS%
echo.
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (echo Installer finished OK.) else (echo Installer exited with code %RC%.)
echo Press any key to close this window...
pause >nul
exit /b %RC%
