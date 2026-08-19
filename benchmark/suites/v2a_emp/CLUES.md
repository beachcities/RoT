# v2a_emp — 手がかりの記録

raw 側に置いた手がかりは **従業員数のみ**。

| 埋めるべき文脈 | self_descriptive での与え方 | raw に置いた手がかり |
| --- | --- | --- |
| `cd` が業種を表すこと | `industry_code` + `industry_name` | 社名（Alpha **Systems** / Gamma **Networks** / Epsilon **Data** Service が同じ `cd=101`、Beta **Foods** が 201、Delta **Metal** Works が 202）。3件が一致するので帰納できる |
| `flg` / `end_dt` が活動状態を表すこと | `is_active_entity` + `closure_date` と定義文 | `end_dt` が入っている行だけ `flg="N"`。対応関係が全行で一貫している |
| `val_24` の単位（百万円） | `unit_definition` に明記 | `emp`（従業員数）だけ。40人の企業の年商が 1200 **円** では常識に反する、という間接的な手がかり |

単位の手がかりが常識依存で、値が一意に決まらない（千円か百万円かを絞れない）。

実測（gpt-4o-mini、最終版のプロンプト、REPEATS=2、raw n=6）: raw 正答 1/6、self_descriptive 6/6。
