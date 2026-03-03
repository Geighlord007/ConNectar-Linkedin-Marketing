@echo off
REM 设置控制台代码页为UTF-8
chcp 65001 >nul

REM 设置环境变量
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo UTF-8编码设置完成
echo 当前代码页: 
chcp