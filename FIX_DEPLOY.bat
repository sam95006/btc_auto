@echo off
echo ==========================================
echo 🚀 BTC Bot Deployment Emergency Repair
echo ==========================================
echo.
echo [1/3] 正在準備整合代碼...
git add requirements.txt main.py sensors.py
echo.
echo [2/3] 正在執行強制修復 commit...
git commit -m "fix(deploy): high-availability startup sequence and dependency sync"
echo.
echo [3/3] 正在發射到 GitHub (喚醒 Zeabur)...
git push
echo.
echo ==========================================
echo ✅ 修復指令已送達雲端！
echo 請回到 Zeabur 儀表板點擊「重啟」按鈕，
echo 並觀察 LINE 報表。
echo ==========================================
pause
