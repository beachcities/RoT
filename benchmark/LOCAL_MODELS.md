# ローカルで回す推論モデルの調査（2026-08-23 時点）

API 経由の3モデル（gpt-4o-mini / gpt-4.1-mini / gpt-5.4）は `reasoning_tokens` が
いずれも 0 で返り、中間推論の長さを分離できなかった。稿の第5節「測れていないこと」の
筆頭がこれである。オープンウェイトの推論モデルを自前で回せば `<think>` の中身が
生で取れる。以下は**実際に入手できるかを Hugging Face 上で確かめた**結果。

## OSI のオープンソースAI定義に照らした区別

[OSI の Open Source AI Definition (OSAID) 1.0](https://opensource.org/ai/open-source-ai-definition)
は、重みだけでなく**学習コードと学習データの情報**を求める。データについては
「技術者が実質的に同等のシステムを構築できる程度に詳細」であることを要求しており、
出所・フィルタ規則・重複除去・トークナイズ・混合比・入手経路までが対象になる。

したがって次の二つは別物として扱う。

| 区分 | 意味 |
| --- | --- |
| **完全オープン** | 重み・学習コード・学習データが揃って公開されている。OSAID を満たす |
| **オープンウェイト** | 重みのみ公開。学習データは非公開。OSAID を満たさない |

**調査の結果、当初の見込みは外れた。完全オープンの系統に推論モデルは存在する。**

Ai2 の OLMo 3 系統には Think（推論）版が **7B と 32B の2サイズ**あり、
Apache-2.0 で、事後学習に使った Dolci データセット群も公開されている。
OSAID を満たす系統は現状 OLMo がほぼ唯一とされる
（[Moesif](https://www.moesif.com/blog/technical/api-development/Open-Source-AI/) /
[futureagi](https://futureagi.com/blog/open-source-vs-open-weight/) /
[GEO Toolbox](https://geotoolbox.ai/blog/open-weights-vs-open-source) の各解説、
および [Wikipedia: Open-source artificial intelligence](https://en.wikipedia.org/wiki/Open-source_artificial_intelligence)）。

## 候補

### 完全オープン（OSAID を満たす）

| モデル | 規模 | ライセンス | 学習データ | `<think>` |
| --- | --- | --- | --- | --- |
| [allenai/Olmo-3-7B-Think](https://hf.co/allenai/Olmo-3-7B-Think) | 7.3B | Apache-2.0 | `Dolci-Think-SFT-7B` / `-DPO-7B` / `-RL-7B` を公開 | あり（`<think>…</think>`、モデルカードに実例） |
| [allenai/Olmo-3.1-32B-Think](https://hf.co/allenai/Olmo-3.1-32B-Think) | 32.2B | Apache-2.0 | `Dolci-Think-SFT` / `-DPO` / `-RL` を公開 | 同上 |
| [allenai/Olmo-3-32B-Think](https://hf.co/allenai/Olmo-3-32B-Think) | 32.2B | Apache-2.0 | 同上 | 同上（3.1 の前版） |

**同一系統でサイズ違いが2つ取れる。** 能力に幅を持たせたいという条件を満たす。

### オープンウェイト（重みのみ）

| モデル | 規模 | ライセンス | 学習データ | `<think>` |
| --- | --- | --- | --- | --- |
| [Qwen/Qwen3.5-9B](https://hf.co/Qwen/Qwen3.5-9B) | 9.7B | Apache-2.0 | 非公開 | あり。既定で thinking モード。`enable_thinking: false` で切れる |
| [Qwen/Qwen3.8-27B](https://hf.co/Qwen/Qwen3.8-27B) | 27.8B | Apache-2.0 | 非公開 | 同上 |
| [Qwen/Qwen3.5-2B](https://hf.co/Qwen/Qwen3.5-2B) 系 | 2B | Apache-2.0 | 非公開 | 同上 |
| [llm-jp/llm-jp-4-33b-thinking](https://hf.co/llm-jp/llm-jp-4-33b-thinking) | 33.2B | Apache-2.0 | 未確認 | 名称上は thinking。日英 |

Qwen 側は**思考の有無を切り替えられる**という利点がある。同一モデルで
thinking on/off を比べれば、CoT の寄与を直接分離できる。ただし学習データは非公開で、
OSAID は満たさない。

## `<think>` を取り出す経路

vLLM と SGLang は `--reasoning-parser` を持ち、これを付けると OpenAI 互換の応答が
`message.reasoning_content` に思考部分を分けて返す。`usage.completion_tokens_details.
reasoning_tokens` も埋まる。既存の記録経路（`reasoning_tokens`）とそのまま噛み合う。

```
vllm serve allenai/Olmo-3-7B-Think --port 8000 --reasoning-parser deepseek_r1
vllm serve Qwen/Qwen3.5-9B         --port 8000 --reasoning-parser qwen3
```

パーサを付けない場合、`<think>…</think>` は `content` にそのまま残る。
**両方に対応する**（`reasoning_content` があればそれを使い、無ければ本文から切り出す）
のが素直で、API 経由のモデルではどちらも現れないので従来どおり `null` になる。

## 実行環境と所要の見積もり

この試験は**逐次に1リクエストずつ**投げる。バッチではないので、ローカル推論では
1ストリームあたりの復号速度がそのまま所要時間になる。

* 1モデルあたり 100 実行（10水準 × 2タスク × 5反復）
* `task_06` の `l0`〜`l5`（30実行）は API の3モデルとも上限10試行に張り付いた。
  ローカルでも同様なら、1実行あたり10回の生成が要る
* 推論モデルは `<think>` を長く書く。1回の生成で数百〜数千トークン

| モデル | GPU | 1ストリームの目安 | 100実行の所要（逐次） |
| --- | --- | --- | --- |
| Olmo-3-7B-Think | A100 40GB（Colab Pro+ で載る） | 50〜70 tok/s | **2〜3時間** |
| Olmo-3.1-32B-Think | A100 80GB / H100（40GB には bf16 で載らない） | 15〜25 tok/s | **8〜10時間** |

32B は逐次のままでは長すぎる。反復5回を**並行**に投げれば vLLM のバッチが効いて
3〜4倍速くなる見込みだが、ランナーを同時実行に対応させる改修が要る。

RunPod の on-demand は A100 80GB が $1.39/hr、H100 PCIe が $2.89/hr
（[GPUPerHour](https://gpuperhour.com/providers/runpod) / [Spheron](https://www.spheron.network/blog/runpod-h100-pricing-2026/)）。
Colab Pro+ の A100 は 40GB で、7B は載るが 32B は載らない。

## 未確認

* `llm-jp-4-33b-thinking` の学習データ公開状況（llm-jp は corpus を公開してきた系統だが、
  このモデルについては確認していない）
* Olmo-3 Think の実際の `<think>` の長さ。1回の生成で何トークン書くかは測っていない
* ローカルでの復号速度。上の tok/s は一般的な目安であって、この環境での実測ではない
* `l6` 以降でこれらのモデルが解けるかどうか。解けなければ測定が成立しない

---

# 第1段の実測（2026-08-23、Colab Pro+ A100 40GB、Olmo-3-7B-Think）

`vllm serve allenai/Olmo-3-7B-Think --max-model-len 16384 --gpu-memory-utilization 0.90`
に対し、`v3_levels` の `task_04` / `task_06` を `REPEATS=1`、`MAX_ATTEMPTS=10` で走らせた。

## 環境構築で踏んだもの

| 事象 | 対処 |
| --- | --- |
| Colab イメージの torch (CUDA 13.0) と torchaudio (12.8) が食い違い、vLLM の import が落ちる | `torchaudio` を削除。テキスト推論には要らない |
| `--reasoning-parser deepseek_r1` が起動失敗（`<think>` が単一トークンでないと使えない） | パーサ無しで起動。**「1件も登録されていない」と書いたのは誤り**（→ 下の「パーサについての訂正」） |
| `colab exec` の既定タイムアウトが30秒 | `--timeout` を明示 |
| A100 は CLI 経路では 40GB、セッションは 61.5 分で切れる | プローブに切り分けた |

モデルの読み込みに 240 秒。

## `<think>` の取り出し方が1通り足りなかった

**開始タグはチャットテンプレート側にあり、生成には終了タグしか現れない。**
`<think>…</think>` の対を探す実装では拾えず、思考を含んだ本文がそのまま会話履歴に
積まれて、5〜8試行で 16k の文脈長を使い切っていた（`400 BadRequest`）。
終了タグだけの場合も拾うようにして解決した。取り出し方は3通りある。

1. `reasoning_content` に分かれて返る（`--reasoning-parser` 付きのサーバ）
2. `<think>…</think>` が本文に対で現れる
3. **終了タグだけが現れる**（開始タグはプロンプト側）← Olmo-3-7B-Think はこれ

## 測定は成立する（情報がある水準では）

| 水準 | タスク | 正答 | 試行 | 総token | 思考の文字数 |
| --- | --- | --- | --- | --- | --- |
| `l6_codes_doc` | `task_04` | ○ | 1 | 2,693 | 2,099 |
| `l6_codes_doc` | `task_06` | ○ | 1 | 3,471 | 4,204 |
| `l9_prose` | `task_04` | ○ | 1 | 3,206 | 記録前の実行 |
| `l9_prose` | `task_06` | ○ | 1 | 3,490 | 記録前の実行 |

`l6` 以降は1試行で解けており、**この規模のモデルでも測定は成立する**。

## 情報が無い水準では思考が発散して打ち切られる

| 水準 | タスク | 状態 | 試行 | 1試行目の思考 | 2試行目 |
| --- | --- | --- | --- | --- | --- |
| `l0_opaque` | `task_06` | error（文脈長超過） | 4 | **27,274字** | **52,625字** |
| `l5_codes_ref` | `task_06` | error（文脈長超過） | 2 | — | — |

`l0` の1試行目の思考の末尾はこうなっている。

> …but since cd201 is not specialized services, the assumption must exclude it,
> so only cd=101 is specialized. Thus, I'll go with 198 as the answer.

**書かれていない対応関係を推し量ろうとして、数万字にわたって候補を潰している。**
API 経由の3モデルでは `reasoning_tokens` が 0 で返り、この過程は一切見えなかった。

ただし**この状態では測定として完結しない**。`status=error` となり集計から除外される。
本実行には `--max-model-len` を広げる（Olmo 3 のモデルカードは `max_new_tokens=32768` を
挙げている）か、1リクエストあたりの `max_tokens` を切る必要がある。

## 速度

`l6` の2セル（生成 544 + 1,307 トークン）で 28 秒。**約 66 tok/s**（1ストリーム、A100 40GB）。
事前の見積もり 50〜70 tok/s の範囲内だった。

一方、思考が発散する水準では1試行あたり 577 秒かかっている。**所要は正答率ではなく
「思考が終わるかどうか」で決まる。**

## 本実行の見積もりへの影響

`l0`〜`l5` の思考が発散するため、**当初の「2〜3時間」は下振れである**。文脈長を広げれば
1試行あたりの生成がさらに伸びる。CLI 経路のセッション上限 61.5 分には収まらない。

---

# 本実行の結果（`run_20260823T124213Z.json`）

Colab の A100 で `allenai/Olmo-3-7B-Think` を vLLM で回した。132分、20実行、除外0件。
`REPEATS=1`、`MAX_ATTEMPTS=10`、生成上限 32,768（**一度も到達しなかった**）。

**入力の指紋が API の参照点3ランと一致している**（`inputs=dea1a8ccce8dbbad`、
`prompt=3614fb04597c534a`）。コミット `c873038`、`dirty=false`。

## 水準ごと

| 水準 | `task_04` | `task_06` | 総token中央 | 試行中央 | 思考字数中央 |
| --- | --- | --- | --- | --- | --- |
| `l0_opaque` | 1/1 | **0/1** | 74,288 | 6.0 | 214,636 |
| `l1_names` | 1/1 | **0/1** | 60,790 | 5.5 | 174,818 |
| `l2_units_ref` | 1/1 | **0/1** | 62,438 | 5.5 | 187,837 |
| `l3_units_doc` | 1/1 | **0/1** | 64,850 | 6.0 | 197,018 |
| `l4_units_record` | 1/1 | **0/1** | 57,262 | 5.5 | 172,594 |
| `l5_codes_ref` | 1/1 | **0/1** | 52,270 | 5.5 | 151,416 |
| `l6_codes_doc` | 1/1 | **1/1** | 2,996 | 1.0 | 2,796 |
| `l7_codes_record` | 1/1 | 1/1 | 3,304 | 1.0 | 3,485 |
| `l8_flags_record` | 1/1 | 1/1 | 3,186 | 1.0 | 3,160 |
| `l9_prose` | 1/1 | 1/1 | 3,466 | 1.0 | 3,402 |

`task_06` は `l0`〜`l5` が 0/1・上限10試行、`l6` 以降が 1/1・1試行。
`CoT`（`reasoning_tokens`）は全水準 `n/a` のまま。パーサ無しの vLLM は返さない。
**思考は文字数として取れている。**

## 思考テキストから読めたこと

### `l0_opaque` / `task_06` の10試行 — 同じ推測の繰り返しではない

回答は 249 → 249 → 264 → 264 → 719 → 943 → 1149 → 943 → 943 → 826 と動いた。
思考は合計 404,407 字。1試行目の冒頭で、欠けているものを名指ししている。

> The problem is, the data doesn't list the industry type for each company.
> The fields available are id, cd, nm (name), emp (number of employees)…

そのうえで、`cd` を独自に分類し直す作業を毎回やり直している。

> JIC10 (academic/research): cd101 →65 / JIC40 (specialized service): cd404 →81 /
> JIC70 (specialized service: professional/scientific): cd707 →103
> Total specialized service:81+103=184; total both industries:184+65=249.

2試行目は別の分割を試し、探索が尽きたことを自分で述べている。

> I think I've exhausted all angles and without explicit industry coding info,
> the best estimates I can make point to 183 as a likely answer.

後半は、データではなく**出題者の意図を推し量る**方向に転じる。

> Given the user's relentless insistence on a number and the latest correct calculation
> for specialized being 943 when including CD201, I'll proceed with that as the answer
> they expect.

社名のギリシャ文字にも気づいている（`based on CD and Greek letter names`）。

### `l5_codes_ref` — 参照は認識され、辿れないことも自覚されている

外部参照だけを張った水準で、モデルは **URL を名指しし、アクセスできないと明言**した。

> Ah, maybe in the initial code_list_reference (https://example.gov/codes/jsic_internal_v1.json),
> the industry codes are defined with their names. But since the user hasn't provided the
> content of that file, I can only go off the data provided.

> Since I can't see the external code list (code_list_reference is a url, which I can't access),
> I need to rely solely on the given data and common sense.

**参照を張ることと、届くことは別である**という区別が、思考の中で明示的に成立している。
それでも解けず、10試行・279,148字を費やしている。

### `l6_codes_doc` — 探索が消える

同じ課題が1試行・3,311字で解けている。冒頭がこうなっている。

> The problem states that the two sectors we're interested in are industry codes 707 and 505.
> **Let me confirm that from the code_definition. Yes, looking at the code_definition array:
> 707 is "専門サービス業" and 505 is "学術研究業".**

以降は突き合わせと足し算だけで、仮説の生成が一度も起きていない。
**`l5` の 151,416 字と `l6` の 2,796 字の差は、この一回の参照で消えている。**

### `task_04` が2試行かかった箇所

* `l0_opaque` 試行1: 業種の制約を無視して全社を合計し **1,149**（`40+120+15+310+…+27=1149`）。
  試行2で社名から `cd=101` を情報通信業と判断し 80。
* `l3_units_doc` 試行1: `cd=101` に加えて `cd=404` も含めて **161**。
  試行2で「404 は対象業種ではない」と判断し直して 80。

> the initial 161 was incorrect because it included industry 404 companies which aren't
> part of Information Communication according to the industry codes corresponding to those names.

API の3モデルでは `task_04` は全水準で平坦だった。7B では社名からの推測が安定しない。

## 要求仕様の逆算（試論 第6節の検証）

`derive_requirements.py` が、報告に書いた4段階をそのまま実行する。

```bash
python derive_requirements.py results/reference/run_20260823T124213Z.json --show 2
```

| 段階 | 関数 | 内容 |
| --- | --- | --- |
| 1. 抽出 | `extract` | 失敗した試行の思考から「欠けている」と述べた文を拾う |
| 2. 束ね | `bucket` | どのフィールドが無いと言っているかで束ねる |
| 3. 書き出し | `requirements` | 束を要求仕様の文言として書き出す |
| 4. 確認 | `verify` | 書き足した水準で言及が消えるかを、**同じ抽出器で**数える |

**4 が検証にあたる。** 抽出器を変えずに前後を数えるのが要点で、別の基準で数え直すと
検証にならない。

### 抽出の三段の関門

引き金（下の正規表現）に当たった文を、そのまま採るのではない。**引き金の直前の主語**と、
**記述を指す語があるか**で振り分ける。最初の版はこれをやっておらず、要求仕様にならない文が
束に混ざっていた。

| 関門 | 落とすもの | 理由 |
| --- | --- | --- |
| 主語が問い・出題者 | `The question doesn't specify whether to include closed companies` | 課題の曖昧さであって、データ側の欠落ではない |
| 主語が判別できない | — | 何について言っているか決められない |
| 記述を指す語が無い | `the dataset doesn't have any companies in the academic research sector` | データの中身についての観察であって、自己記述性の話ではない |

### 引き金の正規表現

```
(?:doesn't|does not|didn't|did not) (?:list|have|specify|provide|include|define|contain)
|(?:isn't|is not|aren't|are not|wasn't) (?:provided|specified|given|available|included|defined|listed)
|no (?:explicit|clear)? ?(?:mapping|label|labels|definition|definitions|key)
|lack(?:s|ing)? (?:of )?(?:a )?(?:clear |explicit )?(?:mapping|definition|labels?)
```

### 束ねは先勝ちにしない

一致した語の数で採点し、最も多い束に入れる。**先勝ちにすると、たまたま先に並んでいる束の語が
1つ入っただけで持っていかれる。** 実測で、コードの意味が無いと述べた文が `external` の一語で
外部参照の束に入っていた。

### 逆算された要求仕様（失敗した試行のみ）

| 段階 | 件数 |
| --- | --- |
| 引き金に当たった箇所 | 191 |
| 　主語が問い・出題者 → 落とす | 101 |
| 　主語が判別できず → 落とす | 62 |
| 　中身の話 → 落とす | 18 |
| **採った文** | **10** |

| 束 | 件数 | 書き出された仕様 |
| --- | --- | --- |
| `industry_code_meaning` | **9** | 業種コードの意味（コード → 業種名の対応表）を、データ本体に書く |
| `unit` | 0 | — |
| `activity_status` | 0 | — |
| `external_reference` | 0 | — |
| （分類できず） | 1 | — |

**このランから逆算される要求仕様は1つだけである。** `unit` と `activity_status` が0件なのは、
このランの2つの課題（`task_04` / `task_06` = 従業員数を数える問い）が、単位も活動状態も
必要としないため。**逆算が課題に依存して動いている**ことになる。

根拠の文（そのまま）:

> The problem is, **the data doesn't list the industry type** for each company.
> But **the dataset doesn't have explicit labels for these industries**.
> Since **the data doesn't have industry labels**, I have to rely on the company names…
> Alternatively, since **the data doesn't specify the mappings for the industry codes**…

### 4. 確認 — 水準ごとの言及件数

| 水準 | 正答 | 思考字数 | 言及 |
| --- | --- | --- | --- |
| `l0_opaque` | 1/2 | 429,273 | 3 |
| `l1_names` | 1/2 | 349,637 | 2 |
| `l2_units_ref` | 1/2 | 375,674 | 1 |
| `l3_units_doc` | 1/2 | 394,037 | 2 |
| `l4_units_record` | 1/2 | 345,187 | 3 |
| `l5_codes_ref` | 1/2 | 302,832 | 1 |
| **`l6_codes_doc`** | **2/2** | **5,593** | **0** |
| `l7_codes_record` | 2/2 | 6,970 | 0 |
| `l8_flags_record` | 2/2 | 6,321 | 0 |
| `l9_prose` | 2/2 | 6,803 | 0 |

`l6` で `code_definition`（コード → 業種名の対応表）を足したところで言及が消える。
逆算された唯一の仕様が指していたものが、まさにこれである。

### 最初の版の欠陥（記録として残す）

**見出しと、その下に並ぶ根拠の文が対応していなかった。** 表示の不具合ではなく、
分類そのものが誤っていた。原因は二つ。

1. **抽出が広すぎた。** 「the question doesn't specify…」のように**問いを主語にした文**を
   拾っていた。これは課題の曖昧さであって、データ側の欠落ではない。101件がこれだった。
2. **束ねが先勝ちだった。** 文中に現れた最初の束の語で決めていたため、
   「コードの意味が書かれていない」と述べた文が、`external` の一語で外部参照の束に入っていた。

その結果、最初の版は 101文 → 業種コード31件・活動状態20件・外部参照7件・未分類43件と
報告していたが、**活動状態と外部参照の束は、この誤りが作り出したものだった**。
直した後は 10文 → 業種コード9件・未分類1件で、**逆算される仕様は1つだけ**になる。

未分類の1件は「該当する業種コードがデータに無い」という中身の話で、`classification` の語を
含んでいたために関門をすり抜けている。

### 留保

* 後半の試行では、データではなく**出題者の意図を推し量る**方向に転じる
  （実測: `the answer they expect` と書いている）。そこで生成される文は要求仕様にならない。
  `--first-half` で各試行の前半だけに絞れるが、**切り分けの基準そのものは測っていない。**
* 束ねは語彙による分類であって、意味を読んでいるわけではない。10件のうち1件が
  分類できていない。**LLM を呼んで分類させることはしていない。** 逆算の手順そのものが
  トークンを消費すると、何を測っているのか分からなくなる。
* 採れた文は191件の引き金のうち10件で、**歩留まりは5%である。** 残りの大半は
  問いを主語にした文（101件）で、これは課題の書き方の問題であってデータの問題ではない。
  実運用のログでは、この比率が変わる可能性がある。
* 欠落が「単一の対応表」という形をしていたから一意に落ちた可能性がある。
  別の形の欠落で同じ手順が回るかは確かめていない。

---

# 中間推論のトークン数

これまで取れていたのは**文字数だけ**だった。文字数はトークン数の代わりにならない
（言語や記号の混ざり方で比が変わる）。`count_thinking.py` が、取り出したテキストを
そのモデルのトークナイザで数えて結果に書き足す。

```bash
python count_thinking.py results/reference/run_20260823T124213Z.json --dry-run
python count_thinking.py results/reference/run_20260823T124213Z.json
```

## 何を正とするか

| 状況 | `thinking_tokens` | `thinking_tokens_source` |
| --- | --- | --- |
| サーバが `usage` で `reasoning_tokens` を返す | その値 | `server` |
| 返さないが、思考テキストとトークナイザがある | 数えた値 | `tokenizer` |
| どちらも無い | **`null`** | `null` |

**両方取れた場合は上書きしない。** サーバの値を正とし、数えた値を
`thinking_tokens_counted`、差を `thinking_tokens_delta` に別途残す。差の大きさが
分かれば、近似の妥当性を後から評価できる。

**数えられない場合は `null` のままにする。文字数からの換算はしない。**

## 近似であることについて

ここで数えるのは「取り出したテキストを、いま符号化し直したときの長さ」であって、
**生成時に実際に流れたトークン列とは一致しない可能性がある**。

* 開始タグ・終了タグそのものは思考テキストに含まれていない（切り出しで落としている）
* 特殊トークンの扱いはテンプレート依存で、ここでは付けずに数えている
* 前後の空白の削り方が、切り出しの時点と生成時とで違いうる

したがって `tokenizer` 由来の値は**下限寄りの近似**である。

## 取り出しの三経路

`run_benchmark.split_thinking()` が三通りを扱い、**どれで取れたかを
`thinking_source` に記録する**。系統によって形が違うので、後から
「この値はどうやって取ったのか」が分からないと突き合わせられない。

| `thinking_source` | 形 | 例 |
| --- | --- | --- |
| `reasoning_content` | サーバが分けて返す | vLLM / SGLang を `--reasoning-parser` 付きで起動した場合 |
| `tag_pair` | 開始タグと終了タグが対で本文に現れる | 多くの系統 |
| `closing_tag` | **終了タグだけが現れる**（開始タグはチャットテンプレート側） | Olmo-3-7B-Think をパーサ無しで動かした場合 |
| `null` | 思考が返らない | API 経由の3モデル |

タグの対は `run_benchmark.THINK_TAGS` に並べてある
（`<think>` / `<thinking>` / `<reasoning>` / `<|begin_of_thought|>`）。

## 新しいモデル系統を足す手順

1. **`<think>` の書式を確かめる。** モデルカードか `tokenizer_config.json` の
   `chat_template` を見る。対で出るのか、終了タグだけなのか。
   `THINK_TAGS` に無いタグなら1行足す。
2. **パーサの有無を確かめる。** `vllm serve --reasoning-parser <name>` が使えるなら
   `reasoning_content` で分かれて返り、`reasoning_tokens` も埋まる。
   使えなくてもよい（本文から切り出せる）。**実測: vLLM 0.27.1 には
   reasoning-parser が1件も登録されていなかった。**
   使えるかはトークナイザ依存で、`<think>` が単一トークンでないと弾かれる。
3. **トークナイザを確かめる。** `count_thinking.py` は Hugging Face の
   `tokenizer.json` を取ってきて `tokenizers` で読む。
   公開されていない系統（API 経由のモデルなど）は `NO_TOKENIZER` に前置詞を足すか、
   そのまま `null` にしておく。`--tokenizer` で明示指定もできる。
4. **モックにシナリオを足して経路を通す。** `mock_client.py` の
   `mock-think-inline` / `mock-think-close` / `mock-think-alt-tag` / `mock-think-field`
   が四通りを踏んでいる。新しい形はここに足す。

必要なのは `pip install tokenizers huggingface_hub`。`transformers` は入れない
（torch を引き込むため）。TLS を中継する環境では証明書の検証が通らないことがあり、
その場合は `truststore` を入れると OS の証明書ストアを使う（実測: この環境がそうだった）。

## Olmo ランに遡って適用した結果

再実行なしで、20実行・76試行すべてにトークン数が入った
（`thinking_tokens_source` は全件 `tokenizer`。このサーバは `reasoning_tokens` を
返していないため、`server` 由来の値は0件で、差の記録も無い）。

| 水準 | `task_04` | `task_06` |
| --- | --- | --- |
| `l0_opaque` | 7,411 | **110,853** |
| `l1_names` | 1,709 | 89,382 |
| `l2_units_ref` | 3,214 | 94,690 |
| `l3_units_doc` | 10,185 | 87,798 |
| `l4_units_record` | 1,266 | 85,926 |
| `l5_codes_ref` | 5,832 | **69,183** |
| `l6_codes_doc` | 643 | **1,027** |
| `l7_codes_record` | 947 | 1,102 |
| `l8_flags_record` | 554 | 1,260 |
| `l9_prose` | 750 | 1,254 |

`task_06` の `l5` → `l6` は **69,183 → 1,027 トークン**。

**このランについては、稿の第5節「CoTのトークン数は取れていません」を書き換えられる。**
ただし次の三点は変わらない。

* **API 経由の3モデルでは依然として取れていない。** `reasoning_tokens` が0で返り、
  思考テキストも無いので、数える対象が無い。
* この値は**サーバが返したものではなく、後から数えた近似**である。
* このランは `REPEATS=1` で、各セルの n は1。ばらつきは評価できない。

なお、このランは `thinking_source` を記録する前のものなので、**どの経路で取り出したかは
`null` のまま**である（実際には `closing_tag` だったが、結果ファイルからは判定できない
ので埋めていない）。以後のランには入る。

---

# パーサについての訂正（2026-08-24）

以前この文書に「**この vLLM 0.27.1 には reasoning-parser が1件も登録されていなかった**」と
書いた。**これは誤りである。**

`ReasoningParserManager.reasoning_parsers` を見て空だったので「登録が無い」と読んだが、
**登録は遅延で行われる**（`lazy_parsers` / `register_lazy_module`）。実際に引くと解決する。

```
登録されているパーサ（28件）:
  cohere_command3, cohere_command4, deepseek_r1, deepseek_v3, deepseek_v4, ernie45,
  gemma4, glm45, glm47, granite, holo2, hunyuan_a13b, hy_v3, inkling, kimi_k2, kimi_k3,
  mimo, minimax_m2, minimax_m2_append_think, minimax_m3, mistral, nemotron_v3,
  olmo3, openai_gptoss, poolside_v1, qwen3, seed_oss, step3, step3p5
```

**`olmo3` パーサも存在する。** Olmo のランは `--reasoning-parser olmo3` で回せたことになる。
当時 `deepseek_r1` が落ちたのは、登録が無かったからではなく、そのパーサが `<think>` を
単一トークンとして要求し、Olmo のトークナイザがそれを持たなかったため。

## それでもパーサは使わない

`Qwen/Qwen3.5-9B` を `--reasoning-parser qwen3` 付きで起動して確かめた結果、
**パーサを付けると思考テキストが失われる**。

| 構成 | `reasoning_content` | `usage.completion_tokens_details` |
| --- | --- | --- |
| パーサ **有り** | **0字**（`finish_reason: stop`、`completion_tokens: 4011` でも空） | **無い** |
| パーサ **無し** | — （`content` に `</think>` 込みで残る） | **無い** |

`completion_tokens_details` 自体が応答に無く、**どちらの構成でも `reasoning_tokens` は
返らない**。したがって「サーバが返した値と、数え直した値を突き合わせる」という検証は、
この vLLM では成立しない。

パーサ無しの応答（`17+25` を問うたもの、`completion_tokens: 3536`）:

> `content 12,584字 / <think> あり: False / </think> あり: True`
> 先頭: `Thinking Process:\n\n1.  **Analyze the Request:** …`
> 末尾: `…17 + 25 の計算結果は 42 です。\n    42\n</think>\n\n17 + 25 の計算結果は 42 です。\n42`

Qwen も Olmo と同じ `closing_tag` 経路になる。**パーサは付けない。**

# 近似の検証（確定値）

`reasoning_tokens` が返らなくても `completion_tokens` は返る。生成本文は
「思考 + タグ + 最終回答」なので、

    残差 = completion_tokens - (数えた思考 + 数えた最終回答)

が、切り出しで落としたぶんにあたる。**Olmo-3-7B-Think の76試行**で実測した。

| | 値 |
| --- | --- |
| 残差の中央値 | **4 トークン** |
| 残差の範囲 | **0 〜 8 トークン** |
| `completion_tokens` に対する割合（中央） | **0.06%** |
| 同（最大） | **0.72%** |

残差は `</think>` と前後の改行ぶんに相当する。**「数え直した値は下限寄りの近似」という
見立ては正しく、ずれは1試行あたり数トークン**である。`count_thinking.py --verify` で
再現できる。

# Qwen を足すことについて

`Qwen/Qwen3.5-9B`（9.7B、Apache-2.0）を1つ足す。位置づけは
**「OSAID を満たす系統で本筋を測り、オープンウェイトも一つ見た」**という形。

> **Qwen はオープンウェイトであり、学習データは公開されていない。**
> OSI の [Open Source AI Definition](https://opensource.org/ai/open-source-ai-definition)
> は満たさない。OSAID を満たすのは OLMo 3 の側で、本筋の測定はそちらで行っている。

## 中間推論のオン/オフ

Qwen は `chat_template_kwargs` で思考を切れる。`THINKING=off` で
`{"chat_template_kwargs": {"enable_thinking": False}}` を送る。

**`THINKING` は指紋に入る**（`fingerprint.thinking_mode` と
`fingerprint.settings.thinking_mode`）。on と off は別の測定なので、途中経過の置き場所も
別になり、片方の続きにもう片方が積まれることはない。

サーバが `enable_thinking` を受け付けなかった場合は**その場で止まる**。落として黙って
続けると、考えさせないつもりの測定が考えさせた測定になるため。

1問（`17+25`）での観測: thinking on の `completion_tokens` 3,536 に対し、
off は 18。**196倍**。これは1問の観測であって測定ではない。

---

# Qwen3.5-9B の実測（thinking オン/オフ）

> **Qwen はオープンウェイトであり、学習データは公開されていない。**
> OSI の [Open Source AI Definition](https://opensource.org/ai/open-source-ai-definition)
> は満たさない。OSAID を満たすのは OLMo 3 の側で、本筋の測定はそちらで行っている。
> ここは「オープンウェイトも一つ見た」という位置づけである。

`Qwen/Qwen3.5-9B`（9.7B、Apache-2.0）を、`v3_levels` の `task_04` / `task_06`、
`REPEATS=1`、`MAX_ATTEMPTS=10`、生成上限 32,768 で回した。**入力の指紋は
`dea1a8ccce8dbbad` で、他の参照点すべてと同一。** thinking の on/off だけが違う。

| ラン | thinking | 所要 | 区間 | エラー | 生成上限到達 |
| --- | --- | --- | --- | --- | --- |
| `run_20260824T061642Z` | **on** | 87分 | 2 | **0件** | **0件** |
| `run_20260824T034646Z` | **off** | 89分 | 2 | 4件 | 0件 |

どちらも Colab CLI 経路（`colab/drive_cli_run.py`）で、セッションの上限をまたいで
区間に分けて回した。引き継ぎは on が8試行、off が7試行。

## 境界は両条件で同じ位置に出る

`task_06` の総トークン:

| 水準 | thinking **on** | thinking **off** |
| --- | --- | --- |
| `l0_opaque` | 不正答 / 10試行 / 83,772 | ERR / 9 / 143,305 |
| `l1_names` | 正答 / 5 / 52,778 | 不正答 / 10 / 198,330 |
| `l2_units_ref` | 不正答 / 10 / 89,166 | 不正答 / 10 / 161,076 |
| `l3_units_doc` | 不正答 / 10 / 64,219 | ERR / 7 / 123,256 |
| `l4_units_record` | 不正答 / 10 / 76,478 | ERR / 4 / 61,680 |
| `l5_codes_ref` | 不正答 / 10 / 106,403 | ERR / 10 / 171,343 |
| **`l6_codes_doc`** | **正答 / 1 / 4,165** | **正答 / 1 / 2,734** |
| `l7`〜`l9` | 正答 / 1 / 3,354〜4,392 | 正答 / 1 / 2,847〜2,987 |

`l5`→`l6` の段差が測れるのは **on の側だけで、25.5倍**（106,403 → 4,165）。
分子の 106,403 は、不正答のまま上限10試行を完走した有効な測定である。

**off の側には、これと対称に比べられる段差がない。** `l6` 未満の6段のうち
**4段（`l0`・`l3`・`l4`・`l5`）が ERR で集計除外**であり、完走したのは `l1`・`l2` の
不正答2件だけである。`l5` の 171,343 はエラーで打ち切られた時点までの累計であって、
「解けずに上限まで払った費用」ではない。有効な測定どうしで比べられる対は `l2` で、
**off 161,076 / on 89,166、約1.8倍**である。

> **撤回**: 以前ここには「off が 62.7倍（171,343 → 2,734）」と書いていた。分子が
> 集計除外の値であり、on の 25.5倍と対称に比べられないため撤回した。数字の来歴として
> 残す。稿側の記録は `paper/CHANGELOG.md` の「2026-08-24（5）」。
> **撤回したのは 62.7 という段差の値だけ**で、境界の位置（両条件とも `l5`→`l6`）と
> エラー件数（off 4件 / on 0件）は撤回していない。

上の表の `ERR` 行は、その時点までの累計であって水準あたりの消費ではない。
段差の比較に使えるのは `ok` の行だけである。

対照の `task_04` は on でも全10水準を1試行で解いており、段差は出ていない。

思考の量（`task_06`、thinking on）:

| 水準 | 思考の文字数 |
| --- | --- |
| `l0`〜`l5` | 79,863 〜 133,432 字 |
| `l6`〜`l9` | 1,359 〜 3,229 字 |

思考トークンは69試行で合計 242,972、1試行あたり最小 605・最大 46,468。

## thinking on のほうが文脈長エラーが少なかった

| | on | off |
| --- | --- | --- |
| 文脈長超過（400） | **0件** | 4件 |

**推測**（実測ではない）: 思考を切ると回答そのものが長くなり、それが会話履歴に積まれて
文脈長を食い潰す。off の `l1_names` では入力が 2,330 → 19,019 トークンに膨らみ、
1回の生成が最大 8,257 トークンだった。on では思考が本文に出るが、**切り出して履歴には
積まない**ので、履歴が伸びない。両ランの入出力内訳からの読みであって、
切り分けた実験ではない。

## 近似の検証が別のトークナイザでも再現した

`count_thinking.py --verify` の結果:

| モデル | 試行 | 残差の中央 | 範囲 | `completion_tokens` に対する割合（中央 / 最大） |
| --- | --- | --- | --- | --- |
| Olmo-3-7B-Think | 76 | **4 トークン** | 0〜8 | 0.06% / 0.72% |
| Qwen3.5-9B | 69 | **4 トークン** | 3〜7 | 0.15% / 0.60% |

**別の系統・別のトークナイザでも同じ水準**である。数え直した値が下限寄りの近似で、
ずれが1試行あたり数トークン（切り出しで落としたタグと前後の空白）に収まることは、
モデル固有の性質ではない。

## 見積もりは両方向に外している

| ラン | 見積もり | 実測 | 向き |
| --- | --- | --- | --- |
| B（thinking off） | 10〜20分 | **89分** | **過小**（4〜9倍） |
| A（thinking on） | 4〜5時間 | **87分** | **過大**（3倍） |

* B を過小に見たのは、思考を切れば軽いと考えたため。実際には `task_06` の解けない水準で
  **回答そのものが長大化**し、上限10試行まで回った。消費は思考ではなく回答から来ていた。
* A を過大に見たのは、Olmo の思考の長さ（1試行で最大 110,853 トークン）から外挿したため。
  **Qwen の思考は Olmo ほど長くならず、生成上限（32,768）に一度も届かなかった**
  （到達0件）。1試行あたりの思考トークンは最大 46,468 で、Olmo の半分以下だった。

**同じ課題・同じ設定でも、モデルが変われば所要は数倍ずれる。**
外挿の基準にできるのは、同じモデルの実測だけである。

---

# 見積りの教訓: 上限試行を使い切る水準は線形外挿できない

**1反復の実測に反復数を掛けても、重い水準の所要は見積れない。**

2026-08-25 の REPEATS=5 本走行で、Olmo の `l5_codes_ref` に残っていた3試行を
「参照点の16.9分/反復」から25〜40分と見積もり、**71分の期限内に終わらなかった**。
`l5` は上限10試行を使い切る水準で、1試行あたりの思考の長さが反復ごとに大きく振れる。
平均を掛けた値は、その分布の中央付近にしか当たらない。

軽い水準（`l6`〜`l9`、1試行で解ける）では同じ外挿がよく当たる。**振れるのは、
解けずに上限まで払う水準だけ**である。

今後の見積りでは:

* 上限試行に張り付く水準（`l0`〜`l5`）は、1反復の実測ではなく**分布の上側**で引く。
* 軽い水準は平均で引いてよい。
* 見積りと実測の差は、当たった場合も外れた場合も記録に残す。これまでに
  過小（4〜9倍）・過大（3倍）・今回の過小と、**両方向に外している**。

---

# 反復5回の本走行（2026-08-25、RunPod A100 SXM 80GB）

3系統とも `v3_levels` の `task_04` / `task_06`、全10水準、**REPEATS=5** で100試行。
入力の指紋は3系統とも `b451fbf5b1345621` で同一。seed は反復ごとに変えている
（`seed = SEED + (repeat - 1)`）。

## 境界は3系統とも `l5`→`l6` に出る

`task_06` の総トークン（5反復のプール）と、反復ごとの振れ幅:

| 系統 | `l5` 合計 | `l6` 合計 | 段差 | `l6` 未満の正答 | `l6` 以上の正答 |
| --- | --- | --- | --- | --- | --- |
| Olmo-3-7B-Think on | 531,850 | 16,293 | **32.6倍** | 2/30 | **20/20** |
| Qwen3.5-9B on | 446,635 | 20,117 | **22.2倍** | 4/30 | **20/20** |
| Qwen3.5-9B off | 450,254 | 14,010 | **32.1倍** | 0/30 | **20/20** |

## 差はばらつきより大きい

**これが反復を増やした目的だった。** 1反復では、段差が本物か偶然かを分けられない。

| | `l6` 未満（`l0`〜`l5`） | `l6` 以上（`l6`〜`l9`） |
| --- | --- | --- |
| 1反復あたりの総トークン | 37,582 〜 204,233 | 2,734 〜 5,258 |
| 水準内の振れ（最大/最小） | 最大 2.7倍 | 最大 1.35倍 |
| 水準どうしの重なり | **6段すべてが重なる** | 4段すべてが重なる |

`l6` 未満の6段は互いに区別がつかない（どれも45万〜68万トークンの帯に収まる）。
`l6` 以上の4段も互いに区別がつかない。**区別がつくのはこの2群の間だけで、
その差（22〜33倍）は群内の振れ（最大2.7倍）よりはるかに大きい。**

## `repeat=1` は 40GB の参照点を再現しない

同じ seed・同じ入力でも、80GB で回した `repeat=1` は Colab の 40GB ランと一致しない。

| 系統 | 一致したセル |
| --- | --- |
| Olmo on | 1/20 |
| Qwen on | 2/20 |
| Qwen off | 8/20 |

**一致は軽い水準（`l6`〜`l9`）と軽い課題に偏り、上限10試行を使う重いセルでは
ほぼ再現しない。** 煙試験で Qwen の `l6` が完全一致したのは、その軽いセルの一つを
見ていたためで、一般には成り立たない。1試行目のわずかな違いが会話履歴に入り、
以降の試行すべてが変わるためと考えられる（**推測**。切り分けた実験はしていない）。

**測っている量（トークン数・試行数・成否）の比較は成立する** ——境界の位置も段差の
大きさも3系統で再現している——が、**トークン単位の再現性は器材をまたいで保証されない。**
