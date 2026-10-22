# 贡献指南

## 本地开发

```bash
git clone https://github.com/5244DragonLin/genshin_obc_exporter.git
cd genshin_obc_exporter
pip install -r requirements.txt        # 仅 PyYAML（可选）
python -m unittest discover -s tests   # 跑测试
python src/main.py --dry-run           # 不联网落盘，先看分类规模
```

## 提交改动

1. Fork 本仓库并克隆到本地
2. 新建分支：`git checkout -b feature/your-feature`
3. 提交改动，确保 `python -m unittest discover -s tests` 通过
4. 向 `main` 分支发起 Pull Request

## 约定

- 仅使用 Python 标准库，不引入新依赖
- 接口路径与频道 id 集中在 `src/obc_api.py` 与 `src/exporter.py`，站点改版时只需调这两处
- 改动建模逻辑后，可用 `.cache/` 里的词条样本回归验证（先正常跑一轮，再重跑确认产物未变）
