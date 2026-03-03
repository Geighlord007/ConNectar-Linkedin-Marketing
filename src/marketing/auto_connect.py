#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LinkedIn 自动连接模块 — 打开个人主页 → 点 Connect → Add a note → 填写消息 → Send

通过 Selenium execute_script 操作 DOM，处理以下场景：
1. Connect 按钮在主操作区直接可见
2. Connect 藏在 "More" 下拉菜单中
3. 已经是好友（Message 按钮可见）
4. 已发送待处理（Pending）
5. 只有 Follow（无法 Connect）
"""

import time
import logging
import re
from typing import List, Dict, Any, Optional

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 检测当前页面的连接状态
# ---------------------------------------------------------------------------
CHECK_STATUS_JS = r"""
return (() => {
    const result = {
        status: 'unknown',  // 'can_connect' | 'already_connected' | 'pending' | 'follow_only' | 'unknown'
        profile_name: '',
        connect_method: null,  // 'direct_button' | 'more_menu' | null
    };

    // 获取 profile name
    const h1 = document.querySelector('h1');
    if (h1) result.profile_name = h1.textContent.trim();

    // 检查是否已连接（有 Message 主按钮）
    const msgBtns = document.querySelectorAll('button');
    for (const btn of msgBtns) {
        const lbl = (btn.getAttribute('aria-label') || '').toLowerCase();
        const txt = btn.textContent.trim().toLowerCase();
        if ((txt === 'message' || lbl.includes('message')) && lbl.includes(result.profile_name.split(' ')[0].toLowerCase())) {
            result.status = 'already_connected';
            return result;
        }
    }

    // 检查 Pending
    for (const btn of msgBtns) {
        if (/^pending$/i.test(btn.textContent.trim())) {
            result.status = 'pending';
            return result;
        }
    }

    // 检查直接的 Connect 按钮（aria-label 中包含 profile name 的首名）
    const firstName = result.profile_name.split(' ')[0];
    for (const btn of msgBtns) {
        const lbl = (btn.getAttribute('aria-label') || '');
        if (/connect/i.test(lbl) && lbl.includes(firstName)) {
            result.status = 'can_connect';
            result.connect_method = 'direct_button';
            return result;
        }
    }

    // 直接文本匹配: 主操作区域的 Connect 按钮
    const topSection = document.querySelector('.pv-top-card, .scaffold-layout__main');
    if (topSection) {
        for (const btn of topSection.querySelectorAll('button')) {
            if (/^Connect$/i.test(btn.textContent.trim()) && !btn.disabled) {
                result.status = 'can_connect';
                result.connect_method = 'direct_button';
                return result;
            }
        }
    }

    // 检查 More 菜单中是否有 Connect
    result.status = 'check_more_menu';
    result.connect_method = 'more_menu';
    return result;
})()
"""

# ---------------------------------------------------------------------------
# 点击 Connect 按钮（直接按钮）
# ---------------------------------------------------------------------------
CLICK_CONNECT_DIRECT_JS = r"""
return (() => {
    const h1 = document.querySelector('h1');
    const profileName = h1 ? h1.textContent.trim() : '';
    const firstName = profileName.split(' ')[0];

    // 优先找 aria-label 包含 profile name 的 Connect 按钮
    const buttons = document.querySelectorAll('button');
    for (const btn of buttons) {
        const lbl = (btn.getAttribute('aria-label') || '');
        if (/connect/i.test(lbl) && lbl.includes(firstName)) {
            btn.click();
            return { clicked: true, method: 'aria-label match' };
        }
    }

    // 回退: 主区域内的 Connect 按钮
    const topSection = document.querySelector('.pv-top-card, .scaffold-layout__main');
    if (topSection) {
        for (const btn of topSection.querySelectorAll('button')) {
            if (/^Connect$/i.test(btn.textContent.trim()) && !btn.disabled) {
                btn.click();
                return { clicked: true, method: 'text match in top section' };
            }
        }
    }
    return { clicked: false };
})()
"""

# ---------------------------------------------------------------------------
# 打开 More 菜单并点击 Connect
# ---------------------------------------------------------------------------
CLICK_CONNECT_MORE_JS = r"""
return (() => {
    // 1. 主 profile 的 More 按钮：id 含 profile-overflow-action（主操作区）
    let moreBtn = document.querySelector('button[id*="profile-overflow-action"][aria-label="More actions"]');
    if (!moreBtn) {
        moreBtn = document.querySelector('button[aria-label="More actions"][id*="profile"]');
    }
    // 2. 主卡片区域内的 More（.pv-top-card 或 header 附近）
    if (!moreBtn) {
        const profileCard = document.querySelector('.pv-top-card, .pv-top-card-v2, [class*="profile-card"]');
        if (profileCard) {
            moreBtn = profileCard.querySelector('button[aria-label="More actions"]');
        }
    }
    // 3. 回退：主视区内的 aria-label="More actions"
    if (!moreBtn) {
        for (const btn of document.querySelectorAll('button[aria-label="More actions"]')) {
            const rect = btn.getBoundingClientRect();
            if (rect.top > 0 && rect.top < 500) { moreBtn = btn; break; }
        }
    }
    // 4. 文本为 More 的按钮（主区域）
    if (!moreBtn) {
        const topSection = document.querySelector('.pv-top-card, .scaffold-layout__main');
        for (const btn of (topSection || document).querySelectorAll('button')) {
            if (/^More$/i.test(btn.textContent.trim()) && !btn.disabled) {
                const rect = btn.getBoundingClientRect();
                if (rect.top > 0 && rect.top < 600) { moreBtn = btn; break; }
            }
        }
    }
    if (!moreBtn) return { clicked: false, reason: 'no More button found' };
    moreBtn.click();
    return { clicked: true, step: 'more_opened' };
})()
"""

CLICK_CONNECT_IN_MENU_JS = r"""
return (() => {
    // 优先在可见的下拉菜单中找 Connect（避免点到侧边推荐人）
    const menus = document.querySelectorAll('.artdeco-dropdown__content-inner, [role="menu"], .artdeco-dropdown');
    for (const menu of menus) {
        const rect = menu.getBoundingClientRect();
        if (rect.height < 5) continue;  // 隐藏的菜单
        for (const item of menu.querySelectorAll('[role="menuitem"], .artdeco-dropdown__item, li, button, div[role="button"]')) {
            const text = (item.textContent || '').trim();
            if (/^Connect$/i.test(text) || /^Invite.*connect$/i.test(text) || (text === 'Connect' && text.length < 25)) {
                item.click();
                return { clicked: true, text: text };
            }
        }
    }
    // 回退：任意包含 Connect 的菜单项
    for (const item of document.querySelectorAll('[role="menuitem"], .artdeco-dropdown__item')) {
        if (/^Connect$/i.test(item.textContent.trim())) {
            item.click();
            return { clicked: true, text: item.textContent.trim() };
        }
    }
    return { clicked: false, reason: 'Connect not in More menu' };
})()
"""

# ---------------------------------------------------------------------------
# 处理 "Add a note"（仅在弹窗内查找）
# ---------------------------------------------------------------------------
CLICK_ADD_NOTE_JS = r"""
return (() => {
    const modal = document.querySelector('[role="dialog"], .artdeco-modal, [class*="invite"], [class*="modal"]') || document;
    for (const btn of modal.querySelectorAll('button, [role="button"]')) {
        const text = (btn.textContent || '').trim();
        if (/^Add a note$/i.test(text)) {
            const rect = btn.getBoundingClientRect();
            if (rect.width > 0) { btn.click(); return { clicked: true }; }
        }
    }
    for (const btn of modal.querySelectorAll('*')) {
        const text = (btn.textContent || '').trim();
        if (text === 'Add a note' && (btn.tagName === 'SPAN' || btn.tagName === 'DIV')) {
            const parent = btn.closest('button, [role="button"], [role="menuitem"]') || btn.parentElement;
            if (parent && parent.click) { parent.click(); return { clicked: true }; }
        }
    }
    return { clicked: false };
})()
"""

# ---------------------------------------------------------------------------
# 在弹窗内的输入框中填写消息（必须点击 Add a note 后输入框才会出现）
# ---------------------------------------------------------------------------
FILL_MESSAGE_JS = r"""
return ((message) => {
    const modal = document.querySelector('[role="dialog"], .artdeco-modal, [class*="send-invite"], [class*="invite"], [class*="modal"]') || document;
    const scope = modal;

    // 1. 弹窗内的 textarea
    for (const ta of scope.querySelectorAll('textarea')) {
        const rect = ta.getBoundingClientRect();
        if (rect.width > 50 && rect.height > 20 && rect.top > 0) {
            ta.focus();
            ta.value = '';
            const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
            if (setter) setter.call(ta, message); else ta.value = message;
            ta.dispatchEvent(new Event('input', { bubbles: true }));
            ta.dispatchEvent(new Event('change', { bubbles: true }));
            ta.dispatchEvent(new Event('blur', { bubbles: true }));
            return { success: true, type: 'textarea', len: message.length };
        }
    }

    // 2. 弹窗内的 contenteditable（LinkedIn 连接请求弹窗常用）
    for (const el of scope.querySelectorAll('[contenteditable="true"]')) {
        const rect = el.getBoundingClientRect();
        const ph = (el.getAttribute('data-placeholder') || el.getAttribute('placeholder') || '').toLowerCase();
        const isNoteInput = ph.includes('note') || ph.includes('message') || rect.height > 25;
        if (rect.width > 50 && rect.height > 15 && rect.top > 0 && rect.top < 500 && isNoteInput) {
            el.focus();
            if (document.execCommand) {
                document.execCommand('selectAll', false);
                document.execCommand('insertText', false, message);
            } else {
                el.textContent = message;
                el.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
            }
            return { success: true, type: 'contenteditable', len: (el.textContent || '').length };
        }
    }

    // 3. 弹窗内任意 contenteditable
    for (const el of scope.querySelectorAll('[contenteditable="true"]')) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 40 && rect.height > 15 && rect.top > 0 && rect.top < 600) {
            el.focus();
            document.execCommand && document.execCommand('selectAll', false);
            document.execCommand ? document.execCommand('insertText', false, message) : (el.textContent = message);
            return { success: true, type: 'contenteditable_fallback', len: (el.textContent || '').length };
        }
    }
    // 4. 全局回退：任何在视区上部的输入（弹窗选择器可能不匹配）
    for (const ta of document.querySelectorAll('textarea')) {
        const rect = ta.getBoundingClientRect();
        if (rect.top > 0 && rect.top < 500 && rect.width > 50) {
            ta.focus();
            const s = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
            if (s) s.call(ta, message); else ta.value = message;
            ta.dispatchEvent(new Event('input', { bubbles: true }));
            return { success: true, type: 'textarea_fallback', len: message.length };
        }
    }
    for (const el of document.querySelectorAll('[contenteditable="true"]')) {
        const rect = el.getBoundingClientRect();
        if (rect.top > 0 && rect.top < 500 && rect.width > 80 && rect.height > 25) {
            el.focus();
            document.execCommand ? document.execCommand('insertText', false, message) : (el.textContent = message);
            return { success: true, type: 'contenteditable_global', len: (el.textContent || '').length };
        }
    }
    return { success: false, reason: 'no input found' };
})(arguments[0])
"""

CLICK_SEND_JS = r"""
return (() => {
    // 1. 优先：aria-label="Send invitation"（LinkedIn 连接请求弹窗的 Send）
    for (const btn of document.querySelectorAll('button[aria-label*="Send invitation"], button[aria-label*="send invitation"]')) {
        if (!btn.disabled) { btn.click(); return { sent: true, method: 'aria-label' }; }
    }
    // 2. 弹窗内的 Send 按钮（文本或 label）
    const modal = document.querySelector('[role="dialog"], .artdeco-modal, [class*="modal"]');
    if (modal) {
        for (const btn of modal.querySelectorAll('button')) {
            const text = (btn.textContent || '').trim();
            const label = (btn.getAttribute('aria-label') || '').toLowerCase();
            if ((/^Send( now)?$/i.test(text) || label.includes('send')) && !btn.disabled) {
                const rect = btn.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) { btn.click(); return { sent: true, method: 'modal' }; }
            }
        }
    }
    // 3. 任何 visible 且在视区上部的 Send
    for (const btn of document.querySelectorAll('button')) {
        const text = (btn.textContent || '').trim();
        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
        if ((/^Send$/i.test(text) || label.includes('send invitation')) && !btn.disabled) {
            const rect = btn.getBoundingClientRect();
            if (rect.top >= 0 && rect.top < 900) { btn.click(); return { sent: true, method: 'fallback' }; }
        }
    }
    return { sent: false };
})()
"""

GET_PAGE_MODE_JS = r"""
return (() => {
    const url = location.href || '';
    const text = (document.body?.innerText || '').toLowerCase();
    const hasSalesSignals =
        url.includes('/sales/') ||
        !!document.querySelector('[data-test-sales-nav], [data-control-name*="sales"], [class*="sales-nav"], [class*="lead-page"]') ||
        text.includes('sales navigator');
    return {
        mode: hasSalesSignals ? 'sales_navigator' : 'standard_profile',
        url
    };
})()
"""

CHECK_ACTION_STATE_JS = r"""
return (() => {
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const lower = (s) => norm(s).toLowerCase();
    const profileName = norm(document.querySelector('h1')?.textContent || '');
    const firstName = profileName ? profileName.split(' ')[0].toLowerCase() : '';

    const candidates = [];
    const roots = Array.from(document.querySelectorAll(
        '.pv-top-card, .pv-top-card-v2, .ph5, .scaffold-layout__main, header, [class*="profile-topcard"], [class*="lead-actions"], [class*="top-card"]'
    ));
    if (roots.length === 0) roots.push(document.body);

    const seen = new Set();
    for (const root of roots) {
        for (const btn of root.querySelectorAll('button, [role="button"]')) {
            const el = btn.closest('button, [role="button"]') || btn;
            if (seen.has(el)) continue;
            seen.add(el);
            const rect = el.getBoundingClientRect();
            if (rect.width < 24 || rect.height < 18) continue;
            if (rect.top < -2 || rect.top > 760) continue;
            const text = norm(el.textContent || '');
            const aria = norm(el.getAttribute('aria-label') || '');
            if (!text && !aria) continue;
            const all = `${text} ${aria}`.toLowerCase();
            candidates.push({
                text,
                aria,
                all,
                disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
                top: Math.round(rect.top),
                left: Math.round(rect.left)
            });
        }
    }

    const hasPending = candidates.some(x => /^pending$/i.test(x.text) || x.all.includes('invitation pending'));
    const hasMessage = candidates.some(x => /^message$/i.test(x.text) || x.all.includes('message'));
    const hasConnect = candidates.some(x =>
        !x.disabled && (
            /^connect$/i.test(x.text) ||
            /^连接$/i.test(x.text) ||
            x.all.includes(' connect ') ||
            x.all.startsWith('connect ') ||
            x.all.includes('连接') ||
            x.all.includes('invite') ||
            x.all.includes('add to your network')
        )
    );
    const hasMore = candidates.some(x =>
        !x.disabled && (
            /^more$/i.test(x.text) ||
            /^更多$/i.test(x.text) ||
            x.all.includes('more actions') ||
            x.all.includes('更多')
        )
    );

    let status = 'unknown';
    if (hasPending) status = 'pending';
    else if (!hasConnect && hasMessage) status = 'already_connected';
    else if (hasConnect || hasMore) status = 'can_connect';

    return {
        status,
        profile_name: profileName,
        first_name: firstName,
        has_connect: hasConnect,
        has_more: hasMore,
        candidates: candidates.slice(0, 60)
    };
})()
"""

CLICK_CONNECT_SMART_JS = r"""
return (() => {
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const inTop = (el) => {
        const r = el.getBoundingClientRect();
        return r.width > 24 && r.height > 18 && r.top > -2 && r.top < 760;
    };
    const score = (el) => {
        const t = norm(el.textContent || '').toLowerCase();
        const a = norm(el.getAttribute('aria-label') || '').toLowerCase();
        const all = `${t} ${a}`;
        let s = 0;
        if (/^connect$/.test(t) || /^连接$/.test(t)) s += 120;
        if (all.includes('connect')) s += 80;
        if (all.includes('连接')) s += 80;
        if (all.includes('invite')) s += 40;
        if (all.includes('follow')) s -= 120;
        if (all.includes('message')) s -= 120;
        if (el.disabled || el.getAttribute('aria-disabled') === 'true') s -= 500;
        const r = el.getBoundingClientRect();
        if (r.top < 260) s += 20;
        return s;
    };

    const list = [];
    for (const el of document.querySelectorAll('button, [role="button"]')) {
        const btn = el.closest('button, [role="button"]') || el;
        if (!inTop(btn)) continue;
        const s = score(btn);
        if (s > 50) list.push({ el: btn, score: s, text: norm(btn.textContent || ''), aria: norm(btn.getAttribute('aria-label') || '') });
    }
    list.sort((a, b) => b.score - a.score);
    if (list.length) {
        list[0].el.click();
        return { clicked: true, method: 'smart_direct', text: list[0].text, aria: list[0].aria, score: list[0].score };
    }
    return { clicked: false, reason: 'no direct connect candidate' };
})()
"""

CLICK_MORE_SMART_JS = r"""
return (() => {
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const score = (el) => {
        const t = norm(el.textContent || '').toLowerCase();
        const a = norm(el.getAttribute('aria-label') || '').toLowerCase();
        const all = `${t} ${a}`;
        let s = 0;
        if (/^more$/.test(t) || /^更多$/.test(t)) s += 120;
        if (all.includes('more actions')) s += 120;
        if (all.includes('更多')) s += 120;
        if (all.includes('more')) s += 30;
        if (all.includes('message') || all.includes('follow') || all.includes('connect')) s -= 80;
        if (el.disabled || el.getAttribute('aria-disabled') === 'true') s -= 500;
        const r = el.getBoundingClientRect();
        if (r.top < 280) s += 20;
        return s;
    };

    const list = [];
    for (const el of document.querySelectorAll('button, [role="button"]')) {
        const btn = el.closest('button, [role="button"]') || el;
        const r = btn.getBoundingClientRect();
        if (r.width < 24 || r.height < 18 || r.top < -2 || r.top > 760) continue;
        const s = score(btn);
        if (s > 80) list.push({ el: btn, score: s });
    }
    list.sort((a, b) => b.score - a.score);
    if (!list.length) return { clicked: false, reason: 'no more candidate' };
    list[0].el.click();
    return { clicked: true, method: 'smart_more' };
})()
"""

CLICK_CONNECT_IN_MENU_SMART_JS = r"""
return (() => {
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const menus = Array.from(document.querySelectorAll('[role="menu"], .artdeco-dropdown__content-inner, .artdeco-dropdown'));
    const visibleMenus = menus.filter(m => {
        const r = m.getBoundingClientRect();
        return r.width > 40 && r.height > 20;
    });

    const scanRoots = visibleMenus.length ? visibleMenus : [document];
    for (const root of scanRoots) {
        for (const item of root.querySelectorAll('[role="menuitem"], button, li, div[role="button"], a')) {
            const t = norm(item.textContent || '');
            if (!t) continue;
            const low = t.toLowerCase();
            if (/^connect$/i.test(t) || /^连接$/i.test(t) || low.includes('invite to connect') || low.includes('connect') || low.includes('连接')) {
                const r = item.getBoundingClientRect();
                if (r.width > 20 && r.height > 12) {
                    item.click();
                    return { clicked: true, text: t };
                }
            }
        }
    }
    return { clicked: false, reason: 'connect menu item not found' };
})()
"""

CLICK_ADD_NOTE_SMART_JS = r"""
return (() => {
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const modal = document.querySelector('[role="dialog"], .artdeco-modal, [class*="send-invite"], [class*="invite"], [class*="modal"]');
    if (!modal) return { clicked: false, reason: 'no dialog' };

    const hasInput = !!(modal.querySelector('textarea') || modal.querySelector('[contenteditable="true"]'));
    if (hasInput) return { clicked: true, reason: 'input_already_visible' };

    for (const el of modal.querySelectorAll('button, [role="button"], span, div')) {
        const text = norm(el.textContent || '');
        const aria = norm(el.getAttribute?.('aria-label') || '');
        const low = `${text} ${aria}`.toLowerCase();
        if (low.includes('add a note') || low.includes('add note') || low.includes('添加备注') || /^note$/i.test(text) || /^备注$/i.test(text)) {
            const target = el.closest('button, [role="button"], [role="menuitem"]') || el;
            const r = target.getBoundingClientRect();
            if (r.width > 20 && r.height > 12) {
                target.click();
                return { clicked: true, reason: 'clicked' };
            }
        }
    }
    return { clicked: false, reason: 'add_note_not_found' };
})()
"""

VERIFY_MESSAGE_IN_DIALOG_JS = r"""
return (() => {
    const modal = document.querySelector('[role="dialog"], .artdeco-modal, [class*="send-invite"], [class*="invite"], [class*="modal"]') || document;
    for (const ta of modal.querySelectorAll('textarea')) {
        const val = (ta.value || '').trim();
        if (val.length > 0) return { ok: true, len: val.length, type: 'textarea' };
    }
    for (const el of modal.querySelectorAll('[contenteditable="true"]')) {
        const val = (el.innerText || el.textContent || '').trim();
        if (val.length > 0) return { ok: true, len: val.length, type: 'contenteditable' };
    }
    return { ok: false, len: 0 };
})()
"""

CLICK_SEND_SMART_JS = r"""
return (() => {
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const modal = document.querySelector('[role="dialog"], .artdeco-modal, [class*="send-invite"], [class*="invite"], [class*="modal"]');
    const scope = modal || document;
    const cands = [];
    for (const btn of scope.querySelectorAll('button, [role="button"]')) {
        const el = btn.closest('button, [role="button"]') || btn;
        const t = norm(el.textContent || '');
        const a = norm(el.getAttribute('aria-label') || '');
        const low = `${t} ${a}`.toLowerCase();
        const r = el.getBoundingClientRect();
        if (r.width < 20 || r.height < 14) continue;
        let s = 0;
        if (/^send$/i.test(t) || /^send now$/i.test(t) || /^发送$/i.test(t)) s += 120;
        if (low.includes('send invitation')) s += 180;
        if (low.includes('send')) s += 40;
        if (low.includes('发送')) s += 180;
        if (low.includes('dismiss') || low.includes('cancel')) s -= 200;
        if (el.disabled || el.getAttribute('aria-disabled') === 'true') s -= 500;
        cands.push({ el, s, t, a });
    }
    cands.sort((x, y) => y.s - x.s);
    const pick = cands.find(x => x.s > 80);
    if (!pick) return { sent: false, reason: 'no send candidate', candidates: cands.slice(0, 8).map(x => ({t:x.t,a:x.a,s:x.s})) };
    pick.el.click();
    return { sent: true, method: 'smart_send', text: pick.t, aria: pick.a };
})()
"""

SNAPSHOT_DIALOG_JS = r"""
return (() => {
    const dialogs = [];
    for (const d of document.querySelectorAll('[role="dialog"], .artdeco-modal, [class*="send-invite"], [class*="invite"], [class*="modal"]')) {
        const r = d.getBoundingClientRect();
        if (r.width < 80 || r.height < 60) continue;
        const buttons = [];
        for (const b of d.querySelectorAll('button, [role="button"]')) {
            const br = b.getBoundingClientRect();
            if (br.width < 10 || br.height < 10) continue;
            buttons.push({
                text: (b.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
                aria: (b.getAttribute('aria-label') || '').slice(0, 80),
                disabled: !!b.disabled || b.getAttribute('aria-disabled') === 'true'
            });
        }
        const inputs = [];
        for (const x of d.querySelectorAll('textarea, input[type="text"], [contenteditable="true"]')) {
            const xr = x.getBoundingClientRect();
            if (xr.width < 20 || xr.height < 10) continue;
            inputs.push({
                tag: x.tagName,
                name: x.getAttribute('name') || '',
                placeholder: x.getAttribute('placeholder') || x.getAttribute('data-placeholder') || '',
                contenteditable: x.getAttribute('contenteditable') || ''
            });
        }
        dialogs.push({ width: Math.round(r.width), height: Math.round(r.height), buttons: buttons.slice(0, 20), inputs: inputs.slice(0, 10) });
    }
    return dialogs.slice(0, 4);
})()
"""


class AutoConnector:
    """LinkedIn 自动连接器"""

    def __init__(self, driver, delay_between: float = 5.0):
        self.driver = driver
        self.delay_between = delay_between

    def _wait_dialog(self, timeout: float = 6.0) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: bool(
                    d.execute_script(
                        "const m=document.querySelector('[role=\"dialog\"],.artdeco-modal,[class*=\"send-invite\"],[class*=\"invite\"],[class*=\"modal\"]');"
                        "if(!m) return false;"
                        "const r=m.getBoundingClientRect();"
                        "return r.width>120 && r.height>80;"
                    )
                )
            )
            return True
        except Exception:
            return False

    def _has_message_input(self) -> bool:
        try:
            return bool(self.driver.execute_script(
                "const m=document.querySelector('[role=\"dialog\"],.artdeco-modal,[class*=\"send-invite\"],[class*=\"invite\"],[class*=\"modal\"]')||document;"
                "const t=m.querySelector('textarea,[contenteditable=\"true\"],input[name=\"message\"],textarea[name=\"message\"]');"
                "if(!t) return false;"
                "const r=t.getBoundingClientRect();"
                "return r.width>40 && r.height>12;"
            ))
        except Exception:
            return False

    def _detect_page_mode(self) -> str:
        try:
            info = self.driver.execute_script(GET_PAGE_MODE_JS) or {}
            mode = info.get("mode") or "standard_profile"
            return mode if mode in ("sales_navigator", "standard_profile") else "standard_profile"
        except Exception:
            return "standard_profile"

    def _click_connect(self) -> Dict[str, Any]:
        direct = self.driver.execute_script(CLICK_CONNECT_SMART_JS)
        if direct and direct.get("clicked"):
            return {"ok": True, "method": "direct", "detail": direct}
        more = self.driver.execute_script(CLICK_MORE_SMART_JS)
        if more and more.get("clicked"):
            time.sleep(0.7)
            menu = self.driver.execute_script(CLICK_CONNECT_IN_MENU_SMART_JS)
            if menu and menu.get("clicked"):
                return {"ok": True, "method": "more_menu", "detail": menu}
            return {"ok": False, "method": "more_menu", "detail": menu or more}
        return {"ok": False, "method": "none", "detail": direct or more}

    def _click_add_note(self) -> Dict[str, Any]:
        res = self.driver.execute_script(CLICK_ADD_NOTE_SMART_JS)
        if res and res.get("clicked"):
            time.sleep(0.5)
            if self._has_message_input():
                return {"ok": True, "detail": res}
        res_old = self.driver.execute_script(CLICK_ADD_NOTE_JS)
        if res_old and res_old.get("clicked"):
            time.sleep(0.5)
            if self._has_message_input():
                return {"ok": True, "detail": res_old}
        xpaths = [
            "//button[contains(@aria-label,'Add a note') or contains(@aria-label,'Add note') or contains(@aria-label,'添加备注') or contains(@aria-label,'备注')]",
            "//button[contains(.,'Add a note') or contains(.,'Add note') or contains(.,'添加备注') or contains(.,'备注')]"
        ]
        for xp in xpaths:
            try:
                btns = self.driver.find_elements(By.XPATH, xp)
                for btn in btns:
                    try:
                        if not btn.is_displayed():
                            continue
                        ActionChains(self.driver).move_to_element(btn).pause(0.1).click(btn).perform()
                        time.sleep(0.6)
                        if self._has_message_input():
                            return {"ok": True, "detail": {"clicked": True, "reason": "selenium_actionchains"}}
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
                        if self._has_message_input():
                            return {"ok": True, "detail": {"clicked": True, "reason": "selenium_js_click"}}
                    except Exception:
                        continue
            except Exception:
                pass
        try:
            btn = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Add a note') or contains(.,'Add note') or contains(.,'添加备注') or contains(.,'备注')]"))
            )
            btn.click()
            time.sleep(0.6)
            if self._has_message_input():
                return {"ok": True, "detail": {"clicked": True, "reason": "selenium_xpath"}}
        except Exception:
            pass
        return {"ok": False, "detail": res or res_old}

    def _fill_message(self, message: str) -> Dict[str, Any]:
        fill_result = None
        for _ in range(5):
            fill_result = self.driver.execute_script(FILL_MESSAGE_JS, message)
            verify = self.driver.execute_script(VERIFY_MESSAGE_IN_DIALOG_JS)
            if fill_result and fill_result.get("success") and verify and verify.get("ok") and verify.get("len", 0) >= max(10, int(len(message) * 0.4)):
                return {"ok": True, "detail": fill_result, "verify": verify}
            time.sleep(0.4)
        fallback = self._fill_with_selenium(message)
        verify = self.driver.execute_script(VERIFY_MESSAGE_IN_DIALOG_JS)
        if fallback and fallback.get("success") and verify and verify.get("ok"):
            return {"ok": True, "detail": fallback, "verify": verify}
        return {"ok": False, "detail": fill_result or fallback, "verify": verify}

    def _click_send(self) -> Dict[str, Any]:
        send = self.driver.execute_script(CLICK_SEND_SMART_JS)
        if send and send.get("sent"):
            return {"ok": True, "detail": send}
        send_old = self.driver.execute_script(CLICK_SEND_JS)
        if send_old and send_old.get("sent"):
            return {"ok": True, "detail": send_old}
        try:
            btn = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//button[contains(@aria-label,'Send invitation') or contains(@aria-label,'发送') or normalize-space()='Send' or normalize-space()='Send now' or normalize-space()='发送']"
                ))
            )
            self.driver.execute_script("arguments[0].click();", btn)
            return {"ok": True, "detail": {"sent": True, "method": "selenium_xpath"}}
        except Exception:
            return {"ok": False, "detail": send or send_old}

    def _snapshot_dialog(self) -> List[Dict[str, Any]]:
        try:
            res = self.driver.execute_script(SNAPSHOT_DIALOG_JS)
            return res or []
        except Exception:
            return []

    def connect_with_note(
        self,
        contacts: List[Dict[str, Any]],
        message_template: str,
    ) -> List[Dict[str, Any]]:
        """
        批量发送连接请求 + 个性化消息。

        Args:
            contacts: 联系人列表（需含 linkedin_url 和 name）
            message_template: 消息模板，{name} 会被替换为联系人名字

        Returns:
            结果列表，每个包含 {name, url, status, error}
        """
        results = []

        for i, contact in enumerate(contacts):
            name = contact.get("name", "")
            url = contact.get("linkedin_url", "")
            if not url:
                results.append({"name": name, "url": "", "status": "skipped", "error": "no URL"})
                continue

            logger.warning(f"[{i+1}/{len(contacts)}] {name}")

            # 个性化消息：替换 {name}，取 first name
            first_name = name.split(",")[0].split("(")[0].strip().split()[0] if name else ""
            first_name = re.sub(r'\s+(is hiring|is open to work)$', '', first_name, flags=re.IGNORECASE)
            message = (
                message_template
                .replace("{name}", first_name)
                .replace("[name]", first_name)
                .replace("[当前LinkedIn用户的名]", first_name)
            )

            result = self._connect_one(url, name, message)
            results.append(result)

            if i < len(contacts) - 1:
                time.sleep(self.delay_between)

        # 汇总
        sent = sum(1 for r in results if r["status"] == "sent")
        skipped = sum(1 for r in results if r["status"] in ("already_connected", "pending", "skipped"))
        failed = sum(1 for r in results if r["status"] == "failed")
        logger.warning(f"连接完成: 发送 {sent}, 跳过 {skipped}, 失败 {failed}")

        return results

    def _fill_with_selenium(self, message: str) -> Dict[str, Any]:
        """Selenium 原生填写备用（JS 失败时）"""
        try:
            for sel in ["textarea[name='message']", "textarea", "[contenteditable='true']"]:
                try:
                    els = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, sel))
                    )
                    for el in els:
                        try:
                            if not el.is_displayed():
                                continue
                            loc = el.location
                            if loc and loc.get("y", 0) > 600:
                                continue
                            el.click()
                            time.sleep(0.25)
                            if el.tag_name.lower() == "textarea":
                                el.clear()
                                el.send_keys(message)
                            else:
                                self.driver.execute_script(
                                    "var e=arguments[0],t=arguments[1]; e.focus(); e.textContent='';"
                                    "if(document.execCommand) document.execCommand('insertText',false,t);"
                                    "else { e.textContent=t; e.dispatchEvent(new Event('input',{bubbles:true})); }",
                                    el, message
                                )
                            return {"success": True, "type": "selenium", "method": sel}
                        except Exception:
                            continue
                except Exception:
                    pass
        except Exception as e:
            return {"success": False, "reason": str(e)}
        return {"success": False, "reason": "selenium fallback: no usable input"}

    def _connect_one(self, url: str, name: str, message: str) -> Dict[str, Any]:
        """对单个联系人执行 Connect + Add a note + Send"""
        result = {"name": name, "url": url, "status": "failed", "error": "", "message": message, "page_mode": ""}

        try:
            # 1. 导航到个人主页
            self.driver.get(url)
            time.sleep(3)

            page_mode = self._detect_page_mode()
            result["page_mode"] = page_mode

            status = self.driver.execute_script(CHECK_ACTION_STATE_JS)
            if not status:
                status = self.driver.execute_script(CHECK_STATUS_JS)
            if not status:
                result["error"] = "status check failed"
                return result

            page_status = status.get("status", "unknown")
            logger.info(f"  状态: {page_status}, 方法: {status.get('connect_method')}")

            if page_status == "already_connected":
                result["status"] = "already_connected"
                result["error"] = "已是好友"
                logger.info(f"  已是好友，跳过")
                return result

            if page_status == "pending":
                result["status"] = "pending"
                result["error"] = "已有待处理请求"
                logger.info(f"  已有待处理请求，跳过")
                return result

            # 3. 点击 Connect
            if page_status in ("can_connect", "check_more_menu", "unknown"):
                click_result = self._click_connect()
            else:
                result["error"] = f"无法连接: {page_status}"
                return result

            if not click_result or not click_result.get("ok"):
                result["error"] = f"Connect 按钮点击失败: {click_result}"
                return result

            time.sleep(1.5)

            add_note = self._click_add_note()
            if add_note and add_note.get("ok"):
                time.sleep(1.0)
            else:
                time.sleep(0.6)

            self._wait_dialog(timeout=6.0)
            time.sleep(0.4)

            fill_result = self._fill_message(message)
            if not fill_result or not fill_result.get("ok"):
                result["debug_dialog"] = self._snapshot_dialog()
                result["error"] = f"消息填写失败: {fill_result}"
                return result

            time.sleep(0.5)

            send_result = self._click_send()
            if not send_result or not send_result.get("ok"):
                try:
                    btns = self.driver.execute_script(
                        "return Array.from(document.querySelectorAll('button')).filter(b=>b.getBoundingClientRect().width>0).map(b=>({t:(b.textContent||'').trim().substring(0,50),l:(b.getAttribute('aria-label')||'').substring(0,50),inD:!!b.closest('[role=dialog]')}))"
                    )
                    result["debug_buttons"] = btns[:25] if btns else []
                except Exception:
                    pass
                result["debug_dialog"] = self._snapshot_dialog()
                result["error"] = f"Send 点击失败: {send_result}"
                return result

            result["status"] = "sent"
            result["error"] = ""
            logger.warning(f"  发送成功")
            time.sleep(1)

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"  异常: {e}")

        return result
