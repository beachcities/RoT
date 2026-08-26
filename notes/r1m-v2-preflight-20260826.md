# 計器v2.0 パイロット preflight（2026-08-26）

仕様の正本は `paper/notes/instrument-v2-distribution-probe.md` の **v2.0凍結版**
（凍結コミット `04caeaa`、第3節の根拠置換 `1392548`）。本文書は同仕様 第8節⑤の
preflight であり、**chat の照合を待って停止する。走行はしていない。**

---

## (a) AUDITED_COMMIT

```
AUDITED_COMMIT=28e2acca0c903e35cf6fe4aa8df55b2e9fff7e5e
```

追随実装を含む監査対象コミット。**GO は当該 SHA に対する GO** とし、GO 受領後に
タグ `instrument-v2.0` をこの SHA に打ってから走行へ入る。

走行は `drive_cli_run.py --commit 28e2acca0c903e35cf6fe4aa8df55b2e9fff7e5e` で実施し、
**`--use-local` は使わない。** ラン記録で `fingerprint.git.commit == AUDITED_COMMIT`
を確認して記載する。

## (b) 仕様条項 → 実装箇所の対応表

| 仕様条項 | 実装箇所（ファイル・関数） | 備考 |
| --- | --- | --- |
| 第2節 一発勝負（試行上限1・再試行プロンプトなし） | `run_benchmark.py` の `run_task`（`max_attempts=1` で再試行分岐に入らない） | 走行時 `--max-attempts 1` |
| 第2節 seed群の事前登録・記録 | `suites/build_v4.py` の `MASTER_SEEDS`／`design_for`、`run_benchmark.py` の `resolve_sample`、各試行の `seed` 欄 | (d) 参照 |
| 第2節 v3非互換の別スイート | `suites/v4_distribution/`（`build_v4.py` が生成） | v3 と直接比較しない |
| 第3節 格子 t×d の15セル | `build_v4.py` の `main`（`for t in (0,1,2) / for d in (0..4)`） | |
| 第3節 変種 V=C(2,t)·C(4,d) | `build_v4.py` の `variant_count`／`variants_for` | (c) 参照 |
| 第3節 外れ部分集合は振る | `build_v4.py` の `variants_for`＋条件の `arm: "varied"` | 固定側は生成しない |
| 第3節 入れ子master seed（先頭から取る） | `build_v4.py` の `MASTER_SEEDS`／`design_for` | (d) 参照 |
| 第3節 **完全交差・均衡**（同一セル内で同じseed集合を全変種に交差） | `run_benchmark.py` の `resolve_sample`（変種 `i // k`、seed `seeds[i % k]`） | selftest「同一セル内で同じ seed 集合が全変種に交差する」 |
| 第3節 各変種に最低2seed／均衡が取れないnは採らない | `build_v4.py` の `design_for`（`k < 2` と `n % V` で `SystemExit`） | |
| 第3節 variant×seed の二段記録 | `run_benchmark.py` の結果行 `variant`／`seed` | |
| 第3節 パイロット最小設計（計200） | `build_v4.py` の `N_TABLE` | (e) 参照 |
| 第4節 H=C(6−t−d, 2−t)、γ=1/H | `build_v4.py` の `hypotheses`／`gamma` | (c) 参照 |
| 第5節 横軸 x=log₂H | `build_v4.py` が条件に `log2H` を持たせ、`summarize_v4.py` の表と `v4_grid.py` の小字に出す | |
| 第5節 t=2 は m/w 推定の対象外（lapse系列） | 条件の `series: "lapse"`、`v4_grid.py` が t=2 行に注記 | 当てはめ自体は chat の仕事 |
| 第7節 棄権の定義（理由の明示。0の機械判定ではない） | `summarize_v4.py` の `ABSTAIN_STRONG`／`ABSTAIN_ABSENT`／`ABSTAIN_UNABLE`／`abstention` | 判定規則本文は下記 |
| 第7節 二部モデル（山統計は非棄権、棄権込みは感度分析） | `summarize_v4.py` の `describe`（分母 `m`＝非棄権、`感度_棄権込み`） | 総トークンは全標本 |
| 第7節 山は隙間ベースの素朴な実装・閾値依存は留保 | `summarize_v4.py` の `cluster`（相対閾値5%）、凡例に明記 | |
| 第8節⑤ preflight・AUDITED_COMMIT | 本文書 | |
| 第8節 チェックポイントと再開 | `run_benchmark.py` の `append_partial`／`load_partial`、`colab/drive_cli_run.py` | 標本ごとに書き出し |
| 発注⓪-5 GPU不要selftestのActions | `.github/workflows/selftest.yml` | (f) 参照 |

### 棄権の判定規則（本文）

最終回答の本文のみを見る（思考テキストは見ない）。次のいずれかで棄権とする。

1. **強い言い切り**が含まれる：`特定できません` / `特定することができません` /
   `特定できない` / `回答できません` / `答えられません` /
   `該当する企業は存在しません` / `該当する企業はありません` / `該当なし`
2. **「対応が無い」と「だから出せない」の両方**が含まれる。
   * 対応が無い側：`定義されていない` / `定義がありません` / `定義はありません` /
     `定義が含まれ` / `含まれていません` / `提供されていません` / `提供されていない` /
     `記載されていません` / `記載がありません` / `マッピング` / `対応関係` /
     `不明` / `判別できません`
   * 出せない側：`できません` / `できない` / `判断できません` / `0 となります` /
     `0となります` / `0 です` / `0です` / `存在しません` / `ありません`

**数値0そのものは棄権の要件ではない**（0 が正当な数値解になり得る課題への拡張に備える）。
当たった語は各標本に `棄権の根拠` として記録し、集計出力にヒット標本一覧を印字する。

**既存データでの当たり方**：スモーク（`run_20260826T030829Z`）の20標本に適用すると、
**既知の4標本にだけ当たり、他には当たらない**。

| 条件 | 反復 | 値 | 当たった語 |
| --- | --- | --- | --- |
| `t0_d2_varied` | 4 | 0 | `特定することができません` |
| `t0_d2_varied` | 5 | 0 | `含まれていません` + `できません` |
| `t0_d2_varied` | 9 | 0 | `定義が含まれ` + `含まれていません` |
| `t0_d2_fixed` | 6 | 0 | `記載されていません` + `対応関係` |

## (c) V／H／γ 表（15セル、実装側の算出値）

| セル | V | H | log₂H | γ | n | k | seed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| t=0 d=0 | 1 | 15 | 3.907 | 1/15 | 12 | 12 | S1〜S12 |
| t=0 d=1 | 4 | 10 | 3.322 | 1/10 | 12 | 3 | S1〜S3 |
| t=0 d=2 | 6 | 6 | 2.585 | 1/6 | 12 | 2 | S1〜S2 |
| t=0 d=3 | 4 | 3 | 1.585 | 1/3 | 12 | 3 | S1〜S3 |
| t=0 d=4 | 1 | 1 | 0.000 | 1 | 12 | 12 | S1〜S12 |
| t=1 d=0 | 2 | 5 | 2.322 | 1/5 | 12 | 6 | S1〜S6 |
| t=1 d=1 | 8 | 4 | 2.000 | 1/4 | 16 | 2 | S1〜S2 |
| t=1 d=2 | 12 | 3 | 1.585 | 1/3 | 24 | 2 | S1〜S2 |
| t=1 d=3 | 8 | 2 | 1.000 | 1/2 | 16 | 2 | S1〜S2 |
| t=1 d=4 | 2 | 1 | 0.000 | 1 | 12 | 6 | S1〜S6 |
| t=2 d=0 | 1 | 1 | 0.000 | 1 | 12 | 12 | S1〜S12 |
| t=2 d=1 | 4 | 1 | 0.000 | 1 | 12 | 3 | S1〜S3 |
| t=2 d=2 | 6 | 1 | 0.000 | 1 | 12 | 2 | S1〜S2 |
| t=2 d=3 | 4 | 1 | 0.000 | 1 | 12 | 3 | S1〜S3 |
| t=2 d=4 | 1 | 1 | 0.000 | 1 | 12 | 12 | S1〜S12 |

**仕様との照合**：V は t=0行 `1,4,6,4,1`／t=1行 `2,8,12,8,2`／t=2行 `1,4,6,4,1`、
H は t=0断面 `15,10,6,3,1`／t=1断面 `5,4,3,2,1`／t=2断面 全て `1` で、
**15セルすべて仕様第3・4節と一致**。selftest が毎コミット同じ照合をする。

## (d) master seed 集合

```
S1..S12 = 20260901, 20260902, 20260903, 20260904, 20260905, 20260906,
          20260907, 20260908, 20260909, 20260910, 20260911, 20260912
```

* 各セルは**必要数を先頭から**取る（V=1→S1〜S12、V=2→S1〜S6、V=4→S1〜S3、
  V=6/8/12→S1〜S2）。
* **全セルが S1・S2 を共有**するので、d 方向・t 方向の比較が paired に近い構造を持つ。
* **スモーク帯（20260820〜20260829）と重ならない。** selftest が
  `min(MASTER_SEEDS) > 20260829` を検査する。

## (e) セル別 n 配分表

| | d=0 | d=1 | d=2 | d=3 | d=4 | 行計 |
| --- | --- | --- | --- | --- | --- | --- |
| **t=0** | 12 | 12 | 12 | 12 | 12 | 60 |
| **t=1** | 12 | 16 | 24 | 16 | 12 | 80 |
| **t=2** | 12 | 12 | 12 | 12 | 12 | 60 |
| **計** | | | | | | **200** |

モックで全格子を通し、**200標本ちょうど**、セル別 n が上表と一致、
**全セルで variant×seed が1回ずつ**（完全交差）であることを確認済み。

## (f) Actions／selftest が当該 SHA で green である証跡

```
ワークフロー: selftest
SHA:          28e2acca0c903e35cf6fe4aa8df55b2e9fff7e5e
status:       completed
conclusion:   success
URL:          https://github.com/beachcities/RoT/actions/runs/32931171510
```

各ステップの結果：

```
  Set up job: success
  Run actions/checkout@v4: success
  Run actions/setup-python@v5: success
  依存を入れる: success
  組を作り直して差分が出ないことを確かめる: success
  selftest: success
```

**手元でも `python selftest.py` は 98/98 passed。** GPU も実 API も使わない。
「組を作り直して差分が出ないことを確かめる」は、生成器 `build_v4.py` の出力と
リポジトリに置いてある組がずれていないことを毎コミット確かめる。

---

## 走行に入る前の宣言（GO後に実施する内容）

* 全15セル・**計200標本**、`Qwen/Qwen3.5-9B` thinking on、Colab CLI 経路（A100-40GB）、
  **一発勝負**、チェックポイントは標本ごと。
* コマンドは `python colab/drive_cli_run.py --model Qwen/Qwen3.5-9B --thinking on
  --suite v4_distribution --tasks task_06 --repeats 1 --max-attempts 1
  --commit 28e2acca0c903e35cf6fe4aa8df55b2e9fff7e5e ...`
  （`--repeats` はセル設計が上書きするので実効は無い。`--use-local` は付けない）
* エラー二分は従来どおり（測定ERR＝文脈長超過は引き継ぐ／基盤エラーは再実行）。

**この preflight で停止する。chat の照合と GO を待つ。**
