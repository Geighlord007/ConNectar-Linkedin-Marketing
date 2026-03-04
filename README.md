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
              │     └── llm_refiner.py              LLM 精炼 headline
              │
              ├── filter/
              │     ├── contact_filter.py           筛选入口
              │     └── embedding_filter.py         Embedding 向量筛选引擎
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
                    ├── helpers.py                通用工具函数
                    └── llm_client.py             LLM 客户端（OpenAI 兼容）
```

## 数据提取原理

**CDP DOM 提取**：不解析 HTML 文件，不依赖 NLP 模型。通过 Selenium 的 `execute_script()` 在页面中执行 JavaScript，利用 LinkedIn 的语义 DOM 属性直接提取结构化数据：

- 卡片定位：`[data-view-name="people-search-result"]`
- 姓名：`figure[aria-label]`（最干净的数据源）
- 职位/公司：叶子 div 文本，按 `" at "` / `" @ "` 拆分
- 地点：第二个非噪音叶子文本
- URL：`a[href*="/in/"]`

内置安全检测：登录墙、安全验证、频率限制自动识别 + 指数退避重试。

## 筛选引擎

**Embedding 向量筛选**：基于智谱 Embedding-3 模型的语义相似度 + 规则匹配混合评分

### 评分逻辑

1. **需求增强**：使用 LLM 扩展用户需求关键词库（目标公司、职位关键词、行业关键词、地点别名）

2. **向量计算**：
   - 需求描述 → Embedding 向量
   - 联系人（职位+公司+行业）→ Embedding 向量（分批处理，每批50条）

3. **混合评分**：
   - `job_score` = 规则匹配(40%) + 向量相似度(60%)
   - `company_score` = 规则匹配(50%) + 向量相似度(50%)

4. **综合评分**：
   ```
   match_score = similarity * 0.3 + company_score * 0.4 + job_score * 0.3
   ```

分数 ≥ `min_match_score` (默认 0.3) 的联系人通过筛选。

### 关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `embedding_model.batch_size` | 50 | 分批大小（智谱API限制≤64） |
| `embedding_model.timeout` | 60 | 请求超时（秒） |
| `embedding_model.dimensions` | 512 | 向量维度 |
| `llm_enhancement.enabled` | true | 需求增强开关 |

## 工作流

```
init → start → scrape → filter → export
```

| 步骤 | 说明 |
|------|------|
| `init` | 初始化系统（目录/配置/SQLite 数据库） |
| `start` | 连接 Chrome 调试模式浏览器（需已登录 LinkedIn） |
| `scrape` | 输入关键词 + 页数 → 自动搜索/翻页/提取 → JSON + 入库 |
| `filter` | 选择 raw 文件 + 输入需求描述 → Embedding 评分 → 保存筛选结果 |
| `export` | 导出筛选结果（JSON/CSV） |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 Chrome 调试模式（关闭所有 Chrome 后执行）
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 --remote-allow-origins=* `
  https://www.linkedin.com

# 3. 在 Chrome 中登录 LinkedIn

# 4. 配置环境变量（.env 文件）
# 智谱 GLM — 用于需求增强
ZHIPU_API_KEY=your_key_here
ZHIPU_API_BASE=https://open.bigmodel.cn/api/paas/v4
ZHIPU_MODEL=glm-4.5-air

# 智谱 Embedding-3 — 用于向量相似度计算
ZHIPU_EMBEDDING_KEY=your_key_here
ZHIPU_EMBEDDING_BASE=https://open.bigmodel.cn/api/paas/v4
ZHIPU_EMBEDDING_MODEL=embedding-3

# 5. 启动系统
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
| `filter` | 智能筛选（Embedding 向量引擎） |
| `export [json\|csv]` | 导出数据（无参数进入菜单） |
| `import-db` | 导入 trimmed JSON 到数据库 |
| `trim` | 精简筛选结果并补全 URL |
| `status` | 查看系统状态 |
| `backup` | 备份系统数据 |
| `cleanup [天数]` | 清理旧数据 |

## 目录结构

```
├── main.py                  入口
├── src/                     源代码
├── config/
│   ├── settings.json        数据库/浏览器/LLM/筛选配置
│   ├── keywords.json        搜索关键词
│   ├── messages/            连接招呼语模板
│   └── email_templates.json 邮件模板
├── data/
│   ├── raw/                 爬取原始数据 (JSON)
│   │   └── _sessions/       搜索结果会话
│   ├── processed/           处理后的数据
│   ├── filter_results/      筛选结果（按运行时间分目录）
│   │   └── run_YYYYMMDD_HHMMSS/
│   └── exports/             导出文件
├── database/                SQLite 数据库
├── logs/                    系统日志
└── .env                     环境变量（API Keys）
```

## 配置

核心配置在 `config/settings.json`：

```json
{
  "database": {
    "path": "database/contacts.db",
    "backup_enabled": true
  },
  "browser": {
    "chrome_debug_port": 9222,
    "headless": false
  },
  "embedding_model": {
    "enabled": true,
    "model_name": "${ZHIPU_EMBEDDING_MODEL:-embedding-3}",
    "api_base": "${ZHIPU_EMBEDDING_BASE}",
    "api_key": "${ZHIPU_EMBEDDING_KEY}",
    "dimensions": 512,
    "timeout": 60,
    "batch_size": 50
  },
  "llm_enhancement": {
    "enabled": true,
    "model_name": "${ZHIPU_MODEL}",
    "api_base": "${ZHIPU_API_BASE}",
    "api_key": "${ZHIPU_API_KEY}",
    "timeout": 60
  },
  "filtering": {
    "min_match_score": 0.3,
    "weights": {
      "embedding_similarity": 0.3,
      "company_match": 0.4,
      "job_keywords": 0.3
    },
    "rule_scores": {
      "company_exact_match": 0.8,
      "company_partial_match": 0.5,
      "job_keyword_match": 0.3
    }
  }
}
```