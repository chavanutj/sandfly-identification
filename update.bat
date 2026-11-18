@echo off
rem Double-click to rebuild the website from data\*.csv, check it, and open a local preview.
cd /d "%~dp0"
python scripts\update_site.py --serve
pause
