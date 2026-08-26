# 計器v2 本測定 preflight（差分b・2026-08-27）

## 決裁記録

> **(e) は選択肢2で決裁（山田・2026-08-27）。理由：凍結済みGO規則（①〜⑤が白なら
> SHA名指しでGO）に従い、未解決疑義のあるSHAにはGOしない。時間短縮は規則を緩める
> 理由にしない。疑義は許容と読み替えず、機械的に消してから本測定へ進む。**

前版 `notes/r1m-v2-main-preflight-20260827.md`（旧 `AUDITED_COMMIT=4d31ee0…`）の
(e) を消し込んだ差分。**旧 AUDITED_COMMIT では走行しない。**
タグ `instrument-v2.0` は動かしていない（パイロットの `e413a2a…` を指したまま）。

**本差分で停止し、GO を待つ。走行はしていない。**

---

## 1. 加えた監査変更

`.github/workflows/selftest.yml` に、**m1/m2 を再生成して commit 済みの組との差分0を
検証する段**を追加した。**既存のパイロット組の検査は変更していない**（別の段として
そのまま残っている）。

```yaml
      - name: 本測定の組を作り直して差分が出ないことを確かめる
        run: |
          python suites/build_v4_main.py
          git diff --exit-code -- suites/v4_distribution_m1 suites/v4_distribution_m2
          test -z "$(git status --porcelain -- suites/v4_distribution_m1 suites/v4_distribution_m2)"
```

**新しい段は untracked も見る**——既存段は `git diff` のみで、追跡されていない
ファイルは素通りする。今回のように組を新規追加した直後は「生成されたが commit
されていないファイル」が現実的な抜けなので、そこを塞いだ。既存段に手を入れて
いないのは、発注の「既存のパイロットsuite検査は変更しない」に従ったため。

**触れていないもの**：測定設計、生成ロジック、seed、生成済み suite の中身
（`v4_distribution_m1` / `_m2`）、集計ロジック。

**変更は1ファイル・11行の追加のみで、既存行の変更は0。**
複数ファイルには及んでいない。

## 2. 新しい AUDITED_COMMIT

```
AUDITED_COMMIT=0b8c3ae7ddf822aafbcde9034a41d58ae58ed699
```

**本 preflight 文書（`-20260827b.md`）は含まない。** 本文書の push によって
AUDITED_COMMIT は更新しない。

走行は `drive_cli_run.py --commit 0b8c3ae7ddf822aafbcde9034a41d58ae58ed699`、
**`--use-local` は使わない。**

## 3. Actions green の証跡（当該 SHA）

```
ワークフロー: selftest
SHA:          0b8c3ae7ddf822aafbcde9034a41d58ae58ed699
status:       completed
conclusion:   success
URL:          https://github.com/beachcities/RoT/actions/runs/33013551440
```

```
  依存を入れる: success
  組を作り直して差分が出ないことを確かめる: success            ← パイロット組
  本測定の組を作り直して差分が出ないことを確かめる: success      ← **m1/m2（今回追加）**
  selftest: success
  Complete job: success
```

**m1/m2 を含む再生成検査と selftest がいずれも green。**
手元でも同じ3検査（m1/m2 の差分0・untracked なし・パイロット組の差分0）が通り、
`python selftest.py` は 99/99 passed。

## 4. 旧 AUDITED_COMMIT からの差分と、未解決疑義

### 差分の内訳（`4d31ee0` → `0b8c3ae`）

**`benchmark/` 配下の差分は 0。** 測定に関わるコード・組・集計はいずれも動いていない。

| ファイル | 由来 |
| --- | --- |
| `.github/workflows/selftest.yml`（+11） | **本監査変更** |
| `notes/r1m-v2-main-preflight-20260827.md`（+152） | 前版 preflight（`f0cc0f7`、R1M） |
| `paper/CHANGELOG.md`（+5） | chat（`62d1e82`） |
| `paper/notes/section5-v2-reporting-plan.md`（+24） | chat（`62d1e82`） |
| `paper/return-on-token.md`（1行） | chat（`151ccce`） |
| `paper/return-on-token.en.md`（1行） | chat（`151ccce`） |

**事実として明記する**：本監査変更の作業中に上流が進み、chat 側の稿のコミット2本
（`62d1e82`, `151ccce`）が新 AUDITED_COMMIT の祖先に入った。**発注の「旧
AUDITED_COMMIT からの差分が本監査変更以外に無いこと」は、文字どおりには成り立って
いない**——ただし差分は稿と notes のみで、`benchmark/` は1バイトも動いていない。
新 SHA を main 上に置く以上これは避けられず、こちらの判断で履歴を書き換えることは
しなかった。**この SHA でよいかの確認は山田にお願いする。**

### 未解決疑義

**0件。** 前版の (e)（m1/m2 が CI の再生成検査の対象外）は本変更で消えた。
新たな疑義は生じていない。

## GO 後に実施する内容（宣言・前版から不変）

* **反復1（200標本）→ 正常完了した場合のみ反復2（200標本）**。計400標本。
* 各反復とも `--commit 0b8c3ae7ddf822aafbcde9034a41d58ae58ed699`、
  **`--use-local` 禁止**、一発勝負（試行上限1）、標本ごとチェックポイント。
  組はそれぞれ `v4_distribution_m1` / `v4_distribution_m2`。
* **停止条件**：ERR、チェックポイント異常、完全交差の崩れ、その他の凍結仕様からの
  逸脱。
* **停止条件にしないもの**：数値抽出不能の件数・率、観測結果そのものの値。
  **計器・走行の異常では止まり、結果の形では止まらない。**
* 区間途中で落ちた場合：取得済み標本を保持し、最後の有効な checkpoint から
  未取得分のみ続行。**同一標本の再生成・差し替えはしない。**
  区間が標本0で落ちた場合はその区間を破棄し、未取得分を次区間で走行。
* 報告は反復ごとに `notes/` へ、冒頭時刻形式＋要旨3行。

---

**この差分 preflight で停止する。山田の GO を待つ。**
