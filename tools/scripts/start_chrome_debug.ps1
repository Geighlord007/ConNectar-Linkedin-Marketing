# LinkedIn营销系统 - Chrome调试模式启动器 (PowerShell版本)
# 使用方法: 在PowerShell中运行此脚本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "LinkedIn营销系统 - Chrome调试模式启动器" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$DEBUG_PORT = 9222
$USER_DATA_DIR = "$env:USERPROFILE\AppData\Local\Google\Chrome\User Data\LinkedIn"

# 检查Chrome是否已在调试模式运行
Write-Host "检查Chrome调试模式状态..." -ForegroundColor Yellow
$portCheck = netstat -an | findstr ":$DEBUG_PORT"
if ($portCheck) {
    Write-Host "Chrome调试模式已在运行 (端口: $DEBUG_PORT)" -ForegroundColor Yellow
    Write-Host "如需重启，请先关闭所有Chrome窗口" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "按Enter键退出"
    exit
}

# 查找Chrome可执行文件
Write-Host "正在查找Chrome安装路径..." -ForegroundColor Yellow
$chromePaths = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

$chromePath = ""
foreach ($path in $chromePaths) {
    Write-Host "检查路径: $path" -ForegroundColor Gray
    if (Test-Path $path) {
        $chromePath = $path
        Write-Host "找到Chrome: $chromePath" -ForegroundColor Green
        break
    }
}

if ([string]::IsNullOrEmpty($chromePath)) {
    Write-Host "未找到Chrome安装路径" -ForegroundColor Red
    Write-Host "请确保已安装Google Chrome浏览器" -ForegroundColor Yellow
    Read-Host "按Enter键退出"
    exit 1
}

Write-Host "找到Chrome: $chromePath" -ForegroundColor Green
Write-Host ""

# 创建用户数据目录
if (-not (Test-Path $USER_DATA_DIR)) {
    Write-Host "创建Chrome用户数据目录..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $USER_DATA_DIR -Force | Out-Null
}

# 启动Chrome调试模式
Write-Host "启动Chrome调试模式..." -ForegroundColor Green
Write-Host "调试端口: $DEBUG_PORT" -ForegroundColor Cyan
Write-Host "用户数据目录: $USER_DATA_DIR" -ForegroundColor Cyan
Write-Host ""

$arguments = @(
    "--remote-debugging-port=$DEBUG_PORT",
    "--user-data-dir=$USER_DATA_DIR",
    "--disable-web-security",
    "--disable-features=VizDisplayCompositor",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-default-apps",
    "--disable-popup-blocking",
    "--disable-translate",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-ipc-flooding-protection",
    "--window-size=1200,800",
    "--window-position=100,100"
)

try {
    Write-Host "启动Chrome调试模式..." -ForegroundColor Yellow
    Write-Host "Chrome路径: $chromePath" -ForegroundColor Gray
    Write-Host "调试端口: $DEBUG_PORT" -ForegroundColor Gray
    
    if ([string]::IsNullOrEmpty($chromePath)) {
        throw "Chrome路径为空，无法启动"
    }
    
    Start-Process -FilePath $chromePath -ArgumentList $arguments -PassThru
    
    # 等待Chrome启动
    Write-Host "等待Chrome启动..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    
    # 检查Chrome是否成功启动
    $portCheck = netstat -an | findstr ":$DEBUG_PORT"
    if ($portCheck) {
        Write-Host "Chrome调试模式启动成功！" -ForegroundColor Green
        Write-Host ""
        Write-Host "下一步操作:" -ForegroundColor Cyan
        Write-Host "1. 在Chrome中访问 https://www.linkedin.com" -ForegroundColor White
        Write-Host "2. 登录您的LinkedIn账户" -ForegroundColor White
        Write-Host "3. 运行LinkedIn营销系统: python main.py" -ForegroundColor White
        Write-Host ""
        Write-Host "调试地址: http://localhost:$DEBUG_PORT" -ForegroundColor Cyan
        Write-Host "Chrome已在后台运行，可以关闭此窗口" -ForegroundColor Yellow
    } else {
        Write-Host "Chrome调试模式启动失败" -ForegroundColor Red
        Write-Host "请检查端口 $DEBUG_PORT 是否被占用" -ForegroundColor Yellow
    }
} catch {
    Write-Host "启动Chrome时发生错误: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Read-Host "按Enter键退出"
