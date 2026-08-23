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
