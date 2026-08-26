# References

Sources cited in [`return-on-token.en.md`](return-on-token.en.md).

*Japanese version: [`REFERENCES.md`](REFERENCES.md)*

## Token consumption and unit-cost outlook

- Gartner, "Gartner Predicts That by 2030, Performing Inference on an LLM With 1 Trillion Parameters Will Cost GenAI Providers Over 90% Less Than in 2025" (25 March 2026)
  https://www.gartner.com/en/newsroom/press-releases/2026-03-25-gartner-predicts-that-by-2030-performing-inference-on-an-llm-with-1-trillion-parameters-will-cost-genai-providers-over-90-percent-less-than-in-2025
  Cited in Section 3: that rising token consumption outpaces falling unit costs, so total inference costs increase; and that agentic models require 5–30 times more tokens per task than a standard chatbot.

- Goldman Sachs Research, "AI Agents Forecast to Boost Tech Cash Flow as Usage Soars" (20 May 2026)
  https://www.goldmansachs.com/insights/articles/ai-agents-forecast-to-boost-tech-cash-flow-as-usage-soars
  Cited in Section 3: the projection that token consumption multiplies twenty-four fold between 2026 and 2030, reaching 120 quadrillion tokens a month; and that semiconductor providers are driving inference unit costs down 60–70% a year.

## Token consumption with reasoning enabled

- Sasha Luccioni and Boris Gamazaychikov, "AI Energy Score v2: Refreshed Leaderboard, now with Reasoning" (Hugging Face Blog, 2025)
  https://huggingface.co/blog/sasha/ai-energy-score-v2
  Cited in Section 1: comparing the same models with and without reasoning enabled, 300–800 times as many output tokens and 150–700 times the energy.

## Compute optimisation frameworks

- Tokenomics Foundation (Linux Foundation), "The Five-Layer Tokenomics Stack"
  https://www.tokeneconomics.com/projects/the-five-layer-tokenomics-stack/
  Referenced in Sections 3 and 4: the division whereby lower layers set unit price and upper layers set volume consumed. The L3–L5 labels used in this paper follow it.

## Energy efficiency measurement frameworks

Referenced in Section 3 as "proposals for how to measure are plentiful." Each measures energy per token; none addresses how many tokens were needed.

- MLPerf Power (MLCommons)
  https://arxiv.org/abs/2410.12032

- AI Energy Score (Hugging Face)
  https://huggingface.github.io/AIEnergyScore/

- TokenPowerBench
  https://arxiv.org/abs/2512.03024

## Definition of open source AI

- Open Source Initiative, "The Open Source AI Definition 1.0"
  https://opensource.org/ai/open-source-ai-definition
  Referenced in Section 5: a definition requiring not only weights but information about the training data and the training code, sufficient for a skilled person to rebuild a substantially equivalent system. This paper distinguishes lines that meet this definition from those that publish weights alone.

## Models and environment used for measurement

The measurements in Section 5 used OpenAI's gpt-4o-mini, gpt-4.1-mini, and gpt-5.4 through an API, together with the Allen Institute for AI's Olmo-3-7B-Think and Qwen's Qwen3.5-9B and Qwen3.5-2B, all served locally.

- allenai/Olmo-3-7B-Think
  https://huggingface.co/allenai/Olmo-3-7B-Think
  Training data (Dolci) and training code are published, satisfying the Open Source AI Definition above. Serving it locally with vLLM makes the contents of the intermediate reasoning (`<think>`) available as text.

- Qwen/Qwen3.5-9B
  https://huggingface.co/Qwen/Qwen3.5-9B
  Open-weight, with weights published under Apache-2.0. The training data is not published, so the line does not satisfy the Open Source AI Definition above. Served locally with vLLM and measured under two conditions, with thinking enabled and disabled (`enable_thinking`).

- Qwen/Qwen3.5-2B
  https://huggingface.co/Qwen/Qwen3.5-2B
  Open-weight (Apache-2.0), sharing the 9B's family and architecture. The training data is not published, so the line does not satisfy the Open Source AI Definition above. Served locally with vLLM (used for the capacity comparison in Section 5).

Fingerprints of each run — input data, prompt, sampling settings, and code hashes — are recorded in the result files. Reproduction steps are in [`benchmark/`](../benchmark/).

## Citation policy

This paper cites primary sources only: material published by the originating organisation. Figures heard secondhand, and estimates whose source cannot be shown, are not carried in the body text.
