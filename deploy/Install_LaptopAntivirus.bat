@echo off
REM Laptop Antivirus - Deploy Installer (EXE version, no Python needed)
echo Installing Laptop Antivirus...
echo.

REM 1. Startup folder (auto ON at login, no admin needed)
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
echo Adding to Startup folder...
echo @echo off > "%STARTUP%\LaptopAntivirus.bat"
echo start "" /min "%~dp0LaptopAntivirus.exe" >> "%STARTUP%\LaptopAntivirus.bat"
echo OK - Startup installed.

REM 2. Task Scheduler (auto ON at logon)
echo Adding Task Scheduler entry...
schtasks /create /tn "LaptopAntivirus" /tr "'%~dp0LaptopAntivirus.exe'" /sc onlogon /rl limited /f
echo.
echo Done! Restart your laptop - antivirus will auto-start.
echo To run now, double-click LaptopAntivirus.exe
pause
