@echo off
rem Import ArtSource\ into /Game/IronReign with the Unreal editor's Python commandlet (DESIGN.md section 12).
rem
rem   Tools\Unreal\build_assets.bat [--incremental] [--rhi] [extra editor arguments...]
rem
rem   --incremental   only rebuild when ArtSource\manifest.json "version" (or the pipeline) changed
rem   --rhi           run with a real RHI instead of -nullrhi
rem
rem Environment: UE_EDITOR (editor binary) or UE_ROOT (folder containing Engine\,
rem default "C:\Program Files\Epic Games\UE_5.8"). Build the IronReignEditor target first.
rem Exit code: 0 OK, 1 import failed, 2 setup problem.
setlocal EnableExtensions EnableDelayedExpansion

set "HERE=%~dp0"
for %%I in ("%HERE%..\..") do set "PROJECT_DIR=%%~fI"
set "UPROJECT=%PROJECT_DIR%\IronReign.uproject"
set "RESULT_FILE=%PROJECT_DIR%\Saved\IronReign\asset_build_result.txt"
set "STATUS_FILE=%PROJECT_DIR%\Saved\IronReign\asset_version.txt"
set "FORCE=1"
set "RHI_ARG=-nullrhi"
set "EXTRA_ARGS="

:parse
if "%~1"=="" goto parsed
if /I "%~1"=="--incremental" (
  set "FORCE=0"
) else if /I "%~1"=="--rhi" (
  set "RHI_ARG="
) else (
  set "EXTRA_ARGS=!EXTRA_ARGS! %1"
)
shift
goto parse
:parsed

if not exist "%PROJECT_DIR%\ArtSource\manifest.json" (
  echo error: "%PROJECT_DIR%\ArtSource\manifest.json" not found - generate ArtSource with Tools\BlenderArt first. 1>&2
  exit /b 2
)

if defined UE_EDITOR (
  set "EDITOR=!UE_EDITOR!"
) else (
  if not defined UE_ROOT set "UE_ROOT=C:\Program Files\Epic Games\UE_5.8"
  set "EDITOR=!UE_ROOT!\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
)
if not exist "!EDITOR!" (
  echo error: Unreal Editor not found at "!EDITOR!". Set UE_ROOT or UE_EDITOR. 1>&2
  exit /b 2
)

echo [build_assets] editor:  !EDITOR!
echo [build_assets] project: %UPROJECT% (force=%FORCE%)
if exist "%RESULT_FILE%" del /q "%RESULT_FILE%"

rem IRONREIGN_SKIP_AUTO_IMPORT keeps init_unreal.py from starting a second import inside the commandlet.
set "IRONREIGN_IMPORT_FORCE=%FORCE%"
set "IRONREIGN_SKIP_AUTO_IMPORT=1"
"!EDITOR!" "%UPROJECT%" -run=pythonscript -script="%HERE%run_import.py" -unattended -nopause -nosplash -nosound -stdout -FullStdOutLogOutput %RHI_ARG% %EXTRA_ARGS%
set "EDITOR_STATUS=%ERRORLEVEL%"

set "RESULT=MISSING"
if exist "%RESULT_FILE%" set /p RESULT=<"%RESULT_FILE%"
echo [build_assets] editor exit code %EDITOR_STATUS%, import result: %RESULT% (details: %STATUS_FILE%)
if "%RESULT%"=="OK" exit /b 0
exit /b 1
