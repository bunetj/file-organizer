@echo off

set "AUTO=C:\Users\user\Home\documents\file sys\organization\automatic_organization"
set "LIST=%AUTO%\folders_preview.txt"
set "FLOW=%AUTO%\obsidian_flow_preview.bat"

for /f "usebackq delims=" %%F in ("%LIST%") do call :one "%%F"
pause
exit /b

:one
echo === %~1 ===
pushd "%~1"
if errorlevel 1 (
    echo pushd FAILED for [%~1]
    exit /b
)
if /i not "%AUTO%\org.py"=="%~1\org.py" copy /y "%AUTO%\org.py" "%~1\org.py" >nul
call "%FLOW%"
if /i not "%AUTO%\org.py"=="%~1\org.py" del "%~1\org.py"
popd
exit /b