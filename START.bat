@echo off
setlocal
title PC-Check USB
chcp 65001 >nul
"%~dp0runtime\python.exe" -B -X utf8 "%~dp0check.py"
if errorlevel 1 pause
