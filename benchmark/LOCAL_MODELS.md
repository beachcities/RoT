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
| `--reasoning-parser deepseek_r1` が起動失敗（`<think>` が単一トークンでないと使えない） | パーサ無しで起動。**この vLLM 0.27.1 には reasoning-parser が1件も登録されていなかった**（`ReasoningParserManager` が空） |
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

## 「欠けている」の言及頻度

思考テキストから、欠落を述べた文を機械的に数えたもの。

| 水準 | 「欠けている」の言及 | コードの意味への言及 | 思考字数 |
| --- | --- | --- | --- |
| `l0`〜`l5` | 7〜20件 | 57〜128件 | 302,832〜429,273 |
| `l6`〜`l9` | 0〜1件 | 0〜2件 | 5,593〜6,970 |

`l6` を境に、どちらも消える。
