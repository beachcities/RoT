# v2d_tax — 手がかりの記録（既定の組）

v2b に **消費税額（円建て）** を足したもの。業種と活動状態の手がかりは v2a と同じ。

| 埋めるべき文脈 | self_descriptive での与え方 | raw に置いた手がかり |
| --- | --- | --- |
| `cd` が業種を表すこと | `industry_code` + `industry_name` | 社名（Systems / Networks / Data Service が `cd=101` で一致、Foods が 201、Metal Works が 202） |
| `flg` / `end_dt` が活動状態を表すこと | `is_active_entity` + `closure_date` と定義文 | `end_dt` が入っている行だけ `flg="N"`。全行で一貫 |
| `val_24` の単位（百万円） | `unit_definition` に明記 | `tax_24`（消費税額、円建ての生の値）。全行で `tax_24 / val_24 = 100000` がちょうど成立する。税率10%に気づけば `val_24` の単位が百万円と**一意に**決まる。補助として `emp` と `cap` |

**単位そのものは raw のどこにも書いていない。** 書いてあるのは別のフィールドの値だけで、
比を取って初めて単位が決まる。

## この組を既定にした理由

* 実測（gpt-4o-mini、最終版のプロンプト、REPEATS=2 と 3、raw n=15）: raw 正答 2/15、self_descriptive 15/15。
  raw 側が 0% でも 100% でもない範囲に入っている。
* v2c_anchor は raw 3/15 とわずかに高いが、この差は 15 試行では区別できない。
  v2c の手がかりは外部知識の記憶に依存し、モデル間比較に交絡が入るため採らなかった（判断であって実測ではない）。

## 既知の弱点

* `tax_24` を足したことで、`fiscal_year_2024_consumption_tax_yen` を売上と取り違える誤答が
  self_descriptive 側でも一度観測されている（推論を許す前の版）。手がかりは同時に紛れ込みでもある。
* raw 正答率 2/15 は低い。REPEATS=5（raw n=15）でも正答は数件しか出ないため、ROT 比のばらつきは大きい。
