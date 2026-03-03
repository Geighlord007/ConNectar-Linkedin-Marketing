#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LinkedIn Voyager API 拦截测试
通过 Chrome DevTools Protocol (CDP) 拦截 LinkedIn 内部 API 响应，
验证能否直接获取结构化 JSON 数据来替代 HTML 解析。

前置条件:
  1. Chrome 以调试模式启动: chrome.exe --remote-debugging-port=9222
  2. 已在 Chrome 中登录 LinkedIn
  3. 已安装: pip install websocket-client requests

用法:
  python experiments/cdp_voyager_test.py
"""

import json
import time
import sys
import os
import base64
from datetime import datetime
from urllib.parse import quote_plus

try:
    import requests
except ImportError:
    print("缺少 requests: pip install requests")
    sys.exit(1)

try:
    import websocket
except ImportError:
    print("缺少 websocket-client: pip install websocket-client")
    sys.exit(1)


class VoyagerInterceptor:
    """通过 CDP Network 域拦截 LinkedIn Voyager API 响应"""

    def __init__(self, debug_port=9222):
        self.debug_port = debug_port
        self.ws = None
        self._msg_id = 0
        self.voyager_requests = {}      # request_id -> {url, status, body, ...}
        self._pending_bodies = {}       # msg_id -> request_id

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    def connect(self):
        """连接到 Chrome 调试端口并找到 LinkedIn 标签页"""
        try:
            resp = requests.get(
                f"http://localhost:{self.debug_port}/json", timeout=3
            )
            pages = resp.json()
        except Exception as e:
            print(f"[错误] 无法连接到 Chrome 调试端口 {self.debug_port}: {e}")
            print("       请确保 Chrome 以 --remote-debugging-port=9222 启动")
            return False

        ws_url = None
        for page in pages:
            url = page.get("url", "")
            if "linkedin.com" in url and page.get("type") == "page":
                ws_url = page.get("webSocketDebuggerUrl")
                print(f"[OK] 找到 LinkedIn 标签页: {url[:80]}")
                break

        if not ws_url:
            print("[错误] 未找到 LinkedIn 标签页，请在 Chrome 中打开 LinkedIn")
            return False

        self.ws = websocket.WebSocket()
        self.ws.connect(ws_url)
        self.ws.settimeout(0.5)
        print("[OK] WebSocket 已连接")
        return True

    # ------------------------------------------------------------------
    # CDP 通信
    # ------------------------------------------------------------------
    def _send(self, method, params=None):
        self._msg_id += 1
        self.ws.send(json.dumps({
            "id": self._msg_id,
            "method": method,
            "params": params or {},
        }))
        return self._msg_id

    def _recv_loop(self, timeout_sec):
        """持续接收 CDP 消息直到超时"""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                raw = self.ws.recv()
                data = json.loads(raw)
                self._on_cdp_message(data)
            except websocket.WebSocketTimeoutException:
                continue
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"[警告] 接收消息异常: {e}")
                break

    def _on_cdp_message(self, data):
        method = data.get("method", "")

        if method == "Network.responseReceived":
            resp_info = data["params"]["response"]
            url = resp_info["url"]
            request_id = data["params"]["requestId"]
            if "voyager" in url:
                self.voyager_requests[request_id] = {
                    "url": url,
                    "status": resp_info["status"],
                    "mime": resp_info.get("mimeType", ""),
                    "body": None,
                }

        elif method == "Network.loadingFinished":
            request_id = data["params"]["requestId"]
            if request_id in self.voyager_requests and self.voyager_requests[request_id]["body"] is None:
                mid = self._send("Network.getResponseBody", {"requestId": request_id})
                self._pending_bodies[mid] = request_id

        elif "id" in data and "result" in data:
            mid = data["id"]
            if mid in self._pending_bodies:
                request_id = self._pending_bodies.pop(mid)
                result = data["result"]
                body_str = result.get("body", "")
                if result.get("base64Encoded", False):
                    body_str = base64.b64decode(body_str).decode("utf-8", errors="replace")
                try:
                    self.voyager_requests[request_id]["body"] = json.loads(body_str)
                except (json.JSONDecodeError, TypeError):
                    self.voyager_requests[request_id]["body"] = body_str

    # ------------------------------------------------------------------
    # 高层操作
    # ------------------------------------------------------------------
    def enable_network(self):
        self._send("Network.enable")
        time.sleep(0.3)
        self._recv_loop(0.5)
        print("[OK] CDP Network 监控已启用")

    def navigate_to_search(self, keyword):
        encoded = quote_plus(keyword)
        url = (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords={encoded}&origin=SWITCH_SEARCH_VERTICAL"
        )
        self._send("Page.navigate", {"url": url})
        print(f"[OK] 正在导航到搜索页: {keyword}")

    def collect(self, timeout=15):
        """收集 Voyager 响应，包括自动拉取 body"""
        print(f"[..] 收集 Voyager API 响应（等待 {timeout} 秒）...")
        self._recv_loop(timeout)

        still_missing = [
            rid for rid, info in self.voyager_requests.items()
            if info["body"] is None and info["status"] == 200
        ]
        if still_missing:
            print(f"[..] 补充拉取 {len(still_missing)} 个响应 body...")
            for rid in still_missing:
                mid = self._send("Network.getResponseBody", {"requestId": rid})
                self._pending_bodies[mid] = rid
            self._recv_loop(5)

    # ------------------------------------------------------------------
    # 解析联系人
    # ------------------------------------------------------------------
    def parse_contacts(self):
        contacts = []
        for rid, info in self.voyager_requests.items():
            body = info.get("body")
            if not isinstance(body, dict):
                continue
            contacts.extend(self._extract_from_included(body))
            contacts.extend(self._extract_from_search_clusters(body))

        seen = set()
        unique = []
        for c in contacts:
            key = c.get("linkedin_url") or c.get("name")
            if key and key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    def _extract_from_included(self, body):
        """从 Voyager 响应的 included 数组提取 MiniProfile"""
        results = []
        for item in body.get("included", []):
            t = item.get("$type", "")
            if "MiniProfile" not in t and "Profile" not in t:
                continue
            first = item.get("firstName", "")
            last = item.get("lastName", "")
            name = f"{first} {last}".strip()
            if not name:
                continue
            pub_id = item.get("publicIdentifier", "")
            results.append({
                "name": name,
                "title": item.get("occupation", "") or item.get("headline", ""),
                "company": "",
                "location": item.get("locationName", ""),
                "linkedin_url": f"https://www.linkedin.com/in/{pub_id}" if pub_id else "",
                "_source": "included/MiniProfile",
            })
        return results

    def _extract_from_search_clusters(self, body):
        """从 searchDashClusters 结构提取 entityResult"""
        results = []
        data = body.get("data", {})
        for key, val in data.items():
            if not isinstance(val, dict):
                continue
            for element in val.get("elements", []):
                for item_wrap in element.get("items", []):
                    entity = (item_wrap.get("item", {}) or {}).get("entityResult")
                    if not entity:
                        continue
                    name = self._text(entity.get("title"))
                    subtitle = self._text(entity.get("primarySubtitle"))
                    location = self._text(entity.get("secondarySubtitle"))
                    nav_url = entity.get("navigationUrl", "")

                    title, company = self._split_subtitle(subtitle)
                    if name:
                        results.append({
                            "name": name,
                            "title": title,
                            "company": company,
                            "location": location,
                            "linkedin_url": nav_url.split("?")[0] if nav_url else "",
                            "_source": "searchClusters/entityResult",
                        })
        return results

    @staticmethod
    def _text(obj):
        if isinstance(obj, dict):
            return obj.get("text", "")
        return str(obj) if obj else ""

    @staticmethod
    def _split_subtitle(subtitle):
        for sep in (" at ", " @ ", " | "):
            if sep in subtitle:
                parts = subtitle.split(sep, 1)
                return parts[0].strip(), parts[1].strip()
        return subtitle, ""

    # ------------------------------------------------------------------
    def close(self):
        if self.ws:
            try:
                self._send("Network.disable")
            except Exception:
                pass
            self.ws.close()


def save_results(interceptor, keyword):
    """保存原始响应和解析结果"""
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    raw_path = os.path.join(out_dir, f"voyager_raw_{keyword}_{ts}.json")
    save_data = {}
    for rid, info in interceptor.voyager_requests.items():
        save_data[rid] = {
            "url": info["url"],
            "status": info["status"],
            "has_body": info.get("body") is not None,
            "body": info.get("body"),
        }
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"\n[保存] 原始 Voyager 响应 → {raw_path}")

    contacts = interceptor.parse_contacts()
    if contacts:
        contacts_path = os.path.join(out_dir, f"contacts_{keyword}_{ts}.json")
        with open(contacts_path, "w", encoding="utf-8") as f:
            json.dump(contacts, f, ensure_ascii=False, indent=2)
        print(f"[保存] 解析联系人 ({len(contacts)} 人) → {contacts_path}")
    return contacts


def main():
    print("=" * 60)
    print("  LinkedIn Voyager API 拦截测试")
    print("  通过 CDP 直接获取 JSON，替代 HTML 解析")
    print("=" * 60)

    keyword = input("\n请输入搜索关键词 (直接回车默认 'software engineer'): ").strip()
    if not keyword:
        keyword = "software engineer"

    interceptor = VoyagerInterceptor(debug_port=9222)

    if not interceptor.connect():
        return

    interceptor.enable_network()
    interceptor.navigate_to_search(keyword)
    interceptor.collect(timeout=15)

    # 汇总
    print(f"\n{'=' * 60}")
    print(f"捕获到 {len(interceptor.voyager_requests)} 个 Voyager API 请求:")
    for rid, info in interceptor.voyager_requests.items():
        tag = "✅" if info.get("body") else "❌"
        short_url = info["url"]
        if len(short_url) > 100:
            short_url = short_url[:97] + "..."
        print(f"  {tag} [{info['status']}] {short_url}")

    contacts = save_results(interceptor, keyword.replace(" ", "_"))

    if contacts:
        print(f"\n{'=' * 60}")
        print(f"成功从 API JSON 中提取 {len(contacts)} 个联系人:\n")
        for i, c in enumerate(contacts[:15], 1):
            print(f"  {i:>2}. {c['name']}")
            if c["title"]:
                print(f"      职位: {c['title']}")
            if c["company"]:
                print(f"      公司: {c['company']}")
            if c["location"]:
                print(f"      地点: {c['location']}")
            if c["linkedin_url"]:
                print(f"      URL:  {c['linkedin_url']}")
            print()
        if len(contacts) > 15:
            print(f"  ... 还有 {len(contacts) - 15} 个联系人")
    else:
        print("\n[!] 未能提取到联系人")
        print("    请查看 experiments/output/ 下的原始响应文件，分析 JSON 结构")

    interceptor.close()
    print("\n测试完成。")


if __name__ == "__main__":
    main()
