# ライセンス

このリポジトリは、収録物の種類によって異なるライセンスを適用します。

| 対象 | ライセンス |
| --- | --- |
| 文書（`paper/` 以下、および各 README） | [CC BY 4.0 International](https://creativecommons.org/licenses/by/4.0/) |
| コードおよびデータ（`benchmark/` 以下のスクリプト・JSON） | [Apache License 2.0](LICENSE) |

Copyright 2026 Masayuki Yamada

## 文書について

`paper/return-on-token.md` をはじめとする文書は CC BY 4.0 の下で提供します。出典を明示していただければ、複製・改変・再配布・商用利用のいずれも可能です。

## コードについて

`benchmark/` 以下のコードとデータは Apache License 2.0 の下で提供します。全文は [LICENSE](LICENSE) を参照してください。

## 測定結果に含まれるモデルの応答について

`benchmark/results/reference/` に置いてある結果ファイルには、**測定に用いたAPIが生成した応答の本文**が含まれます。採点をやり直したり、抽出規則を検証したりするために必要なので、そのまま残してあります。

これらの応答はモデルの生成物であり、リポジトリのライセンスが及ぶ範囲とは別に、**生成に用いたAPIの利用条件に従います**。応答本文を再利用する場合は、そちらを確認してください。どのランをどのモデルで走らせたかは [`benchmark/results/reference/RUNS.md`](benchmark/results/reference/RUNS.md) にあります。
