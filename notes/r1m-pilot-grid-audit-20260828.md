# artifact 整合性監査：pilot 格子14行の件（2026-08-28）

**発注時刻：取得不能**（R1M 側で機械取得できないため、推定していない）。
作業開始 **2026-08-28T01:55:06Z**、完了 **2026-08-28T02:10:xxZ**、
**所要 約15分**（開始・完了とも `date` によるシステム時刻の機械取得。差から算出）。

**新規測定・モデル呼び出し・GPU 使用なし。課金 $0。**

---

## 1. 原因

**対象ファイルは `benchmark/results/reference/runs/20260826T132218Z.md`**
（`git show 4bbbd47 --stat` で機械特定。当該コミットで唯一「行が消えた」ファイルで、
`14 -` の削除のみ）。

**原因は、生成 markdown と手追加部分の衝突。**

* ラン記録は `benchmark/make_run_records.py` が生成する。
  同スクリプトは `out.write_text(render_record(run, note), ...)` で
  **記録ファイルを毎回まるごと上書きする**（追記ではない）。
* パイロット報告時（`7f07be0`）、格子は `render_record()` の出力に**含まれておらず**、
  こちらが生成後に**手で追記**していた。
* 反復1の報告時（`4bbbd47`）、台帳登録のため `make_run_records.py` を再実行した。
  その時点で記録が作り直され、**手追記だった14行が上書きで消えた**。

**混入・改竄ではなく、生成器の上書きと手追記の衝突。**
消えた14行は「## 格子（テキスト版）」の見出し・説明文・格子本体・凡例のみ。

## 2. JSON 値への影響の有無

**影響なし。**

* `4bbbd47` が触った JSON は `benchmark/results/reference/run_20260827T060549Z.json`
  の**新規追加のみ**（26,045行の追加、削除0）。
* パイロットの正本 `run_20260826T132218Z.json` は
  **`7f07be0` で追加されて以降、一度も変更されていない**（`git log --follow` で確認）。
* `trials.csv`・`RUNS.md`・`*_distribution.txt`・`*_grid.html` にも
  当該コミットでの値の変更はない。
* **消えた14行の内容は、正本 JSON から機械再現した結果と完全一致した**（下記4）。
  すなわち**表示が失われただけで、値は失われていない**。

**数値差・新しい科学的論点は見つからなかった。**

## 3. 修正内容（実 diff）

**重要：この修正は `benchmark/` 配下に出る。発注の「修正は notes/ 配下のみ」に
反するため、検証だけ行い、作業ツリーには適用していない（`git checkout -- benchmark/`
で戻し済み）。** 記録対象のラン記録も生成器も `benchmark/` にあり、
**notes/ 配下だけでは直せない**——この点の判断は山田にお願いする。

検証済みのパッチは `notes/pilot-grid-audit/make_run_records_grid.patch` に保存した。

```diff
--- a/benchmark/make_run_records.py
+++ b/benchmark/make_run_records.py
@@ -118,6 +118,32 @@ def table(rows):
+def grid_lines(run):
+    """計器v2 の格子をテキストで載せる。**HTML が開けない場所のために併存させる。**
+
+    以前は生成後に手で継ぎ足していたが、この生成器は記録を毎回丸ごと書き直すので
+    次の再生成で消えていた（4bbbd47 で実際に消えた）。**格子は結果 JSON から
+    機械再現できる**ので、生成の側に置く。格子を持たない組では何も足さない。
+    """
+    if not run.get("condition_spec"):
+        return []
+    try:
+        import v4_grid
+        cells = v4_grid.collect(run)
+    except Exception:
+        return []
+    if not cells or all(c.get("t") is None for c in cells.values()):
+        return []
+    # 併記する HTML が無い記録には載せない（存在しない先を指してしまう）。
+    html_name = f"{run.get('run_at')}_grid.html"
+    if not (Path(__file__).resolve().parent / "results" / "reference" / "runs" / html_name).exists():
+        return []
+    return ["", "## 格子（テキスト版）", "",
+            f"同じ内容の一枚 HTML は `{run.get('run_at')}_grid.html`。"
+            "**HTML が開けない場所のために併存させている。**", "",
+            "```", v4_grid.text_grid(cells), "```"]
+
@@ -146,6 +172,7 @@ def render_record(run, ledger_note=""):
     run_only = summarize.run_caveats(summary)
     lines += (["```"] + run_only + ["```"]) if run_only else ["（なし）"]
+    lines += grid_lines(run)
     return "\n".join(lines) + "\n"
```

**単に14行を手で戻すのではなく、生成器の側に置いた。** 手で戻すと、次に
`make_run_records.py` を回した時点でまた消える——今回と同じことが再発する。

適用したときの差分（検証時に実測）：

```
 benchmark/make_run_records.py                      | 27 ++++++++++++++++++++++
 .../results/reference/runs/20260826T132218Z.md     | 14 +++++++++++
 .../results/reference/runs/20260827T060549Z.md     | 14 +++++++++++
 3 files changed, 55 insertions(+)
```

**`*.json`・`trials.csv`・`RUNS.md`・`*_distribution.txt`・`*_grid.html` に差分は出ない**
（`git status` で確認）。実測値は一切動かない。

### 検証中に見つけた副作用（対処済み）

素朴に格子を足すと、**スモーク記録（`20260826T030829Z.md`）にも格子が付き、
存在しない `20260826T030829Z_grid.html` を指す**（当該 HTML は
`results/reference/runs/` に無い）。上のパッチではこれを機械規則で塞いだ——
**併記する HTML が実在する記録にだけ載せる**。結果、変わるのは
パイロットと反復1の2件だけになる。

## 4. 再生成後も14行が保持されるか

**保持される。**

* パッチ適用後に `make_run_records.py` を**3回**回し、3ランすべてで
  `## 格子（テキスト版）` が **1回だけ**現れることを確認（重複追記もしない）。
* パイロット記録の格子部分を `4bbbd47^`（消える前）と突き合わせ、**完全一致**。
* `python selftest.py` は **99/99 passed**。

**格子が正本 JSON から機械再現できることも独立に確認した。**
再現スクリプトを `notes/pilot-grid-audit/regenerate_grid.py` に保存した
（**正本 JSON を読むだけで、何も書き換えない**）。

```
python notes/pilot-grid-audit/regenerate_grid.py benchmark 20260826T132218Z
```

の出力は、`4bbbd47^` の消えた14行と**完全一致**した（改行コードを正規化して比較。
差は CRLF/LF のみだった）。

## 5. 最終 HEAD

* 監査開始時の HEAD：`569eabc`
* **`benchmark/` は無変更のまま**（`git checkout -- benchmark/` で戻し、`git status` clean）。
* 本報告と検証成果物（`notes/pilot-grid-audit/`）のみを push。
* **push 後の HEAD は本コミットの SHA**（下記「push 結果」に記載）。

---

## 保存した成果物

| ファイル | 内容 |
| --- | --- |
| `notes/pilot-grid-audit/make_run_records_grid.patch` | 検証済みの最小修正（**未適用**） |
| `notes/pilot-grid-audit/regenerate_grid.py` | 正本 JSON から格子を再現する読み取り専用スクリプト |
| `notes/pilot-grid-audit/restored_14_lines.txt` | 再生成された格子（消えた14行と一致するもの） |
| `notes/pilot-grid-audit/20260826T132218Z_regenerated.md` | パッチ適用時に生成される記録の全文（参考） |

## 触れていないもの・読めなかったもの（推測と明示）

* **修正を作業ツリーに適用していない。** 発注の「修正は notes/ 配下のみ」と、
  修正対象（`benchmark/make_run_records.py` と `results/reference/runs/*.md`）の
  所在が食い違うため、**範囲を広げる判断はしなかった**。適用の可否は山田の手番。
* **`benchmark/` の実測値は一切変更していない**（発注どおり）。
* **正本 JSON の値を変更・再解釈していない**（発注どおり）。
* **モデルは一度も呼んでいない。GPU も Colab も使っていない。**
* 4bbbd47 で他に消えた行は無い（`git show --stat` の削除は当該14行のみ）。
* **反復2の記録（`20260827T144958Z.md`）は、パッチ適用後も差分が出なかった**——
  手追記した格子が生成結果と偶然一致していたため。**この一致は確認したが、
  なぜ完全に一致したかまでは追っていない**（同じ関数で生成した文字列を
  同じ体裁で貼ったためと見られるが、**推測**）。

## 実行して確かめたことと、推測の区別

**確かめたこと**：対象ファイルの機械特定、削除された14行の内容、
`make_run_records.py` が全上書きであること、パイロット JSON が `7f07be0` 以降不変で
あること、`4bbbd47` の JSON 変更が新規追加のみであること、格子が正本 JSON から
再現でき消えた14行と完全一致すること、パッチ適用後3回の再生成で保持されること、
selftest 99/99、スモーク記録への副作用とその封じ込め、JSON・実測値に差分が出ないこと。

**推測にとどまること**：反復2の記録に差分が出なかった理由。
