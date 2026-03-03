@echo off
chcp 65001 >nul
echo ========================================
echo LinkedIn营销系统 - Chrome调试模式启动器
echo ========================================
echo.

REM 设置Chrome调试端口
set DEBUG_PORT=9222

REM 设置用户数据目录
set USER_DATA_DIR=%USERPROFILE%\AppData\Local\Google\Chrome\User Data\LinkedIn

REM 检查Chrome是否已在调试模式运行
netstat -an | findstr ":%DEBUG_PORT%" >nul
if %errorlevel% == 0 (
    echo ⚠️  Chrome调试模式已在运行 (端口: %DEBUG_PORT%)
    echo 💡 如需重启，请先关闭所有Chrome窗口
    echo.
    goto :end
)

echo 🔍 正在查找Chrome安装路径...

REM 查找Chrome可执行文件
set CHROME_PATH=

REM 检查常见安装路径
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
) else (
    echo ❌ 未找到Chrome安装路径
    echo 💡 请确保已安装Google Chrome浏览器
    echo.
    pause
    exit /b 1
)

echo ✅ 找到Chrome: %CHROME_PATH%
echo.

REM 创建用户数据目录
if not exist "%USER_DATA_DIR%" (
    echo 📁 创建Chrome用户数据目录...
    mkdir "%USER_DATA_DIR%" 2>nul
)

echo 🚀 启动Chrome调试模式...
echo 📍 调试端口: %DEBUG_PORT%
echo 📁 用户数据目录: %USER_DATA_DIR%
echo.

REM 启动Chrome调试模式
start "Chrome Debug" "%CHROME_PATH%" ^--remote-debugging-port=%DEBUG_PORT% ^--user-data-dir="%USER_DATA_DIR%" ^--disable-web-security ^--disable-features=VizDisplayCompositor ^--no-first-run ^--no-default-browser-check ^--disable-default-apps ^--disable-popup-blocking ^--disable-translate ^--disable-background-timer-throttling ^--disable-renderer-backgrounding ^--disable-backgrounding-occluded-windows ^--disable-ipc-flooding-protection ^--window-size=1200,800 ^--window-position=100,100

REM 等待Chrome启动
echo ⏳ 等待Chrome启动...
timeout /t 3 /nobreak >nul

REM 检查Chrome是否成功启动
netstat -an | findstr ":%DEBUG_PORT%" >nul
if %errorlevel% == 0 (
    echo ✅ Chrome调试模式启动成功！
    echo.
    echo 📋 下一步操作:
    echo 1. 在Chrome中访问 https://www.linkedin.com
    echo 2. 登录您的LinkedIn账户
    echo 3. 运行LinkedIn营销系统: python main.py
    echo.
    echo 🔗 调试地址: http://localhost:%DEBUG_PORT%
    echo 💡 保持此窗口打开，关闭将停止调试模式
) else (
    echo ❌ Chrome调试模式启动失败
    echo 💡 请检查端口 %DEBUG_PORT% 是否被占用
)

:end
echo.
echo 按任意键退出...
pause >nul