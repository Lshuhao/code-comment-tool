@echo off
chcp 65001 >nul
title 代码注释工具 - Tkinter桌面版

set ROOT_DIR=%~dp0
cd /d "%ROOT_DIR%"

D:\python\python.exe backend/app/gui/app.py
