# 编码设置工具使用说明

## 问题描述
在Windows系统中运行LinkedIn营销系统时，可能会遇到中文字符显示为乱码的问题。这是由于终端编码设置不正确导致的。

## 解决方案

### 方法1：使用PowerShell脚本（推荐）
运行以下命令来设置UTF-8编码：
```powershell
powershell -ExecutionPolicy Bypass -File .\tools\scripts\Set-UTF8Encoding.ps1
```

### 方法2：使用批处理文件
双击运行：
```
.\tools\scripts\set_utf8_encoding.bat
```

### 方法3：手动设置
在PowerShell中依次执行以下命令：
```powershell
# 设置控制台代码页为UTF-8
chcp 65001

# 设置PowerShell编码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

# 设置Python环境变量
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
```

## 验证设置
运行以下命令验证编码设置是否成功：
```python
python -c "print('测试: 成功找到联系人 ✅'); print('测试: 多页爬取完成 🎉'); print('测试: 搜索结果摘要 📊')"
```

如果能正确显示中文字符和emoji，说明设置成功。

## 注意事项
- 每次打开新的PowerShell窗口时，可能需要重新运行编码设置脚本
- 建议在运行LinkedIn营销系统之前先运行编码设置脚本
- 如果仍然出现乱码，请检查系统区域设置是否正确