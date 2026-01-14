# 🔍 PAA Scraper v2.0

> Google "People Also Ask" 智能抓取工具 | 支持断点续爬 | 智能重试机制

---

## ✨ 功能特性 (Features)

### 🔄 智能重试机制 (Smart Fallback)
当原始关键词没有触发 PAA 时，自动转换为多种变体再次尝试：
- `What is + 关键词` — 定义类问题
- `Best + 关键词` — 测评/电商类
- `How to use + 关键词` — 教程类
- `How to choose + 关键词` — 选购类
- `关键词 + guide` — 指南类

**极大提高 PAA 触发成功率！**

### 💾 断点续爬 (Resume Capability)
- 启动时自动检测同名 Excel 文件
- 自动跳过已抓取的问题
- 支持随时中断和继续
- 每抓取一条数据立即保存，不怕意外中断

### 📂 动态文件存储
- 自动以关键词命名 Excel 文件
- 统一保存在 `results/` 目录下
- 示例：`Pickleball_Paddles.xlsx`、`Outdoor_Rugs.xlsx`

### 🛡️ 防闪退系统
- 全局异常捕获，出错不会直接闪退
- 详细错误信息和解决方案提示
- 程序结束前暂停，方便查看运行结果

### 🤖 反检测技术
- Selenium Stealth 隐藏自动化特征
- 随机延迟模拟人类行为
- 智能滚动触发懒加载内容

---

## 🚀 快速开始

### 1. 配置关键词
编辑 `config.json` 文件：
```json
{
    "keywords": [
        "Outdoor Rugs",
        "Pickleball Paddles"
    ],
    "max_depth": 3,
    "headless": false
}
```

### 2. 运行程序
双击 `PAA_Scraper.exe` 或运行：
```bash
python paa_scraper.py
```

### 3. 查看结果
```
results/
├── Outdoor_Rugs.xlsx
├── Pickleball_Paddles.xlsx
└── ...
```

---

## ⚙️ 配置说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `keywords` | 数组 | `[]` | 要抓取的关键词列表 |
| `max_depth` | 数字 | `3` | PAA 展开深度 (建议 2-5) |
| `headless` | 布尔 | `false` | 是否隐藏浏览器窗口 |

---

## 📊 Excel 数据结构

| 列名 | 说明 |
|------|------|
| Original Keyword | 原始关键词 |
| Search Term | 实际搜索词 (可能带前缀) |
| Type | 类型 (PAA / Related Search) |
| Question/Term | 问题或搜索词 |
| Snippet | 答案摘要 |
| Source Link | 来源链接 |
| Discovery Level | 发现层级 |
| Data Source | 数据来源 (Original / Retry) |

---

## ⚠️ 注意事项

1. **Chrome 浏览器**：请确保已安装 Google Chrome
2. **人机验证**：遇到 CAPTCHA 时，手动完成验证后按回车继续
3. **抓取速度**：程序故意放慢速度以避免被封禁
4. **分批处理**：建议每次不超过 10 个关键词

---

## 🛠️ 常见问题

**Q: 程序闪退怎么办？**
A: v2.0 已增加防闪退机制，会显示详细错误信息。如仍有问题，请用 PowerShell 运行查看报错。

**Q: 如何重新抓取某个关键词？**
A: 删除 `results/` 目录下对应的 Excel 文件即可。

**Q: config.json 格式错误？**
A: 程序会提示具体错误位置（行号和列号），请检查 JSON 格式。

---

## 📝 更新日志 (Changelog)

### v2.0 (2026-01-14)

#### ✨ 新功能 (Feat)
- 增加 **PAA 强制触发策略**：自动改写关键词，支持 6 种前缀/后缀变体
- 新增 `Search Term` 和 `Data Source` 列，标识数据来源
- 智能滚动加载：自动滚动页面触发懒加载内容

#### 🐛 修复 (Fix)
- 修复 Windows 控制台中文乱码问题
- 修复 CAPTCHA 验证后页面未刷新导致的闪退
- 修复 ChromeDriver 初始化失败无提示的问题

#### 🔧 优化 (Refactor)
- 重构存储逻辑，实现**一词一表**（每个关键词独立 Excel 文件）
- 增加全局异常捕获和程序结束暂停
- 优化点击逻辑，支持 JavaScript 兜底点击
- 增强 CAPTCHA 检测，支持多种验证类型
- ChromeDriver 初始化增加重试机制

---

### v1.0 (初始版本)
- 基础 PAA 抓取功能
- 断点续爬支持
- Excel 实时保存

---

## 📧 技术支持

如有问题，请检查：
1. 是否已安装 Google Chrome 浏览器
2. config.json 格式是否正确
3. 网络连接是否正常（需要访问 Google）

---

<p align="center">
  <b>祝您使用愉快！🎉</b>
</p>
