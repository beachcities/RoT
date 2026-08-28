# RoT — Return on Token

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22090097.svg)](https://doi.org/10.5281/zenodo.22090097)

計算資源の消費を、データ側から減らせるのではないか。その見立てを試論と極小ベンチマークにまとめ、検証可能な形で公開しているリポジトリです。

## 内容

| パス | 内容 |
| --- | --- |
| [`paper/return-on-token.md`](paper/return-on-token.md) | 試論本体（ディスカッション・ペーパー、公開固定版） |
| [`paper/return-on-token.en.md`](paper/return-on-token.en.md) | 英語版（下訳）。日本語版と食い違う場合は日本語版が正 |
| [`benchmark/`](benchmark/) | 仮説を検証する極小ベンチマークと全測定記録 |
| [`submission/dap/`](submission/dap/) | 学術誌投稿用の派生版（下記） |

## 試論の骨子

推論モデルの実行ログを読める範囲で読むと、思考の一部が、データ側に書かれていない前提（列名の意味、数値の単位、形式の不整合）に向かっている様子が観察できます。消費のどれだけがデータの記述の有無と共に動くのかは、実測すべき問いです。

そこで「投じたトークン総量に対してどれだけの成果が得られたか」を見る指標として **Return on Token（RoT）** を置き、データの自己記述性と共にこの指標が変わるという仮説を検証します。分母には探索で捨てられた再帰性トークンも算入します——この試論の仮説の下では、捨てられた探索の大きさは、データ側が供給しなかった文脈の重さを映すと考えられるためです。

この関係が実データでも成り立つなら（移転は未測定です）、オープンデータの評価に「利用時の推論消費をどれだけ減らすか」という候補軸が加わり得ます。

## 公開固定版 v0.2.0

v0.2.0時点の試論と測定成果を **Frozen Public Release** として固定しています。

- タグ: [`v0.2.0`](https://github.com/beachcities/RoT/releases/tag/v0.2.0)／コミット: `d483d6b726fe83fe47cef471270e3982224402bc`
- Version DOI（v0.2.0そのもの）: [10.5281/zenodo.22136254](https://doi.org/10.5281/zenodo.22136254)
- Concept DOI（全版を束ね、常に最新版を指す）: [10.5281/zenodo.22090097](https://doi.org/10.5281/zenodo.22090097)

固定版の本文は表記「ROT」のまま変更しません。本READMEと投稿派生版では「RoT」表記を用います。

## 主要結果（v0.2.0時点・測定系列別）

数値は系列内でのみ比較し、系列間で統合していません。詳細と全記録は試論第5節と `benchmark/` を参照してください。

- **リトライ方式・参照経路（基準比較）**：gpt-4o-mini、gpt-4.1-mini、gpt-5.4、Olmo-3-7B-Thinkの4システムでは、主課題は必要なコード意味が文書内にないl0–l5で一度も解かれず、l6では初回に解かれました。l5→l6の総消費の段差は14.5〜30.2倍でした。追加のthinking-toggleと小型モデルによる確認は下記のrobustness結果として別に扱います。
- **5反復ローカル経路**（別機材・別経路。Olmo、Qwen 9B thinking有効/無効の3システム）：境界は同位置。段差22〜33倍に対し、水準内の振れは最大2.7倍でした（記述統計としての比較です）。
- **約1/4のパラメータ数・1反復**：段差8.5倍。l6・l7・l9は解けた一方、l8（レコード内フラグ）は両課題とも10試行で失敗しました。この構成は思考挙動も異なり反復も1回のため、容量単独には帰属できません。
- **一発分布の計器**（別実装。リトライ系列と数値統合しません）：対象となる2つの意味が明示されたt=2の5セルは、pilot・confirmatory反復1・反復2の3走行すべてでcorrect-peak 1.00、abstention 0.00でした。一方、t≤1のセル値は独立反復間で安定せず、事前に凍結したfitの前提条件は4つのrepeat×sectionすべてで未達だったため、fitは実行されず「no fit established」を正式な結果として記録しています。
- **思考文の観測**：思考が読めるローカル1系統では、失敗試行の16〜19%（分類規則により1〜23%）がデータ側の欠落への言及・当て推量に分類されました。観測と解釈であり、消費の因果分解ではありません。
- **要件の逆算**：失敗試行の思考から候補要件を導くrule-basedの手続きをトイ課題上で実行できました（実運用ログでは未検証）。

**実データへの移転は未測定です。** 測定の経緯と訂正の履歴（撤回記録を含む）は [`paper/CHANGELOG.md`](paper/CHANGELOG.md) にあります。

## 投稿準備中の派生版

[`submission/dap/`](submission/dap/) で、*Data & Policy*（Cambridge University Press）standard trackのResearch Articleとして投稿する準備を進めています。v0.2.0から派生した英語原稿で、固定版のファイルは変更しません。

## このリポジトリについて

これは個人として進めている試論であり、いかなる組織の見解を示すものでもありません。運営も個人の時間で行っているため、Issue や Pull Request への対応は不定期になります。その点をご了承のうえでお寄せいただければ幸いです。

## 引用

本試論・測定（v0.2.0）を引用する場合はVersion DOIを、常に最新版を指したい場合はConcept DOIをお使いください。

> Yamada, Masayuki (2026). *RoT — Return on Token: A Discussion Paper on Reducing Compute Waste from the Data Side* (v0.2.0). Zenodo. https://doi.org/10.5281/zenodo.22136254

> Yamada, Masayuki (2026). *RoT — Return on Token: A Discussion Paper on Reducing Compute Waste from the Data Side.* Zenodo. https://doi.org/10.5281/zenodo.22090097

## フィードバックのお願い

概念の精緻化、計測手法への批判、タスクセットの拡充、実データの提供、共同での実証——いずれも歓迎します。Issue または Pull Request でお寄せください。

## ライセンス

文書は [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)、コードとデータは [Apache License 2.0](LICENSE) の下で提供します。詳細は [LICENSE-NOTICE.md](LICENSE-NOTICE.md) を参照してください。

Copyright 2026 Masayuki Yamada
