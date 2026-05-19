@echo off
echo ==========================================
echo 🚀 BTC Bot Deployment Auto Repair
echo ==========================================
echo.
echo [1/3] Adding files to git...
git add .
echo.
echo [2/3] Committing changes...
git commit -m "fix(deploy): add LINE env var validation and health checks"
echo.
echo [3/3] Pushing to GitHub...
git push
echo.
echo ==========================================
echo ✅ Changes pushed to GitHub!
echo Please check Zeabur dashboard to see the progress.
echo If it doesn't auto-deploy, click the "Restart" button.
echo ==========================================
pause
