@echo off
setlocal
if not defined NATIVE_FORGE_HOME set "NATIVE_FORGE_HOME=E:\PDF\_ZH\native-forge"
if not exist "%NATIVE_FORGE_HOME%\nf.cmd" (
  echo Native Forge not found. Set NATIVE_FORGE_HOME to the engine directory. 1>&2
  exit /b 2
)
call "%NATIVE_FORGE_HOME%\nf.cmd" %*
exit /b %ERRORLEVEL%
