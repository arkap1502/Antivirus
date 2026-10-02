@echo off
echo Installing Laptop Antivirus...
python --version || (echo Install Python 3.10+ first! && pause && exit /b 1)
pip install -r requirements.txt
python autostart.py
echo.
echo Done! Run: python main.py
echo Restart laptop to test AUTO-ON at boot.
pause
