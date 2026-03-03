# LinkedIn 营销自动化系统

从关键词搜索到联系人筛选、批量连接的一体化 CLI 工具。

## 架构

```
main.py
  └── src/cli.py (交互式命令行)
        └── src/main_controller.py (懒加载 + 组件调度)
              │
              ├── scraper/
              │     ├── browser_manager.py      Chrome 调试模式连接
              │     ├── linkedin_scraper.py      爬取编排器
              │     ├── linkedin_search_manager.py  搜索/翻页/提取调度
              │     └── extractors/
              │           └── cdp_dom_extractor.py   CDP DOM 提取器 (核心)
              │
              ├── filter/
              │     ├── smart_filter_v3.py       筛选入口
              │     ├── hybrid_scoring_engine.py  规则 + 语义混合评分
              │     ├── semantic_engine.py        SentenceTransformer 语义引擎
              │     ├── data_preprocessor.py      数据清洗
              │     └── requirements_parser.py    自然语言需求 → 结构化条件
              │
              ├── data_manager/
              │     ├── database_manager.py       SQLite 管理
              │     └── contact_manager.py        联系人 CRUD + 去重
              │
              ├── marketing/
              │     └── automation.py             连接请求 / 邮件 / 限流
              │
              └── utils/
                    ├── config_loader.py          配置加载
                    ├── logger.py                 日志
                    ├── report_generator.py       Markdown 报告生成
                    ├── llm_client.py             Kimi LLM (OpenAI 兼容)
                    ├── lazy_loader.py            组件懒加载
                    └── helpers.py                通用工具函数
```

## 数据提取原理

**CDP DOM 提取**：不解析 HTML 文件，不依赖 NLP 模型。通过 Selenium 的 `execute_script()` 在页面中执行 JavaScript，利用 LinkedIn 的语义 DOM 属性直接提取结构化数据：

- 卡片定位：`[data-view-name="people-search-result"]`
- 姓名：`figure[aria-label]`（最干净的数据源）
- 职位/公司：叶子 div 文本，按 `" at "` / `" @ "` 拆分
- 地点：第二个非噪音叶子文本
- URL：`a[href*="/in/"]`

内置安全检测：登录墙、安全验证、频率限制自动识别 + 指数退避重试。

## 工作流

```
init → start → scrape → filter → connect
```

| 步骤 | 说明 |
|------|------|
| `init` | 初始化系统（目录/配置/SQLite 数据库） |
| `start` | 连接 Chrome 调试模式浏览器（需已登录 LinkedIn） |
| `scrape` | 输入关键词 + 页数 → 自动搜索/翻页/提取 → JSON + 入库 |
| `filter` | 选择 raw 文件 + 输入需求描述 → AI 解析 + 混合评分 → 保存筛选结果 |
| `connect` | 选择招呼语 + 数据库视图 → 分批打开联系人页面 |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 Chrome 调试模式（关闭所有 Chrome 后执行）
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 --remote-allow-origins=* `
  https://www.linkedin.com

# 3. 在 Chrome 中登录 LinkedIn

# 4. 启动系统
python main.py
```

CLI 中输入 `help` 查看所有命令。

## CLI 命令

| 命令 | 说明 |
|------|------|
| `init` | 初始化系统 |
| `start` | 连接浏览器 |
| `scrape` | 交互式爬取（输入关键词和页数） |
| `scrape-sales` | Sales Navigator 爬取 |
| `filter` | 智能筛选（V3 混合引擎） |
| `report` | 生成筛选结果分析报告 |
| `connect` | 分批打开联系人页面 |
| `export [json\|csv]` | 导出数据（无参数进入菜单） |
| `import-db` | 导入 trimmed JSON 到数据库 |
| `trim` | 精简筛选结果并补全 URL |
| `queue-connect` | 按分数排队待触达联系人 |
| `status` | 查看系统状态 |
| `backup` | 备份系统数据 |
| `cleanup [天数]` | 清理旧数据 |

## 筛选引擎

**需求解析**：输入自然语言（如"食品行业的研发总监"），`RequirementsParser` 先提取显式标签，再调用 Kimi LLM 补全为结构化条件。

**混合评分**：`HybridScoringEngine` = 规则引擎 (0.6) + 语义引擎 (0.4)
- 规则引擎：基于 `config/scoring_rules.yaml` 的关键词匹配
- 语义引擎：本地 SentenceTransformer 模型计算语义相似度（离线优先）

分数 ≥ 0.3 的联系人通过筛选。

## 目录结构

```
├── main.py                  入口
├── src/                     源代码
├── config/
│   ├── settings.json        数据库/浏览器/LLM/安全配置
│   ├── keywords.json        搜索关键词
│   └── messages/            连接招呼语模板
├── data/
│   ├── raw/                 爬取原始数据 (JSON)
│   ├── processed/           筛选结果
│   ├── exports/             导出文件
│   ├── reports/             分析报告 (Markdown)
│   └── html_data/           HTML 页面存档（调试用）
├── database/                SQLite 数据库
├── tools/scripts/           工具脚本
└── tests/                   测试用例
```

## 配置

核心配置在 `config/settings.json`：

```json
{
  "database": { "path": "database/contacts.db" },
  "browser": { "chrome_debug_port": 9222 },
  "llm": {
    "api_base": "https://api.moonshot.cn/v1",
    "api_key": "你的密钥",
    "model_name": "kimi-k2.5"
  }
}
```

筛选参数已统一放在 `config/settings.json` 的 `filtering` 节点中。
