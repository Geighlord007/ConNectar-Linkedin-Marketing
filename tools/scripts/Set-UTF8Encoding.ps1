# LinkedIn Marketing System - UTF-8 Encoding Setup
# This script sets up proper UTF-8 encoding for Chinese character display

Write-Host "Setting up UTF-8 encoding for LinkedIn Marketing System..." -ForegroundColor Cyan

# Set console code page to UTF-8
chcp 65001 | Out-Null

# Set PowerShell encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

# Set Python environment variables
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "✓ UTF-8 encoding setup completed successfully!" -ForegroundColor Green
Write-Host "✓ Chinese characters should now display correctly" -ForegroundColor Green
Write-Host "✓ Ready to run LinkedIn Marketing System" -ForegroundColor Green

# Test display
Write-Host "`nTesting character display:" -ForegroundColor Yellow
python -c "print('  测试: 成功找到联系人 ✅'); print('  测试: 多页爬取完成 🎉'); print('  测试: 搜索结果摘要 📊')"