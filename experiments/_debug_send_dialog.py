"""
调试：在 Add a note 填写完成后，导出弹窗内所有按钮信息，定位 Send 按钮
"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# 连接 Chrome
opts = Options()
opts.add_experimental_option("debuggerAddress", "localhost:9222")
driver = webdriver.Chrome(options=opts)

# 执行到 Add a note 填写后，导出按钮
DUMP_BUTTONS_JS = r"""
return (() => {
    const buttons = [];
    for (const btn of document.querySelectorAll('button')) {
        const rect = btn.getBoundingClientRect();
        const txt = (btn.textContent || '').trim();
        const label = btn.getAttribute('aria-label') || '';
        if (rect.width > 0 && rect.height > 0) {
            buttons.push({
                text: txt.substring(0, 50),
                ariaLabel: label.substring(0, 80),
                disabled: btn.disabled,
                top: Math.round(rect.top),
                left: Math.round(rect.left),
                inDialog: !!btn.closest('[role="dialog"], .artdeco-modal'),
                inForm: !!btn.closest('form'),
                tagName: btn.tagName,
                className: (btn.className || '').substring(0, 60)
            });
        }
    }
    return buttons;
})();
"""

# 手动导航到可 Connect 的页面，然后运行此脚本
# 用户需先：1) 打开 profile 2) 点 Connect 3) 点 Add a note 4) 填写消息
print("请手动：打开一个可 Connect 的个人主页，点击 Connect -> Add a note -> 填写消息")
print("完成后按 Enter 继续...")
input()

result = driver.execute_script(DUMP_BUTTONS_JS)
out = os.path.join(os.path.dirname(__file__), 'output', 'send_dialog_buttons.json')
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\n共 {len(result)} 个按钮，已保存到 {out}")
print("\n弹窗内按钮（Send 相关）:")
for b in result:
    if b['inDialog'] or ('send' in (b['text'] + b['ariaLabel']).lower()):
        print(f"  text={b['text'][:40]!r} label={b['ariaLabel'][:40]!r} disabled={b['disabled']} top={b['top']}")
