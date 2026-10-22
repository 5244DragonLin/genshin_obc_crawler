# genshin_obc_crawler：原神观测枢图鉴导出工具

基于纯 Python 标准库调用米游社「观测枢」（原神官方 WIKI）的公开接口，一条命令导出角色、武器、圣遗物图鉴（JSON）与角色图鉴（Markdown），词条封面随产物落盘。

数据源为 [原神观测枢](https://baike.mihoyo.com/ys/obc/) 的公开接口，全程无需登录。分类列表走米哈游 CDN 的频道接口，词条正文走 hoyowiki 新平台接口（新旧词条全覆盖）。

同系列的 [wuthering_kurobbs_exporter](https://github.com/5244DragonLin/wuthering_kurobbs_exporter) 抓的是鸣潮库街区官方接口，本项目沿用同一套增量对账与产物结构，两者互为姐妹项目。

## 💡为什么需要？

- 观测枢词条正文是富文本 HTML，技能倍率表、突破材料、命之座全埋在模板组件里，想按「元素」「星级」「部位」检索只能自己拆
- 接口响应里大量字段是「字符串化的字典/列表」（服务端直接 `str()` 后塞进 JSON），不专门处理拿到的全是转义文本
- 老的词条详情接口只覆盖未迁移的旧词条，新词条请求会报「内容不存在」，需要走新平台接口并统一新旧数据
- 站点随版本更新，想要最新内容就得能随时重跑

**genshin_obc_crawler 解决这些问题**：把字符串化字段还原成结构、把组件模板还原成字段，一次运行落盘成可直接检索的 JSON 与 Markdown。

## ⭐亮点

- **零依赖**：仅 Python 标准库，3.8+ 直接运行
- **直连接口**：读官方 JSON 接口，不渲染页面、不解析 DOM，省掉浏览器依赖
- **新旧词条全覆盖**：列表走 CDN 频道接口、正文走 hoyowiki 新平台接口，老角色和新角色（丝柯克等）都能取到
- **字符串化字段还原**：接口里的 Python 字面量字符串递归解析成真正的 dict/list
- **三类图鉴按信息建模**：角色（天赋倍率表、命之座、突破材料、语音、角色故事）、武器（精炼技能、成长数值、突破材料）、圣遗物（套装效果、五部位名称与故事、搭配推荐）各有固定键名
- **语音语言可裁剪**：默认只保留汉语语音，要日语/英语/韩语在 `config.yaml` 的 `voice_languages` 里加即可
- **材料条目化**：突破材料拆成 `{name, count, id}`，`id` 就是该材料词条的 content_id，可直接关联
- **角色双格式**：角色图鉴同时出 JSON 与 Markdown，每人一篇放在 `旅行者/` 下，配 `index.md` 索引表
- **封面本地化**：词条封面随 JSON 落盘，JSON 里给相对路径，离线也能看图
- **增量维护**：按内容指纹对账，没变的条目原样沿用、没变的分类不重写文件，每轮新增/更新/移除都写进 `changes.json`
- **断点续跑**：分类列表与词条正文本地缓存，中断后重跑只补缺的部分
- **分类可裁剪**：`--only 角色 武器` 只导指定分类；长期只导某几类，在 `config.yaml` 的 `catalogs` 段里关掉即可
- **空跑校验**：`--dry-run` 只统计各分类条数，先看清规模再落盘

## 🖥️效果预览

运行日志（text，非终端下进度条自动降级成按 10% 打一行）：

```text
====================================================================
原神观测枢图鉴导出 0.1.0｜3 个分类
本次抓取：角色图鉴、武器图鉴、圣遗物图鉴
输出目录：E:\BaiduSyncdisk\其他\原神观测枢图鉴
增量方式：全量正文 + 指纹对账（未变化的条目不重写）
====================================================================

[角色图鉴] 开始抓取
  角色图鉴 100%（136/136）
  角色 Markdown 完成：136 篇 → 旅行者/（本次重写 136 篇）
  角色图鉴 完成：136 条，失败 0 条（新增 133 / 更新 3 / 移除 0 / 未变 0）
[武器图鉴] 开始抓取
  武器图鉴 100%（252/252）
  武器图鉴 完成：252 条，失败 0 条（新增 249 / 更新 0 / 移除 0 / 未变 3）
[圣遗物图鉴] 开始抓取
  圣遗物图鉴 100%（63/63）
  圣遗物图鉴 完成：63 条，失败 0 条（新增 60 / 更新 3 / 移除 0 / 未变 0）

====================================================================
导出完成：451 条，失败 0 条
本次变化：新增 442、更新 6、移除 0、未变 3、失败 0
  角色图鉴：136 条 → 角色图鉴.json
  武器图鉴：252 条 → 武器图鉴.json
  圣遗物图鉴：63 条 → 圣遗物图鉴.json
产物目录：E:\BaiduSyncdisk\其他\原神观测枢图鉴
变更明细：E:\BaiduSyncdisk\其他\原神观测枢图鉴\changes.json
```

重跑第二轮，站点没有更新时全部「未变」，产物文件一个都不重写：

```text
导出完成：451 条，失败 0 条
本次变化：新增 0、更新 0、移除 0、未变 451、失败 0
  角色图鉴：136 条 → 角色图鉴.json（未变）
  武器图鉴：252 条 → 武器图鉴.json（未变）
  圣遗物图鉴：63 条 → 圣遗物图鉴.json（未变）
```

输出目录（text）：

```text
原神观测枢图鉴/
├── 角色图鉴.json
├── 旅行者/                    # 角色 Markdown，每人一篇
│   ├── index.md              # 索引：角色 / 元素 / 武器类型 / 稀有度 / 地区
│   ├── 丝柯克.md
│   └── ...
├── 武器图鉴.json
├── 圣遗物图鉴.json
├── assets/
│   ├── character/            # 角色封面
│   ├── weapon/
│   └── artifact/
├── manifest.json             # 各分类条数、失败明细与检查时间
├── changes.json              # 本轮新增 / 更新 / 移除明细
├── .state.json               # 封面地址台账（可删）
└── README.md
```

角色图鉴 JSON 片段（json）：

```json
{
  "id": "505417",
  "name": "丝柯克",
  "element": "冰",
  "weapon_type": "单手剑",
  "rarity": 5,
  "cv": {"中": "谢莹", "日": "能登麻美子", "英": "Cat Protano（卡特·普罗塔诺）", "韩": "서다혜（徐多慧）"},
  "basic": {"生日": "11月5日", "所属": "寰宇劫灭", "定位": "冰元素输出角色"},
  "talents": [
    {"tab": "天赋1（普通攻击）", "name": "极恶技·断",
     "desc": "普通攻击\n进行至多五段的连续攻击。……",
     "multipliers": {"header": ["详细属性", "LV1", "…"],
                     "rows": [["一段伤害", "54.5%", "59.0%", "…"]]}}
  ],
  "ascension": [
    {"level": "1级属性/突破所需材料",
     "materials": [{"name": "哀叙冰玉碎屑", "count": 1, "id": "857"}]}
  ]
}
```

圣遗物图鉴 JSON 片段（json）：

```json
{
  "id": "508652",
  "name": "影中沉凝的幻灭",
  "rarity": "4星/5星",
  "set_effects": {"2件套效果": "……", "4件套效果": "……"},
  "pieces": {
    "生之花": {"name": "止于荣礼的缎彩", "desc": "……", "story": "……"},
    "死之羽": {"name": "……", "desc": "……", "story": "……"}
  }
}
```

角色 Markdown 每篇按「基础信息 → 档案 → 天赋（含倍率表）→ 命之座 → 突破材料 → 推荐装备 → 语音 → 角色故事」排列：

```markdown
## 天赋：天赋1（普通攻击） / 极恶技·断

普通攻击
进行至多五段的连续攻击。……

| 详细属性 | LV1 | LV2 | … |
| --- | --- | --- | … |
| 一段伤害 | 54.5% | 59.0% | … |
```

## 🚀快速开始

### 1. 克隆项目

```bash
# Gitee 镜像（国内访问快）
git clone https://gitee.com/yhl5244/genshin_obc_crawler.git

# GitHub 原仓库
git clone https://github.com/5244DragonLin/genshin_obc_crawler.git

cd genshin_obc_crawler
```

### 2. 安装依赖

```bash
pip install -r requirements.txt   # 仅标准库即可运行，装了 PyYAML 解析配置更稳
```

### 3. 配置文件

复制一份配置，改掉输出目录（不复制也能跑，默认输出到 `output/`）：

```bash
cp config.example.yaml config.yaml
```

### 4. 运行

```bash
# 导出全部三类（角色 / 武器 / 圣遗物）
python src/main.py

# 指定输出目录与分类
python src/main.py --out "E:/BaiduSyncdisk/其他/原神观测枢图鉴" --only 角色

# 先看规模再决定是否落盘
python src/main.py --dry-run
```

## ⌨️CLI 模式

```text
python src/main.py [--out DIR] [--only 分类 …] [--config FILE] [--images|--no-images]
                   [--limit N] [--refresh] [--progress|--no-progress] [--dry-run] [--version]
```

### 输入选项

| 参数 | 说明 |
| --- | --- |
| `--only` | 只导出指定分类，空格或逗号分隔；别名：角色、武器、圣遗物 |
| `--config, -c` | 配置文件路径，默认 `config.yaml` |

### 输出选项

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--out, -o` | 产物目录 | 取配置 `output_dir`，缺省 `output` |
| `--images / --no-images` | 是否下载词条封面 | 开启 |
| `--progress / --no-progress` | 是否显示进度条；关掉后只打日志 | 开启 |
| `--dry-run` | 只统计条数，不写文件 | `false` |

### 抓取选项

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--limit` | 每个分类最多导出几条（试跑） | `0`（不限） |
| `--refresh` | 忽略 HTTP 缓存重新请求，仍与旧产物对比 | `false` |
| `--version` | 打印版本号 | — |

## 📄配置文件

```yaml
# config.yaml
catalogs:              # 抓不抓
  角色图鉴: true
  武器图鉴: true
  圣遗物图鉴: true
output_dir: output
download_images: true
limit: 0
voice_languages:       # 角色保留哪些语言的语音，all = 全部
  - 汉语
request:
  timeout: 30
  retries: 2
  delay: 0.1
  proxy: ""            # 留空 = 绕过系统代理直连
cache:
  enabled: true
  dir: .cache
  ttl_hours: 24
logging:
  verbose: false
  progress: true
```

启动时自动读取项目根目录的 `config.yaml`；改名或放别处时用 `--config` 指定。

## ⚙️配置说明

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `catalogs` | 抓哪几类图鉴，键名写分类名 / 英文键 / 简称都认 | 全开 |
| `output_dir` | 产物目录，相对路径以项目根目录为基准 | `output` |
| `download_images` | 是否下载封面到 `assets/` | `true` |
| `limit` | 每个分类最多导出几条，0 = 不限 | `0` |
| `voice_languages` | 角色保留哪些语言的语音，列表（如 `汉语`、`日语`）或 `all` | `[汉语]` |
| `request.timeout` | 单请求超时（秒） | `30` |
| `request.retries` | 网络异常重试次数 | `2` |
| `request.delay` | 请求间隔（秒） | `0.1` |
| `request.proxy` | 代理地址；留空则绕过系统/环境变量代理直连 | 空 |
| `cache.enabled` | 是否启用本地缓存 | `true` |
| `cache.dir` | 缓存目录 | `.cache` |
| `cache.ttl_hours` | 缓存有效期（小时），0 = 永不过期 | `24` |
| `logging.verbose` | 打印每次请求明细 | `false` |
| `logging.progress` | 抓取时显示进度条 | `true` |

## 📁项目结构

```text
genshin_obc_crawler/
├── src/
│   ├── main.py              # 命令行入口
│   ├── config.py            # 配置加载（内置极简 YAML 解析）
│   ├── progress.py          # 终端进度条：日志与进度共用一条通道
│   ├── obc_api.py           # 接口客户端：频道列表、词条正文、字符串化字段还原、缓存
│   ├── richtext.py          # 富文本处理：HTML → 纯文本、引用词条与图片提取
│   ├── model_utils.py       # 建模公共取值：组件定位、表格还原、材料条目
│   ├── character_model.py   # 角色词条 → 语义化 JSON
│   ├── character_md.py      # 角色词条 → 单人物 Markdown
│   ├── weapon_model.py      # 武器词条 → 语义化 JSON
│   ├── artifact_model.py    # 圣遗物词条 → 语义化 JSON
│   ├── state.py             # 增量对账：内容指纹、旧产物索引、变更清单
│   └── exporter.py          # 分类定义、抓取编排、封面下载与落盘
├── tests/
│   ├── fixtures/            # 真实词条样本（截取自接口响应）
│   ├── test_richtext.py     # 富文本处理
│   ├── test_models.py       # 三类建模（用 fixtures 回归）
│   ├── test_catalogs.py     # 客户端取值与分类解析
│   └── test_state.py        # 指纹、对账、变更记录
├── config.example.yaml
├── requirements.txt
└── README.md
```

## ❓️FAQ

**抓取需要登录或 Cookie 吗？**

不需要。两个接口都是公开 GET，本项目没有账号相关逻辑。

**为什么有的词条用老接口取不到？**

观测枢已把词条陆续迁到 hoyowiki 新平台，老的 `v1/content/info` 只剩未迁移的旧词条，新词条请求会返回 -2010「内容不存在」。本项目统一走新平台接口 `hoyowiki/genshin/wapi/entry_page`，新旧词条都能取到。

**本机开了代理软件，会影响抓取吗？**

数据源全是国内 CDN，默认绕过系统代理与环境变量代理直连，不受代理软件影响；确实需要代理时在 `config.yaml` 的 `request.proxy` 里显式指定。

**稀有度怎么来的？**

角色、武器星级取词条基础信息组件里的 `star` 字段；角色元素、武器类型、地区取分类卡片上的筛选标签，站点没写时该键不出现。圣遗物稀有度站点写的是「4星/5星」文本，原样保留。

**跑完发现文件没变，是没抓到吗？**

不是。产物按内容指纹比对，站点那边没有改动就不会重写文件。要看本轮检查了多少、有没有变化，看日志末尾的「本次变化」一行和产物目录的 `changes.json`。

**导出到一半中断了，要重来吗？**

不用。已抓到的词条正文在 `.cache/` 里，直接重跑会续着补齐。

**接口改了字段怎么办？**

接口地址与频道 id 集中在 `src/obc_api.py` 与 `src/exporter.py`，改版时只需调这两处；缓存可以 `--refresh` 清掉重取。

## 📝已知问题 / 待改进点

- [ ] 联动角色「埃洛伊」的命之座站点本身只写了 1 条，按原样导出
- [ ] 「奇偶」（千星奇域特殊角色）无 CV 面板，`cv` 键不出现
- [ ] 暂未覆盖敌人、材料、成就等其余频道，建模框架已就位，按需扩展 `src/exporter.py` 的 CATALOGS 即可
- [ ] 角色面板等级成长曲线（1-90 级属性表）站点词条未提供，未建模

## 🤝贡献

欢迎提 Issue 和 PR。

1. Fork 本仓库并克隆到本地
2. 新建分支：`git checkout -b feature/your-feature`
3. 提交改动，确保 `python -m unittest discover -s tests` 通过
4. 向 `main` 分支发起 Pull Request

## 📋更新日志

### v0.1

- 首个版本：角色、武器、圣遗物三类图鉴导出为 JSON，角色图鉴附带每人一篇 Markdown
- 三类图鉴按信息建模：角色拆天赋倍率表、命之座、突破材料、语音与角色故事（默认只留汉语，`voice_languages` 可加其他语言），武器按精炼技能与成长档位列材料，圣遗物按套装效果与五部位整理
- 词条正文走 hoyowiki 新平台接口，新旧词条全覆盖；接口响应中的字符串化字段递归还原
- 材料条目带数量与词条 id，可直接关联到材料词条
- 封面随词条落盘，分类列表与正文带本地缓存，支持断点续跑
- 增量对账：按内容指纹跳过未变条目，未变分类不重写文件，变更写进 changes.json
- 终端进度条，非终端自动降级为文字进度；默认绕过系统代理直连，可用配置显式指定代理

## 🔗关联项目

- [**wuthering_kurobbs_exporter**](https://github.com/5244DragonLin/wuthering_kurobbs_exporter) — 鸣潮库街区图鉴导出，本项目沿用其架构与产物结构
  - GitHub：https://github.com/5244DragonLin/wuthering_kurobbs_exporter
  - Gitee：https://gitee.com/yhl5244/wuthering_kurobbs_exporter
- [**wuthering_bwiki_crawler**](https://github.com/5244DragonLin/wuthering_bwiki_crawler) — 鸣潮 BWIKI 全站内容爬虫
  - GitHub：https://github.com/5244DragonLin/wuthering_bwiki_crawler
  - Gitee：https://gitee.com/yhl5244/wuthering_bwiki_crawler

## 🙏致谢

- [**wuthering_kurobbs_exporter**](https://github.com/5244DragonLin/wuthering_kurobbs_exporter) — 本项目的架构蓝本：`progress.py`、`config.py` 直接取自该项目，增量对账（`state.py`）与导出编排（`exporter.py`）按同一套思路改写
- [**obcSpider**](https://github.com/Ray-Eldath/obcSpider) — 观测枢接口的早期用法参考（`home/content/list` 频道列表、`content/info` 词条详情的调用方式）
- [**GenshinWidgets bbs-api 整理**](https://github.com/zkywalker/GenshinWidgets/wiki/bbs-api) — 观测枢各接口字段与用途的整理，排查接口问题时对照使用

## ⚠️免责声明

本工具仅供学习交流使用，不得用于任何违反法律法规或侵犯第三方权益的用途。抓取内容的版权归米哈游所有，请勿用于商业分发。因使用本工具产生的一切后果由使用者自行承担。

## 📃许可证

本项目基于 [MIT](LICENSE) 协议开源。
