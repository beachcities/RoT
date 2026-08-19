# analysis/

`benchmark/results/` に残っている実行結果JSONを、読むだけで分析するディレクトリ。
測定側（`run_benchmark.py` / `summarize.py` / `suites/` / `prompts.json` / `selftest.py`）は変更しない。
APIも叩かない。

- [OBSERVATIONS.md](OBSERVATIONS.md) — 図と表を見たうえでの観察。ここから読む
- `dataset.py` — 結果JSONを1試行1行に読み直すだけのローダ
- `figures.py` — 図を出す（`figures/`）
- `table.py` — 全実行を総トークン順に並べた表を出す（`tables/`）
- `inspect_counts.py` — 図を読むための素の数え上げを出す（`tables/counts.md`）

```
cd benchmark/analysis
python figures.py
python table.py
python inspect_counts.py
```
