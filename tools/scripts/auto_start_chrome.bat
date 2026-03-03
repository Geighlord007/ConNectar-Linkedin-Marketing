@echo off
chcp 65001 >nul
echo ========================================
echo LinkedIn营销系统 - 自动启动Chrome调试模式
echo ========================================
echo.

echo 正在检查Chrome调试模式状态...
netstat -an | findstr ":9222" >nul
if %errorlevel% == 0 (
    echo Chrome调试模式已在运行 (端口: 9222)
    echo 如需重启，请先关闭所有Chrome窗口
    pause
    exit /b
)

echo 正在启动Chrome调试模式...
echo.

REM 查找Chrome安装路径
set "CHROME_PATH="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
)

if "%CHROME_PATH%"=="" (
    echo 错误: 未找到Chrome安装路径
    echo 请确保已安装Google Chrome浏览器
    pause
    exit /b 1
)

echo 找到Chrome: %CHROME_PATH%
echo.

REM 创建用户数据目录
set "USER_DATA_DIR=%USERPROFILE%\AppData\Local\Google\Chrome\User Data\LinkedIn"
if not exist "%USER_DATA_DIR%" (
    echo 创建Chrome用户数据目录...
    mkdir "%USER_DATA_DIR%"
)

REM 启动Chrome调试模式
echo 启动Chrome调试模式...
echo 调试端口: 9222
echo 用户数据目录: %USER_DATA_DIR%
echo.

start "" "%CHROME_PATH%" --remote-debugging-port=9222 --user-data-dir="%USER_DATA_DIR%" --disable-web-security --disable-features=VizDisplayCompositor --no-first-run --no-default-browser-check --disable-default-apps --disable-popup-blocking --disable-translate --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-ipc-flooding-protection --window-size=1200,800 --window-position=100,100 https://www.linkedin.com/feed/

REM 等待Chrome启动
echo 等待Chrome启动...
timeout /t 3 /nobreak >nul

REM 检查Chrome是否成功启动
netstat -an | findstr ":9222" >nul
if %errorlevel% == 0 (
    echo.
    echo ✅ Chrome调试模式启动成功！
    echo.
    echo 下一步操作:
    echo 1. 在Chrome中访问 https://www.linkedin.com
    echo 2. 登录您的LinkedIn账户
    echo 3. 运行LinkedIn营销系统: python main.py
    echo.
    echo 调试地址: http://localhost:9222
    echo Chrome已在后台运行，可以关闭此窗口
) else (
    echo.
    echo ❌ Chrome调试模式启动失败
    echo 请检查端口 9222 是否被占用
)

echo.
pause