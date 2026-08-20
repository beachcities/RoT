# analysis/

`benchmark/results/` に残っている実行結果JSONを、読むだけで分析するディレクトリ。
測定側（`run_benchmark.py` / `summarize.py` / `suites/` / `prompts.json` / `selftest.py`）は変更しない。
APIも叩かない。

## 分布を見る

- [OBSERVATIONS.md](OBSERVATIONS.md) — 図と表を見たうえでの観察。ここから読む
- `dataset.py` — 結果JSONを1試行1行に読み直すだけのローダ
- `figures.py` — 図を出す（`figures/`）
- `table.py` — 全実行を総トークン順に並べた表を出す（`tables/`）
- `inspect_counts.py` — 図を読むための素の数え上げを出す（`tables/counts.md`）

## 公開の準備

- [REFERENCE_READINESS.md](REFERENCE_READINESS.md) — 再現・検証に要る情報の棚卸しと、記録すべきものの提案
- [RESULTS_PUBLICATION.md](RESULTS_PUBLICATION.md) — `results/` を公開するかどうか、するならどの形か
- [README_DRAFT.md](README_DRAFT.md) — トップと `benchmark/` の README 改訂案
- `input_fingerprint.py` — 結果JSONだけから入力の版を見分けられるかを調べる（`tables/input_fingerprint.md`）

```
cd benchmark/analysis
python figures.py
python table.py
python inspect_counts.py
python input_fingerprint.py
```
