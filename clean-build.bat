@echo off
setlocal EnableExtensions
rem Avio: clean the build outputs, then build the Windows installers.
rem
rem Usage: clean-build.bat [--full] [--deps] [--no-build]
rem   --full      also run "cargo clean" (the whole Rust target folder; the next build takes much longer)
rem   --deps      also reinstall dependencies (npm ci, and pip install into backend\.venv)
rem   --no-build  clean only, do not build

cd /d "%~dp0"

set "FULL=0"
set "DEPS=0"
set "BUILD=1"

:args
if "%~1"=="" goto argsdone
if /i "%~1"=="--full"     (set "FULL=1"  & shift & goto args)
if /i "%~1"=="--deps"     (set "DEPS=1"  & shift & goto args)
if /i "%~1"=="--no-build" (set "BUILD=0" & shift & goto args)
if /i "%~1"=="--help" goto usage
if /i "%~1"=="-h" goto usage
echo Unknown option: %~1
goto usage
:argsdone

for %%t in (node npm cargo) do (
  where %%t >nul 2>&1 || (echo Missing: %%t is not on PATH. & exit /b 1)
)

rem A running Avio holds its files open, and the build would fail halfway.
echo.
echo == Checking that Avio is not running
for %%e in (avio.exe sf_backend.exe) do (
  tasklist /FI "IMAGENAME eq %%e" 2>nul | find /i "%%e" >nul && (echo %%e is running. Close Avio first. & exit /b 1)
)
echo OK

echo.
echo == Cleaning build outputs
for %%d in ("frontend\dist" "backend\dist" "backend\build" "backend\__pycache__" "dist" "src-tauri\target\release\bundle") do (
  if exist "%%~d" (
    rmdir /s /q "%%~d"
    if exist "%%~d" (echo Could not remove %%~d: a file in it is in use. & exit /b 1)
    echo removed %%~d
  )
)

if "%FULL%"=="1" (
  echo.
  echo == cargo clean ^(full Rust clean^)
  pushd src-tauri
  cargo clean || (popd & exit /b 1)
  popd
)

if "%DEPS%"=="1" (
  echo.
  echo == Reinstalling Node dependencies
  call npm ci || exit /b 1
  pushd frontend
  call npm ci || (popd & exit /b 1)
  popd
  echo.
  echo == Reinstalling Python dependencies
  if not exist "backend\.venv\Scripts\python.exe" (
    python -m venv backend\.venv || exit /b 1
  )
  backend\.venv\Scripts\python.exe -m pip install --upgrade pip || exit /b 1
  backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt || exit /b 1
)

if "%BUILD%"=="0" (
  echo.
  echo == Clean done ^(--no-build^)
  exit /b 0
)

if not exist "node_modules" (echo node_modules missing: run again with --deps & exit /b 1)
if not exist "frontend\node_modules" (echo frontend\node_modules missing: run again with --deps & exit /b 1)
if not exist "backend\.venv\Scripts\python.exe" (echo Python venv missing: run again with --deps & exit /b 1)

rem Keep the build machine's user path out of avio.exe.
set "RUSTFLAGS=--remap-path-prefix=%USERPROFILE%=~"

echo.
echo == Building (backend, frontend, Tauri bundle). This takes about 7 minutes.
set "START=%TIME%"
call npm run tauri:build
if errorlevel 1 (echo. & echo BUILD FAILED & exit /b 1)

echo.
echo == Installers (started %START%, finished %TIME%)
powershell -NoProfile -Command "Get-ChildItem 'src-tauri\target\release\bundle\nsis\*.exe','src-tauri\target\release\bundle\msi\*.msi' -ErrorAction SilentlyContinue | ForEach-Object { (Get-FileHash -Algorithm SHA256 $_.FullName).Hash + '  ' + $_.FullName }"
exit /b 0

:usage
echo Usage: clean-build.bat [--full] [--deps] [--no-build]
echo   --full      also run "cargo clean" (the next build takes much longer)
echo   --deps      also reinstall dependencies (npm ci, pip install into backend\.venv)
echo   --no-build  clean only, do not build
exit /b 2
