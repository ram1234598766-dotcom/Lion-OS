@echo off
REM ============================================================================
REM  Lion-OS  --  double-click installer (Windows)
REM  Invokes the Rust installation manager (`lionos install`).
REM  QEMU is a HARD requirement: the install aborts if it cannot be installed.
REM  Use `lionos install --detach` to run entirely in the background.
REM ============================================================================
setlocal
set "ROOT=%~dp0.."

REM self-elevate if we aren't already admin (winget installing QEMU needs it)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights to install QEMU...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b 0
)

REM Prefer a release lionos.exe; fall back to debug, then cargo run.
set "EXE="
for %%D in ("%ROOT%\target\release" "%ROOT%\target\debug") do (
    if exist "%%~D\lionos.exe" set "EXE=%%~D\lionos.exe"
)
if not defined EXE (
    echo [ERROR] lionos.exe not built. Build it once with:
    echo    cd launcher ^&^& cargo build --release
    pause
    exit /b 1
)

echo Using installer: "%EXE%"
echo This installs QEMU + build deps + the Rust toolchain, then builds the image.
echo Log is written to %USERPROFILE%\.lionos\install.log
"%EXE%" install --detach

echo.
echo Lion-OS is installing in the background.
echo   Check progress: powershell -NoProfile -Command "Get-Content $env:USERPROFILE\.lionos\install.log -Wait"
pause