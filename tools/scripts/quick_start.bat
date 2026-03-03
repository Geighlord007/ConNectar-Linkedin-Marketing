@echo off
chcp 65001 >nul
echo ========================================
echo LinkedIn营销系统 - 快速启动
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python未安装或未添加到PATH
    echo 💡 请先安装Python 3.7+
    echo.
    pause
    exit /b 1
)

echo ✅ Python已安装

REM 检查项目文件
if not exist "main.py" (
    echo ❌ 未找到main.py文件
    echo 💡 请确保在项目根目录运行此脚本
    echo.
    pause
    exit /b 1
)

echo ✅ 项目文件检查通过

REM 检查依赖包
echo 🔍 检查依赖包...
python -c "import selenium, requests, pandas" >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️ 缺少必要依赖包
    echo 📦 正在安装依赖包...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ❌ 依赖包安装失败
        echo 💡 请手动运行: pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo ✅ 依赖包检查通过

REM 运行系统测试
echo 🧪 运行系统测试...
python test_system.py --quick >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️ 系统测试发现问题
    echo 🔧 运行详细测试以查看问题...
    python test_system.py
    echo.
    echo 是否继续启动系统？(y/n)
    set /p continue="请选择: "
    if /i not "%continue%"=="y" (
        echo 已取消启动
        pause
        exit /b 1
    )
)

echo ✅ 系统测试通过

REM 检查Chrome调试模式
echo 🌐 检查Chrome调试模式...
netstat -an | findstr :9222 >nul
if %errorlevel% neq 0 (
    echo ⚠️ Chrome调试模式未运行
    echo 🚀 正在启动Chrome调试模式...
    start "Chrome Debug" start_chrome_debug.bat
    echo ⏳ 等待Chrome启动...
    timeout /t 5 /nobreak >nul
    
    REM 再次检查
    netstat -an | findstr :9222 >nul
    if %errorlevel% neq 0 (
        echo ❌ Chrome调试模式启动失败
        echo 💡 请手动运行 start_chrome_debug.bat
        echo 💡 然后在Chrome中登录LinkedIn
        echo.
        pause
        exit /b 1
    )
)

echo ✅ Chrome调试模式运行中

echo.
echo 🎉 系统准备就绪！
echo.
echo 📋 启动选项:
echo 1. 交互式模式 (推荐新用户)
echo 2. 快速启动模式
echo 3. 运行系统测试
echo 4. 退出
echo.
set /p choice="请选择 (1-4): "

if "%choice%"=="1" (
    echo 🚀 启动交互式模式...
    python main.py
) else if "%choice%"=="2" (
    echo 🚀 快速启动模式...
    python main.py --quick-start
) else if "%choice%"=="3" (
    echo 🧪 运行系统测试...
    python test_system.py
) else if "%choice%"=="4" (
    echo 👋 再见！
    exit /b 0
) else (
    echo ❌ 无效选择，启动交互式模式...
    python main.py
)

echo.
echo 按任意键退出...
pause >nul