# 参考文献・出典

本稿（[`return-on-token.md`](return-on-token.md)）で言及した資料の一覧です。

*English version: [`REFERENCES.en.md`](REFERENCES.en.md)*

## トークン消費と単価の見通し

- Gartner「Gartner Predicts That by 2030, Performing Inference on an LLM With 1 Trillion Parameters Will Cost GenAI Providers Over 90% Less Than in 2025」（2026年3月25日）
  https://www.gartner.com/en/newsroom/press-releases/2026-03-25-gartner-predicts-that-by-2030-performing-inference-on-an-llm-with-1-trillion-parameters-will-cost-genai-providers-over-90-percent-less-than-in-2025
  第3節で引用。単価の低下をトークン消費の増加が上回るため推論コストの総額は増加すること、エージェント型モデルが1タスクあたり標準的なチャットボットの5〜30倍のトークンを要すること。

- Goldman Sachs Research「AI Agents Forecast to Boost Tech Cash Flow as Usage Soars」（2026年5月20日）
  https://www.goldmansachs.com/insights/articles/ai-agents-forecast-to-boost-tech-cash-flow-as-usage-soars
  第3節で引用。2026年から2030年にかけてトークン消費が24倍・月間120千兆トークンに達するとの予測、半導体側が推論の単価を年60〜70%下げているとの指摘。

## 推論機能によるトークン消費の増加

- Sasha Luccioni, Boris Gamazaychikov「AI Energy Score v2: Refreshed Leaderboard, now with Reasoning」（Hugging Face Blog, 2025年）
  https://huggingface.co/blog/sasha/ai-energy-score-v2
  第1節で引用。同一モデルについて推論機能の有無を比べ、出力トークン数が300〜800倍、消費エネルギーが150〜700倍になるとの測定。

## 計算資源最適化の枠組み

- Tokenomics Foundation（Linux Foundation傘下）「The Five-Layer Tokenomics Stack」
  https://www.tokeneconomics.com/projects/the-five-layer-tokenomics-stack/
  第3節・第4節で参照。下の層が単価を、上の層が消費量を決めるという二分。本稿のL3〜L5の呼称はこれに拠ります。

## エネルギー効率の計測枠組み

第3節で「測り方の提案は多数ある」として言及したもの。いずれも1トークンあたりのエネルギーを測る枠組みであり、必要なトークン数そのものは扱いません。

- MLPerf Power（MLCommons）
  https://arxiv.org/abs/2410.12032

- AI Energy Score（Hugging Face）
  https://huggingface.github.io/AIEnergyScore/

- TokenPowerBench
  https://arxiv.org/abs/2512.03024

## 測定に用いたモデルと環境

第5節の測定は OpenAI の gpt-4o-mini / gpt-4.1-mini / gpt-5.4 を用いました。実行時の指紋（入力データ・プロンプト・サンプリング設定・コードのハッシュ）はすべて結果ファイルに記録しています。再現手順は [`benchmark/`](../benchmark/) を参照してください。

## 記載の方針

本稿が引用するのは、原則として一次情報（発表元が公開している資料）に限ります。人づてに伺った数値や、出典を示せない推計は本文に載せません。
