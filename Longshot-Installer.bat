@echo off
rem Opens the OoTRR seed installer for Longshot (no console window).
cd /d "%~dp0"
start "" pythonw -m ootrr.tools.longshot_app
