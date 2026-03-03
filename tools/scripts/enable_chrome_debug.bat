@echo off
echo ===== 启用Chrome远程调试模式 =====
echo.
echo 此脚本将为您当前的Chrome浏览器启用远程调试功能
echo 无需关闭现有的浏览器窗口和标签页
echo.

echo 正在检查Chrome进程...
tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I /N "chrome.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo 检测到Chrome正在运行
    echo.
    echo 请按以下步骤操作：
    echo 1. 在Chrome地址栏输入: chrome://flags/
    echo 2. 搜索 "remote-debugging-port"
    echo 3. 或者重启Chrome时添加调试参数
    echo.
    echo 推荐方法：关闭Chrome后运行以下命令
    echo "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
    echo.
) else (
    echo Chrome未运行，正在启动带调试模式的Chrome...
    echo.
    "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
    
    if %ERRORLEVEL% NEQ 0 (
        echo Chrome启动失败，请检查安装路径
        echo 尝试其他可能的路径...
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
    )
)

echo.
echo 完成！现在可以运行 linkedin_scraper_existing.py
echo 或者运行 run_existing_browser.bat
echo.
pause