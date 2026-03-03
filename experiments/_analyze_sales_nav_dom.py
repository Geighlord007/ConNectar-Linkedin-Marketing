"""
分析 Sales Navigator 类页面的 DOM 结构
提取关键元素选择器
"""
import json
import requests
import websocket
import time
import os

def get_websocket_url(debug_port=9222):
    """获取 LinkedIn 页面的 WebSocket URL"""
    resp = requests.get(f"http://localhost:{debug_port}/json")
    pages = resp.json()

    for p in pages:
        url = p.get('url', '')
        if 'linkedin.com/in/' in url and p.get('type') == 'page':
            return p.get('webSocketDebuggerUrl'), p.get('url'), p.get('title')
    return None, None, None

# 分析 DOM 的 JS 脚本
ANALYZE_DOM_JS = r"""
return (() => {
    const result = {
        url: location.href,
        title: document.title,

        // 检测页面类型
        isSalesNav: location.href.includes('sales.'),
        hasSalesNavBanner: !!document.querySelector('[class*="sales-nav"], [data-test-sales-nav]'),

        // 分析 h1 (profile name)
        h1: null,

        // 分析所有可能的操作按钮
        actionButtons: [],

        // 分析 More 菜单
        moreButton: null,
        dropdownMenus: [],

        // 分析弹窗
        dialogs: []
    };

    // h1 信息
    const h1 = document.querySelector('h1');
    if (h1) {
        result.h1 = {
            text: h1.textContent.trim(),
            className: h1.className
        };
    }

    // 查找所有可能的操作按钮区域
    const actionAreas = document.querySelectorAll('.pv-top-card, .scaffold-layout__main, header, [class*="profile-card"]');
    actionAreas.forEach((area, idx) => {
        const buttons = area.querySelectorAll('button');
        buttons.forEach(btn => {
            const rect = btn.getBoundingClientRect();
            if (rect.height > 0 && rect.width > 0) {
                result.actionButtons.push({
                    text: btn.textContent.trim().substring(0, 40),
                    ariaLabel: (btn.getAttribute('aria-label') || '').substring(0, 80),
                    id: btn.id || null,
                    className: (btn.className || '').substring(0, 50),
                    disabled: btn.disabled,
                    inTopCard: !!btn.closest('.pv-top-card'),
                    inHeader: !!btn.closest('header'),
                    rect: { top: Math.round(rect.top), left: Math.round(rect.left), width: Math.round(rect.width), height: Math.round(rect.height) }
                });
            }
        });
    });

    // More 按钮
    const moreBtns = document.querySelectorAll('button[aria-label="More actions"], button[aria-label="More"]');
    moreBtns.forEach(btn => {
        const rect = btn.getBoundingClientRect();
        if (rect.height > 0) {
            result.moreButton = result.moreButton || [];
            result.moreButton.push({
                ariaLabel: btn.getAttribute('aria-label'),
                id: btn.id || null,
                className: (btn.className || '').substring(0, 50),
                rect: { top: Math.round(rect.top), left: Math.round(rect.left) },
                hasOverflow: btn.id && btn.id.includes('overflow'),
                hasProfile: btn.id && btn.id.includes('profile')
            });
        }
    });

    // 下拉菜单
    const menus = document.querySelectorAll('.artdeco-dropdown__content-inner, [role="menu"], .artdeco-dropdown');
    menus.forEach(menu => {
        const rect = menu.getBoundingClientRect();
        if (rect.height > 5) {
            const items = [];
            menu.querySelectorAll('[role="menuitem"], button, li, div[role="button"]').forEach(item => {
                items.push(item.textContent.trim().substring(0, 30));
            });
            result.dropdownMenus.push({
                className: (menu.className || '').substring(0, 50),
                rect: { top: Math.round(rect.top), height: Math.round(rect.height) },
                items: items.slice(0, 10)
            });
        }
    });

    // 弹窗/对话框
    const dialogs = document.querySelectorAll('[role="dialog"], .artdeco-modal, [class*="modal"], [class*="invite"]');
    dialogs.forEach(dialog => {
        const rect = dialog.getBoundingClientRect();
        if (rect.height > 50 && rect.width > 100) {
            const buttons = [];
            dialog.querySelectorAll('button').forEach(btn => {
                buttons.push({
                    text: btn.textContent.trim().substring(0, 40),
                    ariaLabel: (btn.getAttribute('aria-label') || '').substring(0, 60),
                    disabled: btn.disabled
                });
            });
            const inputs = [];
            dialog.querySelectorAll('textarea, [contenteditable="true"], input[type="text"]').forEach(inp => {
                inputs.push({
                    tag: inp.tagName,
                    type: inp.type || 'editable',
                    placeholder: inp.getAttribute('placeholder') || inp.getAttribute('data-placeholder') || '',
                    name: inp.name || ''
                });
            });
            result.dialogs.push({
                className: (dialog.className || '').substring(0, 80),
                rect: { top: Math.round(rect.top), width: Math.round(rect.width), height: Math.round(rect.height) },
                buttons: buttons,
                inputs: inputs
            });
        }
    });

    return result;
})();
"""

def analyze_page(ws_url, page_url, title):
    """连接到页面并分析 DOM"""
    ws = websocket.WebSocket()
    ws.connect(ws_url)
    ws.settimeout(5)

    # 发送命令
    msg_id = 1
    ws.send(json.dumps({"id": msg_id, "method": "Runtime.enable"}))
    time.sleep(0.2)

    # 执行 JS
    msg_id += 1
    ws.send(json.dumps({
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {"expression": ANALYZE_DOM_JS, "returnByValue": True}
    }))

    # 接收结果
    result = None
    deadline = time.time() + 3
    while time.time() < deadline:
        try:
            raw = ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg_id:
                result = data.get("result", {}).get("result", {}).get("value")
                break
        except:
            continue

    ws.close()
    return result

def main():
    print("=" * 70)
    print("  分析 Sales Navigator 类页面的 DOM 结构")
    print("=" * 70)

    # 获取所有 LinkedIn 页面
    resp = requests.get("http://localhost:9222/json")
    pages = resp.json()

    results = []
    for p in pages:
        url = p.get('url', '')
        if 'linkedin.com/in/' in url and p.get('type') == 'page':
            ws_url = p.get('webSocketDebuggerUrl')
            page_url = p.get('url')
            title = p.get('title', '')

            print(f"\n分析页面: {title}")
            print(f"URL: {page_url[:80]}")

            if ws_url:
                result = analyze_page(ws_url, page_url, title)
                if result:
                    results.append(result)

                    # 打印关键信息
                    print(f"\n  H1 (Profile Name): {result.get('h1', {}).get('text', 'N/A')}")

                    isSalesNav = result.get('isSalesNav') or result.get('hasSalesNavBanner')
                    print(f"  Sales Navigator: {'是' if isSalesNav else '否'}")

                    # 分析按钮
                    print(f"\n  操作按钮 ({len(result.get('actionButtons', []))} 个):")
                    for btn in result.get('actionButtons', [])[:15]:
                        text = btn.get('text', '')[:20]
                        label = btn.get('ariaLabel', '')[:30]
                        inTop = btn.get('inTopCard', False)
                        print(f"    - '{text}' | aria-label: '{label}' | inTopCard: {inTop}")

                    # More 按钮
                    if result.get('moreButton'):
                        print(f"\n  More 按钮:")
                        for mb in result.get('moreButton'):
                            print(f"    - id: {mb.get('id')} | aria-label: {mb.get('ariaLabel')}")

                    # 弹窗
                    if result.get('dialogs'):
                        print(f"\n  弹窗 ({len(result.get('dialogs'))} 个):")
                        for dlg in result.get('dialogs'):
                            print(f"    - class: {dlg.get('className', '')[:50]}")
                            print(f"      按钮: {[b['text'][:20] for b in dlg.get('buttons', [])]}")
                            print(f"      输入框: {dlg.get('inputs', [])}")

    # 保存结果
    out_dir = os.path.join(os.path.dirname(__file__), 'output')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'dom_analysis_sales_nav.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n\n完整结果已保存: {out_path}")

if __name__ == "__main__":
    main()