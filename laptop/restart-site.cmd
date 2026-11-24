@echo off
title Restart CS2 ROOM
schtasks /End /TN "CS2Room site" >nul 2>&1
schtasks /Run /TN "CS2Room site"
echo CS2 ROOM site restarted.
timeout /t 4 >nul
