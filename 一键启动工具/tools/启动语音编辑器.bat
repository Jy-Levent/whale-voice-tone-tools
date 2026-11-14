@echo off
rem Whale Girl voice preset editor launcher
rem Keep this file pure ASCII + CRLF: cmd mis-parses BOM and LF line endings.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."

set "PY="
if exist "runtime\python\python.exe" set "PY=runtime\python\python.exe"
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)

if not defined PY (
  echo.
  echo [ERROR] Python not found.
  echo   Expected: %CD%\runtime\python\python.exe
  echo   Or install Python and add it to PATH.
  echo.
  pause
  exit /b 1
)

if /i "%~1"=="check" goto check

if not exist "bridge\voice_preset.py" (
  echo.
  echo [ERROR] bridge\voice_preset.py not found.
  echo   Current dir: %CD%
  echo.
  pause
  exit /b 1
)

if not exist "tools\voice-preset-editor.html" (
  echo.
  echo [ERROR] tools\voice-preset-editor.html not found.
  echo.
  pause
  exit /b 1
)

"%PY%" -u "bridge\voice_preset.py" ui
echo.
pause
exit /b 0

:check
echo.
echo  ==== self check ====
echo  CWD    : %CD%
echo  Python : %PY%
"%PY%" --version
if exist "bridge\voice_preset.py" (echo  voice_preset.py : OK) else (echo  voice_preset.py : MISSING)
if exist "tools\voice-preset-editor.html" (echo  editor html     : OK) else (echo  editor html     : MISSING)
if exist "data\voice-presets.json" (echo  presets json    : OK) else (echo  presets json    : MISSING)
if exist "bridge\voice_reply.py" (echo  voice_reply.py  : OK) else (echo  voice_reply.py  : MISSING)
echo.
pause
exit /b 0
