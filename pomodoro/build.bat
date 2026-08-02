@echo off
REM 打包番茄钟为独立 exe(dist\番茄钟\番茄钟.exe,整目录拷贝即分发)
cd /d "%~dp0"
py -m PyInstaller --noconfirm --clean --noconsole --onedir --name 番茄钟 ^
  --collect-all customtkinter --collect-submodules pystray --hidden-import pystray._win32 ^
  main.py
echo.
echo 打包完成:dist\番茄钟\番茄钟.exe
pause
