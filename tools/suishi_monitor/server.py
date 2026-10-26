#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
JieGarden SuiShi & Strategy Live Monitor Server
Monitors /Users/zzh/Library/Application Support/debug/asst.log (and asst.bak.log)
Checks if '辰' (颉) or '酉' (方) SuiShi has been rolled, along with shop goods and playtime nodes.
"""

import os
import sys
import re
import json
import time
import threading
import socket
import argparse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DEFAULT_LOG_PATH = os.path.expanduser("~/Library/Application Support/debug/asst.log")
DEFAULT_BAK_LOG_PATH = os.path.expanduser("~/Library/Application Support/debug/asst.bak.log")

ALL_SUISHI_CONFIG = [
    {"branch": "子", "name": "子武", "operator": "重岳", "verse": "敬刻一道破勇力，入时者畏惧退避", "is_target": False},
    {"branch": "丑", "name": "丑谋", "operator": "望", "verse": "敬刻二思算八方，入时者移步尽失", "is_target": False},
    {"branch": "寅", "name": "寅诗", "operator": "令", "verse": "敬刻三白日逍遥，入时者所思非人", "is_target": False},
    {"branch": "卯", "name": "卯律", "operator": "均", "verse": "敬刻四天音传法，入时者难逾规矩", "is_target": False},
    {"branch": "辰", "name": "辰■", "operator": "颉", "verse": "敬刻五授道解惑，入时者不分■■", "is_target": False},
    {"branch": "巳", "name": "巳农", "operator": "黍", "verse": "敬刻六谷稻丰足，入时者朴食多餐", "is_target": False},
    {"branch": "午", "name": "午商", "operator": "绩", "verse": "敬刻七长绢聚富，入时者不知财数", "is_target": False},
    {"branch": "未", "name": "未建", "operator": "易", "verse": "敬刻八筑巧藏珍，入时者流连难返", "is_target": False},
    {"branch": "申", "name": "申铸", "operator": "年", "verse": "敬刻九铸金熔火，入时者得见其妙", "is_target": False},
    {"branch": "酉", "name": "酉疗", "operator": "方", "verse": "敬刻十抚伤愈痕，入时者以眠抗害", "is_target": True},
    {"branch": "戌", "name": "戌绘", "operator": "夕", "verse": "敬刻十一卷生花，入时者皆赏便符", "is_target": False},
    {"branch": "亥", "name": "亥食", "operator": "余", "verse": "敬刻十二催饭香，入时亲属饱肚肠", "is_target": False},
]

SUISHI_MAP = {s["branch"]: s for s in ALL_SUISHI_CONFIG}

TRAD_SIMP_CLEAN_MAP = None

def get_trad_simp_map():
    global TRAD_SIMP_CLEAN_MAP
    if TRAD_SIMP_CLEAN_MAP is None:
        json_path = os.path.join(os.path.dirname(__file__), "trad_simp_clean.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as jf:
                TRAD_SIMP_CLEAN_MAP = json.load(jf)
        else:
            TRAD_SIMP_CLEAN_MAP = {}
    return TRAD_SIMP_CLEAN_MAP

def clean_and_simplify_py(text):
    for ch in ["\"", "'", "“", "”", "‘", "’", "「", "」", "『", "』", "《", "》", "【", "】", "〈", "〉", "〔", "〕", "*", "^", "#", "~", "_", "·"]:
        text = text.replace(ch, "")
    text = text.strip(". ,-*#^~_	 ")
    if any(k in text for k in ["售罄", "折", "OFF", "價格", "价格", "NEW", "HOT"]) or text == "UP":
        return ""
    if not text or len(text) < 2 or all(c.isdigit() or c in " ," for c in text):
        return ""
    m = get_trad_simp_map()
    res = "".join(m.get(c, c) for c in text)
    corrections = { "甲贵": "甲胄", "帐第": "帐簿", "帐薄": "帐簿", "苍柯": "苍桐" }
    for k, v in corrections.items():
        res = res.replace(k, v)
    return res


HTML_CONTENT = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>界園肉鴿 · 歲時與流程即時監控</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎋</text></svg>">
    <style>
        :root {
            --bg-primary: #0f141c;
            --bg-secondary: #161e2b;
            --bg-card: #1c2738;
            --bg-card-hover: #223147;
            --border: #2c3e55;
            --border-highlight: #3b82f6;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-cyan: #06b6d4;
            --accent-blue: #3b82f6;
            --accent-amber: #f59e0b;
            --accent-emerald: #10b981;
            --accent-rose: #f43f5e;
            --target-glow: rgba(245, 158, 11, 0.4);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang TC", "Microsoft JhengHei", sans-serif;
        }

        body {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
            padding: 24px;
            min-height: 100vh;
        }

        .container {
            max-width: 1280px;
            margin: 0 auto;
        }

        /* Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 24px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }

        .header-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .badge-live {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            background: rgba(16, 185, 129, 0.15);
            color: var(--accent-emerald);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .badge-live.idle {
            background: rgba(148, 163, 184, 0.15);
            color: var(--text-secondary);
            border-color: rgba(148, 163, 184, 0.3);
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: currentColor;
            animation: pulse 1.8s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.85); }
        }

        .header-actions {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }

        .btn {
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border);
            padding: 8px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }

        .btn:hover {
            background: var(--bg-card);
            border-color: var(--accent-blue);
        }

        .btn.active {
            background: rgba(59, 130, 246, 0.2);
            border-color: var(--accent-blue);
            color: #93c5fd;
        }

        /* Targets Hero Banner */
        .targets-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }

        .target-card {
            background: linear-gradient(145deg, var(--bg-secondary), var(--bg-card));
            border: 2px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .target-card.found {
            border-color: var(--accent-amber);
            background: linear-gradient(145deg, #1f271b, #2b2512);
            box-shadow: 0 0 35px var(--target-glow);
            animation: glow 3s ease-in-out infinite alternate;
        }

        @keyframes glow {
            from { box-shadow: 0 0 20px rgba(245, 158, 11, 0.3); }
            to { box-shadow: 0 0 40px rgba(245, 158, 11, 0.7); }
        }

        .target-card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 16px;
        }

        .target-badge {
            font-size: 32px;
            font-weight: 800;
            width: 58px;
            height: 58px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 12px;
            background: rgba(245, 158, 11, 0.15);
            color: var(--accent-amber);
            border: 1px solid rgba(245, 158, 11, 0.4);
        }

        .target-info h3 {
            font-size: 22px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .target-patron {
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: 2px;
        }

        .target-status-pill {
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .status-waiting {
            background: rgba(100, 116, 139, 0.2);
            color: var(--text-secondary);
            border: 1px solid rgba(100, 116, 139, 0.3);
        }

        .status-found {
            background: rgba(245, 158, 11, 0.25);
            color: #fbbf24;
            border: 1px solid #f59e0b;
        }

        .target-verse {
            font-size: 14px;
            color: var(--text-secondary);
            background: rgba(0, 0, 0, 0.25);
            padding: 10px 14px;
            border-radius: 8px;
            margin: 14px 0;
            border-left: 3px solid var(--accent-amber);
            font-style: italic;
        }

        .target-meta {
            display: flex;
            justify-content: space-between;
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 12px;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            padding-top: 12px;
        }

        /* Overview Stat Row */
        .stats-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .stat-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
        }

        .stat-label {
            font-size: 12px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }

        .stat-value {
            font-size: 26px;
            font-weight: 700;
            color: var(--text-primary);
        }

        /* All 12 SuiShi Grid */
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .section-header h2 {
            font-size: 18px;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .suishi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 28px;
        }

        .suishi-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 14px;
            transition: all 0.2s;
            position: relative;
        }

        .suishi-card:hover {
            transform: translateY(-2px);
            background: var(--bg-card-hover);
        }

        .suishi-card.is-target {
            border-color: rgba(245, 158, 11, 0.5);
            background: rgba(245, 158, 11, 0.05);
        }

        .suishi-card.has-hits {
            border-color: rgba(59, 130, 246, 0.6);
        }

        .suishi-card-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }

        .suishi-name {
            font-weight: 700;
            font-size: 16px;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .suishi-count {
            font-size: 18px;
            font-weight: 800;
            color: var(--accent-cyan);
        }

        .suishi-count.target-count {
            color: var(--accent-amber);
        }

        .suishi-operator {
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }

        .progress-bar {
            height: 4px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 2px;
            overflow: hidden;
            margin-top: 6px;
        }

        .progress-fill {
            height: 100%;
            background: var(--accent-blue);
            transition: width 0.3s;
        }

        .progress-fill.target {
            background: var(--accent-amber);
        }

        /* Timeline and Logs */
        .timeline-container {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
        }

        .filter-tabs {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 16px;
        }

        .tab-btn {
            background: var(--bg-card);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .tab-btn.active {
            background: var(--accent-blue);
            color: white;
            border-color: var(--accent-blue);
        }

        .timeline-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-height: 520px;
            overflow-y: auto;
            padding-right: 6px;
        }

        .timeline-item {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 12px 16px;
            background: var(--bg-card);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 8px;
            font-size: 14px;
            transition: background 0.15s;
        }

        .timeline-item:hover {
            background: var(--bg-card-hover);
        }

        .timeline-item.target-hit {
            background: rgba(245, 158, 11, 0.12);
            border-left: 4px solid var(--accent-amber);
        }

        .timeline-time {
            font-size: 12px;
            color: var(--text-muted);
            white-space: nowrap;
            font-family: ui-monospace, Menlo, Monaco, monospace;
        }

        .timeline-tag {
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
            white-space: nowrap;
        }

        .tag-suishi { background: rgba(59, 130, 246, 0.2); color: #93c5fd; }
        .tag-target { background: rgba(245, 158, 11, 0.25); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.4); }
        .tag-yitrader { background: rgba(16, 185, 129, 0.2); color: #6ee7b7; }
        .tag-playtime { background: rgba(168, 85, 247, 0.2); color: #d8b4fe; }
        .tag-relic { background: rgba(244, 63, 94, 0.25); color: #fda4af; }

        .timeline-content {
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .timeline-level {
            font-size: 12px;
            color: var(--accent-cyan);
            margin-left: 6px;
        }

        /* Footer */
        footer {
            margin-top: 32px;
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.15);
        }
        ::-webkit-scrollbar-thumb {
            background: var(--border);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: var(--text-muted);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <div class="header-title">
                    <h1>界園肉鴿 · 歲時與流程即時監控</h1>
                    <span id="liveStatusBadge" class="badge-live">
                        <span class="pulse-dot"></span>
                        <span id="liveStatusText">監控連線中</span>
                    </span>
                </div>
                <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">
                    監控路徑: <code id="logPathDisplay" style="color: var(--text-secondary);">-</code>
                </div>
            </div>
            <div class="header-actions">
                <button id="toggleBakBtn" class="btn" onclick="toggleBakLog()">
                    <span>📜 包含歷史日誌 (asst.bak)</span>
                </button>
                <button id="audioAlertBtn" class="btn active" onclick="toggleAudioAlert()">
                    <span>🔔 音效提示: 開</span>
                </button>
                <button id="notificationBtn" class="btn" onclick="requestNotificationPermission()">
                    <span>💬 瀏覽器通知</span>
                </button>
                <button class="btn" onclick="fetchStatus()">
                    <span>🔄 立即重整</span>
                </button>
            </div>
        </header>

        <!-- Target Cards Hero -->
        <div class="targets-grid">
            <!-- 辰■ (颉) -->
            <div id="cardChen" class="target-card">
                <div class="target-card-header">
                    <div style="display: flex; gap: 14px; align-items: center;">
                        <div class="target-badge" style="background: rgba(148, 163, 184, 0.2); color: var(--text-secondary); border-color: rgba(148, 163, 184, 0.4);">辰</div>
                        <div class="target-info">
                            <h3>辰■ <span style="font-size: 14px; color: var(--text-secondary);">【已達成 / 非目標】</span></h3>
                            <div class="target-patron">化身 / 承名：颉</div>
                        </div>
                    </div>
                    <div id="statusChen" class="target-status-pill status-waiting">
                        <span class="pulse-dot"></span>
                        <span>尚未刷出</span>
                    </div>
                </div>
                <div class="target-verse">敬刻五授道解惑，入时者不分■■</div>
                <div class="target-meta">
                    <span>出現次數: <strong id="countChen" style="font-size: 16px; color: var(--text-primary);">0</strong> 次</span>
                    <span>最近出現: <span id="lastTimeChen" style="color: var(--text-secondary);">無</span></span>
                </div>
            </div>

            <!-- 酉疗 (方) -->
            <div id="cardYou" class="target-card">
                <div class="target-card-header">
                    <div style="display: flex; gap: 14px; align-items: center;">
                        <div class="target-badge">酉</div>
                        <div class="target-info">
                            <h3>酉疗 <span style="font-size: 15px; color: var(--accent-amber);">【目標歲時】</span></h3>
                            <div class="target-patron">化身 / 承名：方</div>
                        </div>
                    </div>
                    <div id="statusYou" class="target-status-pill status-waiting">
                        <span class="pulse-dot"></span>
                        <span>尚未刷出</span>
                    </div>
                </div>
                <div class="target-verse">敬刻十抚伤愈痕，入时者以眠抗害</div>
                <div class="target-meta">
                    <span>出現次數: <strong id="countYou" style="font-size: 16px; color: var(--text-primary);">0</strong> 次</span>
                    <span>最近出現: <span id="lastTimeYou" style="color: var(--text-secondary);">無</span></span>
                </div>
            </div>
        </div>

        <!-- Stats Bar -->
        <div class="stats-bar">
            <div class="stat-card">
                <div class="stat-label">歲時檢測總次數</div>
                <div class="stat-value" id="statTotalRuns">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">目標命中總數 (酉)</div>
                <div class="stat-value" id="statTargetHits" style="color: var(--accent-amber);">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">成功辨識歲時數</div>
                <div class="stat-value" id="statDetectedCount" style="color: var(--accent-cyan);">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">未檢測到歲時 (1層/未刷出)</div>
                <div class="stat-value" id="statNoneCount" style="color: var(--text-muted);">-</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">稀有藏品觸發</div>
                <div class="stat-value" id="statRareRelicCount" style="color: var(--accent-rose);">-</div>
            </div>
        </div>

        <!-- 12 SuiShi Grid -->
        <div class="section-header">
            <h2>十二歲時全覽統計</h2>
            <span style="font-size: 13px; color: var(--text-muted);">每局第 2 層自動識別與統計</span>
        </div>
        <div id="suishiGrid" class="suishi-grid">
            <!-- Rendered by JS -->
        </div>

        <!-- Timeline -->
        <div class="timeline-container">
            <div class="section-header">
                <h2>即時活動事件流水 (即時更新)</h2>
                <span id="lastEventTime" style="font-size: 13px; color: var(--text-muted);">-</span>
            </div>

            <div class="filter-tabs">
                <button class="tab-btn active" onclick="setFilter('all', this)">全部流水 (<span id="countTabAll">0</span>)</button>
                <button class="tab-btn" onclick="setFilter('target', this)">🎯 僅看目標酉 (<span id="countTabTarget">0</span>)</button>
                <button class="tab-btn" onclick="setFilter('suishi', this)">📜 歲時識別 (<span id="countTabSuishi">0</span>)</button>
                <button class="tab-btn" onclick="setFilter('yitrader', this)">🛒 易與貨架 (<span id="countTabYi">0</span>)</button>
                <button class="tab-btn" onclick="setFilter('playtime', this)">🎭 常樂節點 (<span id="countTabPlay">0</span>)</button>
            </div>

            <div id="timelineList" class="timeline-list">
                <div style="text-align: center; color: var(--text-muted); padding: 40px;">載入日誌中...</div>
            </div>
        </div>

        <footer>
            MAA Assistant Arknights · JieGarden TestStrategy Monitor · 本頁面每 2 秒自動輪詢更新
        </footer>
    </div>

    <script>
        let currentFilter = 'all';
        let includeBak = false;
        let audioAlertEnabled = true;
        let previousChenCount = -1;
        let previousYouCount = -1;
        let audioCtx = null;
        let allEvents = [];

        function initAudio() {
            if (!audioCtx) {
                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
        }

        function playDingSound() {
            if (!audioAlertEnabled) return;
            try {
                initAudio();
                if (audioCtx.state === 'suspended') {
                    audioCtx.resume();
                }
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(880, audioCtx.currentTime); // A5
                osc.frequency.exponentialRampToValueAtTime(1760, audioCtx.currentTime + 0.3); // A6
                gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 1.2);
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.start();
                osc.stop(audioCtx.currentTime + 1.2);
            } catch (e) {
                console.error("Audio play failed:", e);
            }
        }

        function toggleAudioAlert() {
            audioAlertEnabled = !audioAlertEnabled;
            const btn = document.getElementById('audioAlertBtn');
            btn.className = audioAlertEnabled ? 'btn active' : 'btn';
            btn.innerHTML = audioAlertEnabled ? '<span>🔔 音效提示: 開</span>' : '<span>🔕 音效提示: 關</span>';
            if (audioAlertEnabled) {
                initAudio();
                playDingSound();
            }
        }

        function toggleBakLog() {
            includeBak = !includeBak;
            const btn = document.getElementById('toggleBakBtn');
            btn.className = includeBak ? 'btn active' : 'btn';
            fetchStatus();
        }

        function requestNotificationPermission() {
            if (!("Notification" in window)) {
                alert("此瀏覽器不支援桌面通知");
                return;
            }
            Notification.requestPermission().then(permission => {
                const btn = document.getElementById('notificationBtn');
                if (permission === "granted") {
                    btn.classList.add("active");
                    btn.innerHTML = '<span>✅ 通知已開啟</span>';
                    new Notification("界園歲時監控", { body: "通知功能已成功啟用！" });
                } else {
                    btn.classList.remove("active");
                    btn.innerHTML = '<span>❌ 通知已拒絕</span>';
                }
            });
        }

        async function fetchStatus() {
            try {
                const res = await fetch(`/api/status?bak=${includeBak ? '1' : '0'}`);
                if (!res.ok) throw new Error("HTTP " + res.status);
                const data = await res.json();
                renderUI(data);
            } catch (err) {
                console.error("Fetch error:", err);
                const badge = document.getElementById('liveStatusBadge');
                badge.className = 'badge-live idle';
                document.getElementById('liveStatusText').textContent = '連線失敗，重試中...';
            }
        }

        function renderUI(data) {
            // Path
            document.getElementById('logPathDisplay').textContent = data.log_path + (data.include_bak ? ' (含 asst.bak.log)' : '');

            // Live status
            const badge = document.getElementById('liveStatusBadge');
            const statusText = document.getElementById('liveStatusText');
            if (data.is_running) {
                badge.className = 'badge-live';
                statusText.textContent = `監控中 · MAA 運作中 (${data.last_log_ago})`;
            } else {
                badge.className = 'badge-live idle';
                statusText.textContent = `監控中 · MAA 閒置 (${data.last_log_ago})`;
            }

            // Target Chen
            const chen = data.targets.chen;
            const cardChen = document.getElementById('cardChen');
            const statusChen = document.getElementById('statusChen');
            document.getElementById('countChen').textContent = chen.count;
            document.getElementById('lastTimeChen').textContent = chen.last_time || '無';
            if (chen.count > 0) {
                cardChen.classList.add('found');
                statusChen.className = 'target-status-pill status-found';
                statusChen.innerHTML = '<span>🎉 已刷出！</span>';
            } else {
                cardChen.classList.remove('found');
                statusChen.className = 'target-status-pill status-waiting';
                statusChen.innerHTML = '<span class="pulse-dot"></span><span>尚未刷出</span>';
            }

            // Target You
            const you = data.targets.you;
            const cardYou = document.getElementById('cardYou');
            const statusYou = document.getElementById('statusYou');
            document.getElementById('countYou').textContent = you.count;
            document.getElementById('lastTimeYou').textContent = you.last_time || '無';
            if (you.count > 0) {
                cardYou.classList.add('found');
                statusYou.className = 'target-status-pill status-found';
                statusYou.innerHTML = '<span>🎉 已刷出！</span>';
            } else {
                cardYou.classList.remove('found');
                statusYou.className = 'target-status-pill status-waiting';
                statusYou.innerHTML = '<span class="pulse-dot"></span><span>尚未刷出</span>';
            }

            // Trigger alert on new hit (target: You)
            if (previousYouCount >= 0 && you.count > previousYouCount) {
                triggerTargetAlert('酉疗', you.last_time);
            }
            previousChenCount = chen.count;
            previousYouCount = you.count;

            // Stats
            document.getElementById('statTotalRuns').textContent = data.summary.total_runs;
            document.getElementById('statTargetHits').textContent = you.count;
            document.getElementById('statDetectedCount').textContent = data.summary.detected_count;
            document.getElementById('statNoneCount').textContent = data.summary.none_count;
            document.getElementById('statRareRelicCount').textContent = data.summary.rare_relic_count;

            // Render 12 SuiShi Grid
            renderSuishiGrid(data.suishi_stats, data.summary.detected_count);

            // Timeline
            allEvents = data.events || [];
            updateTimelineCounts();
            renderTimeline();
        }

        function triggerTargetAlert(name, time) {
            playDingSound();
            if ("Notification" in window && Notification.permission === "granted") {
                new Notification(`🎉 發現目標歲時：【${name}】！`, {
                    body: `時間：${time}，請確認現場！`,
                    icon: "🎋"
                });
            }
        }

        function renderSuishiGrid(stats, totalDetected) {
            const grid = document.getElementById('suishiGrid');
            grid.innerHTML = stats.map(s => {
                const pct = totalDetected > 0 ? ((s.count / totalDetected) * 100).toFixed(1) : 0;
                const isTargetClass = s.is_target ? 'is-target' : '';
                const hasHitsClass = s.count > 0 ? 'has-hits' : '';
                const targetCountClass = s.is_target ? 'target-count' : '';
                const fillTargetClass = s.is_target ? 'target' : '';
                const star = s.is_target ? '⭐' : '';
                return `
                    <div class="suishi-card ${isTargetClass} ${hasHitsClass}">
                        <div class="suishi-card-top">
                            <span class="suishi-name">${s.branch} · ${s.name} ${star}</span>
                            <span class="suishi-count ${targetCountClass}">${s.count}</span>
                        </div>
                        <div class="suishi-operator">承名: ${s.operator} · ${pct}%</div>
                        <div class="progress-bar">
                            <div class="progress-fill ${fillTargetClass}" style="width: ${pct}%;"></div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function updateTimelineCounts() {
            document.getElementById('countTabAll').textContent = allEvents.length;
            document.getElementById('countTabTarget').textContent = allEvents.filter(e => e.is_target).length;
            document.getElementById('countTabSuishi').textContent = allEvents.filter(e => e.category === 'suishi').length;
            document.getElementById('countTabYi').textContent = allEvents.filter(e => e.category === 'yitrader').length;
            document.getElementById('countTabPlay').textContent = allEvents.filter(e => e.category === 'playtime').length;
        }

        function setFilter(filter, el) {
            currentFilter = filter;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            el.classList.add('active');
            renderTimeline();
        }

        function renderTimeline() {
            const list = document.getElementById('timelineList');
            let filtered = allEvents;
            if (currentFilter === 'target') {
                filtered = allEvents.filter(e => e.is_target);
            } else if (currentFilter === 'suishi') {
                filtered = allEvents.filter(e => e.category === 'suishi');
            } else if (currentFilter === 'yitrader') {
                filtered = allEvents.filter(e => e.category === 'yitrader');
            } else if (currentFilter === 'playtime') {
                filtered = allEvents.filter(e => e.category === 'playtime');
            }

            if (filtered.length === 0) {
                list.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 30px;">尚無符合的事件記錄</div>';
                return;
            }

            list.innerHTML = filtered.slice(0, 150).map(e => {
                let tagClass = 'tag-suishi';
                let tagText = '歲時';
                if (e.is_target) {
                    tagClass = 'tag-target';
                    tagText = '🎯 目標歲時';
                } else if (e.category === 'yitrader') {
                    tagClass = 'tag-yitrader';
                    tagText = '🛒 易與貨架';
                } else if (e.category === 'playtime') {
                    tagClass = 'tag-playtime';
                    tagText = '🎭 常樂節點';
                } else if (e.category === 'rare_relic') {
                    tagClass = 'tag-relic';
                    tagText = '👑 稀有藏品';
                }

                const targetHitClass = e.is_target ? 'target-hit' : '';
                const levelSpan = e.level ? `<span class="timeline-level">（${e.level}）</span>` : '';

                return `
                    <div class="timeline-item ${targetHitClass}">
                        <span class="timeline-time">${e.time}</span>
                        <span class="timeline-tag ${tagClass}">${tagText}</span>
                        <span class="timeline-content">${e.title} ${levelSpan} ${e.extra ? `<span style="color: var(--text-muted); font-size: 13px;">— ${e.extra}</span>` : ''}</span>
                    </div>
                `;
            }).join('');
        }

        // Auto poll every 2000ms
        setInterval(fetchStatus, 2000);
        fetchStatus();
    </script>
</body>
</html>
"""


def parse_log_events(include_bak=False):
    files_to_read = []
    if include_bak and os.path.exists(DEFAULT_BAK_LOG_PATH):
        files_to_read.append(DEFAULT_BAK_LOG_PATH)
    if os.path.exists(DEFAULT_LOG_PATH):
        files_to_read.append(DEFAULT_LOG_PATH)

    re_suishi = re.compile(
        r"\[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\].*?\[JieGarden TestStrategy\] Current SuiShi:\s*(?P<suishi>.*)"
    )
    re_yitrader = re.compile(
        r"\[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\].*?\[JieGarden TestStrategy\] YiTrader goods for sale:\s*(?P<goods>.*)"
    )
    re_playtime = re.compile(
        r"\[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\].*?\[JieGarden TestStrategy\] Playtime node:\s*(?P<playtime>.*)"
    )
    re_relic = re.compile(
        r"\[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\].*?\[JieGarden TestStrategy\] Rare collectible ｢\s*(?P<relic>.*?)\s*｣ detected!"
    )

    events = []
    suishi_counts = {s["branch"]: 0 for s in ALL_SUISHI_CONFIG}
    total_suishi_checks = 0
    detected_count = 0
    none_count = 0
    rare_relic_count = 0

    chen_records = []
    you_records = []

    for file_path in files_to_read:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "[JieGarden TestStrategy]" not in line or "=====" in line:
                        continue

                    # 1. SuiShi Match
                    m_sui = re_suishi.search(line)
                    if m_sui:
                        t = m_sui.group("time")
                        raw = m_sui.group("suishi").strip()
                        total_suishi_checks += 1

                        if "None detected" in raw:
                            none_count += 1
                            events.append(
                                {
                                    "time": t,
                                    "category": "suishi",
                                    "is_target": False,
                                    "title": "未檢出歲時",
                                    "level": "",
                                    "extra": "未達第 2 層或當前難度無歲時",
                                }
                            )
                            continue

                        # Extract awakening level
                        level = ""
                        for lvl in ["醒觉", "醒覺", "入髓", "真切", "朦胧", "朦朧"]:
                            if lvl in raw:
                                level = lvl
                                break

                        # Match which SuiShi
                        matched_branch = None
                        for s in ALL_SUISHI_CONFIG:
                            if (
                                s["name"] in raw
                                or s["branch"] in raw
                                or s["verse"] in raw
                                or s["operator"] in raw
                            ):
                                matched_branch = s["branch"]
                                break

                        if matched_branch:
                            detected_count += 1
                            suishi_counts[matched_branch] += 1
                            s_def = SUISHI_MAP[matched_branch]
                            is_target = s_def["is_target"]

                            if matched_branch == "辰":
                                chen_records.append(
                                    {"time": t, "level": level, "raw": raw}
                                )
                            elif matched_branch == "酉":
                                you_records.append(
                                    {"time": t, "level": level, "raw": raw}
                                )

                            events.append(
                                {
                                    "time": t,
                                    "category": "suishi",
                                    "is_target": is_target,
                                    "title": f"【{s_def['branch']}】{s_def['name']} (承名: {s_def['operator']})",
                                    "level": level,
                                    "extra": s_def["verse"],
                                }
                            )
                        else:
                            detected_count += 1
                            is_target = (
                                "酉" in raw
                                or "方" in raw
                            )
                            events.append(
                                {
                                    "time": t,
                                    "category": "suishi",
                                    "is_target": is_target,
                                    "title": raw,
                                    "level": level,
                                    "extra": "",
                                }
                            )
                        continue

                    # 2. YiTrader Goods
                    m_yi = re_yitrader.search(line)
                    if m_yi:
                        t = m_yi.group("time")
                        raw_goods = m_yi.group("goods").strip()
                        cleaned_items = [clean_and_simplify_py(g) for g in raw_goods.split(",")]
                        cleaned_items = [g for g in cleaned_items if g]
                        goods_str = ", ".join(cleaned_items) if cleaned_items else "None"
                        events.append(
                            {
                                "time": t,
                                "category": "yitrader",
                                "is_target": False,
                                "title": f"易與商店商品: {goods_str}",
                                "level": "",
                                "extra": "",
                            }
                        )
                        continue

                    # 3. Playtime Node
                    m_play = re_playtime.search(line)
                    if m_play:
                        t = m_play.group("time")
                        play = m_play.group("playtime").strip()
                        events.append(
                            {
                                "time": t,
                                "category": "playtime",
                                "is_target": False,
                                "title": f"常樂節點: {play}",
                                "level": "",
                                "extra": "",
                            }
                        )
                        continue

                    # 4. Rare Relic Trigger
                    m_relic = re_relic.search(line)
                    if m_relic:
                        t = m_relic.group("time")
                        relic = m_relic.group("relic").strip()
                        rare_relic_count += 1
                        events.append(
                            {
                                "time": t,
                                "category": "rare_relic",
                                "is_target": False,
                                "title": f"觸發稀有藏品: 【{relic}】已停止肉鴿並退出遊戲",
                                "level": "",
                                "extra": "Slack Webhook 已發送",
                            }
                        )
                        continue
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)

    # Sort events descending by time
    events.reverse()

    # Calculate 12 SuiShi Stats list
    suishi_stats = []
    for s in ALL_SUISHI_CONFIG:
        suishi_stats.append(
            {
                "branch": s["branch"],
                "name": s["name"],
                "operator": s["operator"],
                "verse": s["verse"],
                "is_target": s["is_target"],
                "count": suishi_counts[s["branch"]],
            }
        )

    # Check file last modified & MAA status
    last_log_mtime = 0
    if os.path.exists(DEFAULT_LOG_PATH):
        last_log_mtime = os.path.getmtime(DEFAULT_LOG_PATH)

    now = time.time()
    diff_sec = int(now - last_log_mtime) if last_log_mtime > 0 else 999999
    is_running = diff_sec < 60

    if diff_sec < 60:
        last_log_ago = f"{diff_sec} 秒前"
    elif diff_sec < 3600:
        last_log_ago = f"{diff_sec // 60} 分鐘前"
    else:
        last_log_ago = f"{diff_sec // 3600} 小時前"

    return {
        "log_path": DEFAULT_LOG_PATH,
        "include_bak": include_bak,
        "is_running": is_running,
        "last_log_ago": last_log_ago,
        "summary": {
            "total_runs": total_suishi_checks,
            "detected_count": detected_count,
            "none_count": none_count,
            "rare_relic_count": rare_relic_count,
        },
        "targets": {
            "chen": {
                "count": len(chen_records),
                "last_time": chen_records[-1]["time"] if chen_records else None,
                "records": chen_records,
            },
            "you": {
                "count": len(you_records),
                "last_time": you_records[-1]["time"] if you_records else None,
                "records": you_records,
            },
        },
        "suishi_stats": suishi_stats,
        "events": events,
    }


_cache_lock = threading.Lock()
_status_cache = {
    "key": None,
    "body": b"",
}


def get_cached_status_bytes(include_bak=False):
    files = [DEFAULT_LOG_PATH]
    if include_bak:
        files.insert(0, DEFAULT_BAK_LOG_PATH)

    file_signatures = []
    for fp in files:
        if os.path.exists(fp):
            try:
                st = os.stat(fp)
                file_signatures.append((fp, st.st_mtime, st.st_size))
            except OSError:
                file_signatures.append((fp, 0, 0))
        else:
            file_signatures.append((fp, -1, -1))

    cache_key = (tuple(file_signatures), include_bak)

    with _cache_lock:
        if _status_cache["key"] == cache_key:
            return _status_cache["body"]

    data = parse_log_events(include_bak=include_bak)
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    with _cache_lock:
        _status_cache["key"] = cache_key
        _status_cache["body"] = body

    return body


class SuiShiMonitorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 5

    def do_HEAD(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/" or parsed.path == "/index.html":
                body = HTML_CONTENT.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
            elif parsed.path == "/api/status":
                qs = parse_qs(parsed.query)
                include_bak = qs.get("bak", ["0"])[0] == "1"
                body = get_cached_status_bytes(include_bak=include_bak)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
            else:
                self.send_response(404)
                self.send_header("Connection", "close")
                self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/" or parsed.path == "/index.html":
                body = HTML_CONTENT.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/api/status":
                qs = parse_qs(parsed.query)
                include_bak = qs.get("bak", ["0"])[0] == "1"
                body = get_cached_status_bytes(include_bak=include_bak)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.send_header("Connection", "close")
                self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        # Silence routine request logging to keep terminal tidy
        pass


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except (AttributeError, OSError):
            pass
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(
        description="JieGarden SuiShi & Strategy Live Monitor Server"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="::",
        help="Host address to bind (default: :: for dual-stack IPv4/IPv6)",
    )
    args = parser.parse_args()

    port = args.port
    server = None
    for p in [port, port + 1, port + 2, 8000, 8888]:
        try:
            DualStackServer.allow_reuse_address = True
            server = DualStackServer((args.host, p), SuiShiMonitorHandler)
            server.daemon_threads = True
            port = p
            break
        except OSError:
            try:
                ThreadingHTTPServer.allow_reuse_address = True
                fallback_host = "0.0.0.0" if args.host in ("::", "") else args.host
                server = ThreadingHTTPServer((fallback_host, p), SuiShiMonitorHandler)
                server.daemon_threads = True
                port = p
                break
            except OSError:
                continue

    if not server:
        print(f"Failed to bind any port starting from {args.port}", file=sys.stderr)
        sys.exit(1)

    print("==================================================")
    print("🎋 界園肉鴿 · 歲時與流程即時監控服務已啟動")
    print(f"🌐 本機訪問網址: http://localhost:{port}")
    print(f"📁 監控日誌: {DEFAULT_LOG_PATH}")
    print("==================================================")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服務已停止。")
        server.server_close()


if __name__ == "__main__":
    main()
