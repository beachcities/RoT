# Return on Token: An Indicator Linking Data Self-Description to AI Inference Token Consumption

*Working draft for Data & Policy (standard track, Research Article). Derived from Frozen Public Release v0.2.0 (`d483d6b`). The frozen files under `paper/` are not modified by this derivative. Front-matter statements (Abstract, Policy Significance Statement, Keywords, disclosure statements) are maintained in [`statements.md`](statements.md). Notation: this derivative uses "RoT" throughout; the frozen paper's "ROT" is unchanged on the frozen side.*

## 1. Introduction

*[TODO: derive from frozen §1 (the humming chain of thought), add contributions paragraph and the RoT-name disambiguation note. Per the conversion plan approved 2026-08-28.]*

## 2. Background and related work

**Inference-time scaling and its cost.** Chain-of-thought prompting showed that eliciting intermediate reasoning steps as generated text improves task performance (Wei et al. 2022), and reinforcement-learning-trained reasoning models have since made long generated reasoning a standard operating mode rather than a prompting technique (DeepSeek-AI 2025). The cost side of this shift has been measured: the AI Energy Score comparisons report output-token multipliers of 300–800 and energy multipliers of 150–700 for the same models with reasoning enabled versus disabled (Luccioni and Gamazaychikov 2025). Market projections point the same direction at the aggregate level: Goldman Sachs projects a twenty-four-fold growth in token consumption between 2026 and 2030, and Gartner expects consumption growth to outpace the fall in inference unit costs, so that total inference spending rises (Goldman Sachs Research 2026; Gartner 2026). Token consumption is thus becoming a measurable, growing, and policy-relevant resource.

**Model-side efficiency.** A rapidly growing body of work responds by making the model reason more efficiently. "Overthinking" — reasoning far longer than a problem requires — has been documented directly (Chen et al. 2024), and the first structured survey of efficient reasoning organizes the responses: compressing or shortening reasoning chains, imposing token budgets, exiting early, and switching between reasoning regimes (Sui et al. 2025). Engineering control stacks such as the Tokenomics Foundation's five-layer framework extend this logic from silicon to routing (Tokenomics Foundation n.d.). What these approaches share is the side of the system they act on: they manage the denominator of consumption by constraining the model's output, while treating the input data — and whatever the model must guess about it — as given.

**Documentation of data.** A separate literature treats the description of data as the object of design. The FAIR principles made machine-actionable metadata a general target for scientific data (Wilkinson et al. 2016), and datasheets brought standardized documentation practice to machine-learning datasets (Gebru et al. 2021). At the same time, field evidence shows that this documentation work is systematically undervalued relative to model work (Sambasivan et al. 2021) — an undervaluation consistent with the economics of complementary investment in general purpose technologies, where the returns to a one-off improvement of a non-rival input accrue to downstream users rather than to the investor (Bresnahan and Trajtenberg 1995). This literature establishes what good description is and why it is underprovided; what it measures is conformance and practice, not what description does to a model's consumption at inference time.

**Open government data: metadata and value.** In the open-government-data literature the same questions appear at portal scale, and empirically. Quarati (2023) assessed roughly 400,000 datasets across national, municipal, and international portals, measuring their usage alongside programmatically assessed metadata quality and examining the relationship between the two; notably, the study did not find a clear positive correlation between better metadata publishing practices and usage — a caution against treating metadata quality as an established driver of use. On the value side, systematic work asks how "high-value datasets" should be determined (Nikiforova et al. 2023), the European Union has fixed a legal list of high-value dataset categories to be published free of charge in machine-readable form (European Commission 2023), and UNESCO's guidance places making data AI-ready among the preparation steps for opening data (UNESCO 2023). Across this line, the value and priority of public data are assessed through publication, usage, quality conformance, and enumerated categories; the consumption of inference compute does not yet appear among the evaluation axes.

**Where this paper sits.** The four groups above have developed largely separately: the first measures a growing consumption problem, the second manages it from the model side, and the third and fourth build and prioritize data description without measuring its consequences for that consumption. This paper connects them by measurement: it varies the description available to the model and reads the result in tokens per outcome. Within this bounded review, we did not identify prior work that directly measures inference token consumption as a function of whether task-relevant data descriptions are available to the model.

## 3. The RoT indicator and the self-description hypothesis

**3.1 Definition.** We define Return on Token (RoT) as the ratio of outcome obtained to total tokens invested:

$$\text{RoT} = \frac{\text{outcome obtained (task solved, value created)}}{\text{total tokens invested (including recursive and discarded search)}}$$

Both terms need specification. The numerator is the outcome of the run — in the measurements of this paper, simply whether the task was solved. Richer numerators — value created, measured by reproduction cost, substituted labour, or downstream savings — would be needed to connect RoT to macroeconomic value-added statistics, and none of these is standardised; token intensity is further distorted by linguistic and industrial structure, since a Japanese tokeniser does not cost the same as an English one for equivalent content. We leave the numerator's standardisation open and use the minimal, measurable form throughout.

The denominator is deliberately inclusive: it counts every token of the run, including the recursive tokens an agent generates by feeding its own output back into itself, and the search that is ultimately thrown away. The rationale is that the size of the discarded search is itself informative — it is the weight of the context the data failed to supply. An indicator that excluded failed attempts would hide precisely the expenditure this paper is about.

**3.2 The self-description hypothesis.** We hypothesize that a major determinant of RoT is the self-description of the data: the degree to which the meanings, units, and definitions that a task requires are reachable from where the consumer of the data stands. This is broader, and more demanding, than what "self-describing" usually denotes in data engineering, where the term refers to formats that embed their own schema (JSON, Parquet, Avro and the like). A schema is one means to reachability, not the end: a reference to an external schema that the consumer does not resolve leaves the data, for that consumer, no more self-described than before. The question is not which format was used but whether the required information is present and reachable.

The hypothesis has several components, and they do not share one evidential status; Section 4 reports which have been measured. The component this paper measures directly concerns search: we hypothesize that when required meanings are absent, models expend recursive tokens generating and testing guesses, and that this search diminishes when the description is supplied. A second component received a first, single-point measurement: that description reaching a smaller model can widen the range of tasks it completes — with an observed limit, one description form that the smaller model could not use. Three further components remain hypotheses, stated here so that the boundary is explicit. Regularised description could stabilise the leading portion of prompts and so raise cache hit rates; description could tell on the training side, where stated correspondences fold into weights instead of being supplied as context at inference time; and description may be a precondition for *framing* questions, not only answering them — if what the data holds cannot be read off it, a question the data could answer cannot be posed, and the less spare capacity a model has, the more it is confined to what is written. None of these three is measured in this paper.

**3.3 Relation to model-side efficiency.** The approaches surveyed in Section 2 — compressing reasoning chains, imposing token budgets, exiting early — act on the generation process: given the data as it is, they constrain how much the model may spend on it. The intervention this paper examines acts one step earlier, on the data artifact itself, before any model runs. The difference is in the point of intervention, not a claim of superiority, and the two are combinable: a budget caps the search that guessing produces, while description, where the hypothesis holds, removes the reason for that search to begin. The economic character of the two interventions also differs. A control applied at generation time is exercised on every run and priced in rival compute; a description added to a dataset is a one-off fixed cost on a non-rival good, and, to the extent that its effect transfers across tasks, models, and real data — a transfer this paper does not measure — its benefits would accrue to downstream consumers of that dataset across models and runs. This asymmetry is what later sections develop into a policy question: who should bear a cost whose returns the payer cannot capture.

## 4. Measurements

**4.1 Setup and instruments.** The same tasks were posed against data varied across ten levels of self-description, and token consumption per outcome compared. The levels combine two axes: what is written (from nothing, through meaningful field names and units, to the meanings of codes) and where it sits (inside the record, in a document header, or as an external reference only). Two synthetic tasks were used throughout: a main task requiring the meaning of a code, designed so that it cannot be inferred from other clues, and a control task solvable by inference from company names even when nothing is stated. When a model fails, it is told to reconsider its premises and retry, up to ten attempts; tokens from failed attempts all count toward the denominator. The runtime environment, input data, prompts, and sampling settings are recorded as hashes in the result files, and reproduction steps are published with the benchmark.

Measurements were taken in three series, which we keep separate throughout; numbers are comparable within a series, and we do not aggregate across them.

| Series | Execution | Systems | Repetitions | Reported in |
| --- | --- | --- | --- | --- |
| Reference route | Provider APIs | gpt-4o-mini; gpt-4.1-mini; gpt-5.4 | 5 per cell | 4.2 |
| Reference route | Local (vLLM), A100-40GB | Olmo-3-7B-Think; Qwen3.5-9B (thinking on/off); Qwen3.5-2B | 1 | 4.2, 4.4 |
| Five-repetition local route | Local (vLLM), A100-80GB | Olmo-3-7B-Think; Qwen3.5-9B (thinking on/off) | 5, seed varied per sample | 4.4 |
| Single-shot instrument | Local, separate implementation | Qwen3.5-9B (thinking on) | pilot 200; confirmatory 200×2 | 4.4 |

The five-repetition route runs on different hardware from the reference route and is treated as a separate route: its figures are not merged with reference-route figures. The single-shot instrument is a separate implementation, incompatible with the retry-based series, and no direct numerical comparison is made with them. Two defects found on the measuring side during this work — a grader flaw and task escape routes — are reported in 4.6, together with the results discarded because of them.

**4.2 Main result: a boundary, not a gradient.** On the reference route, the main task was measured across four systems. The table gives median total tokens at the two levels either side of the boundary.

| Model | l5 (external reference only) | l6 (stated in document) | Ratio | Correct at l0–l5 |
| --- | --- | --- | --- | --- |
| gpt-4o-mini | 51,631 | 2,205 | 23.4 | 0/30 |
| gpt-4.1-mini | 62,885 | 2,146 | 29.3 | 0/30 |
| gpt-5.4 | 30,288 | 2,084 | 14.5 | 0/30 |
| Olmo-3-7B-Think | 96,670 | 3,196 | 30.2 | 0/6 |

At every level where the required information was absent from the document, no system solved the main task even once, and every trial ran to the ten-attempt ceiling; at the level where it was present, every system solved it on the first attempt. Total consumption fell by factors of 14 to 30. The boundary appears as a step, not a gradient: the levels below it are not ordered by how much partial description they carry.

Two features of the step matter for what follows. First, the level carrying only an external reference (l5) fell on the same side as stating nothing at all — pointing at a schema and reaching it are not the same thing, the distinction drawn in Section 3.2. Second, the control task shows no step: every system solved it at every level with no substantial difference in consumption. Where a clue exists, the models get there without being told; the boundary appears only where the missing information cannot be inferred. Further systems on the reference route (a thinking-toggle pair and a smaller-capacity model) and the two other series are reported in 4.4.

**4.3 Reading the search: observations from reasoning text.** The three API systems return `reasoning_tokens` as zero and no reasoning text, so their consumption can be measured but not read. Olmo-3-7B-Think, served locally, leaves the contents of its intermediate reasoning as text, and this subsection reports what that text shows on the main task. These are observations of one system's reasoning, and interpretations of it; they are not a causal decomposition of the consumption measured above.

At the external-reference level (l5), the model notices the reference and states that it cannot resolve it ("Since I can't see the external code list (code_list_reference is a url, which I can't access), I need to rely solely on the given data and common sense."). Having said so, it nonetheless spends ten attempts and 279,148 characters of reasoning continuing to guess. At the level stating nothing (l0), it names the gap at the outset ("The problem is, the data doesn't list the industry type for each company.") and rebuilds its own classification on every attempt — the ten answers move 249 → 249 → 264 → 264 → 719 → 943 → 1149 → 943 → 943 → 826, not one guess repeated — across 404,407 characters; partway through it declares its angles exhausted, and the later attempts turn from the data toward inferring what the questioner expects. At the level where the code meanings are stated (l6), the reasoning consists of lookup and addition ("Let me confirm that from the code_definition."), with no hypothesis generation we could identify; the gap between 279,148 characters at l5 and 2,796 at l6 closes on that one lookup. Because characters are no substitute for tokens, the extracted reasoning text was re-counted with the model's own tokeniser: 69,183 tokens at l5 against 1,027 at l6 on the same task. This is an after-the-fact approximation, excluding the enclosing tags and special tokens and therefore erring low; checked against the server-returned consumption, the residual was a median of 4 tokens per attempt (0.06% for Olmo, 0.15% for Qwen, across two tokeniser families).

To put a number on how much of the reasoning concerns the data's gaps, the reasoning of failed attempts was classified sentence by sentence with published, rule-based classifiers (no LLM involved). The share of characters mentioning or guessing at data-side gaps was 16.0% for Olmo and 18.6% for Qwen. The figure moves with the classification rules — up to 23% depending on how sentences touching both sides are treated, down to 1–6% if only explicit statements of absence are counted — and it is a floor for a different quantity than total gap-caused expenditure: a sentence that carries on calculating on top of a guessed correspondence is not captured. Nearly all of it comes from failed attempts at a task built so that a data-side gap is the blocker, so it is not a figure for reasoning in general. One further observation is recorded without resolution: the share of mentions directed at ambiguity in the *question* differed sharply by lineage — 14.3% for Olmo against 3.8% for Qwen — and whether that difference is a habit of how the two write their reasoning, or something substantive, has not been separated.

These observations are consistent with the reading that, on this task, the absent description occasions search and the supplied description makes it unnecessary; the same shape of consumption appeared in the closed systems, where the reasoning cannot be read and attribution is correspondingly harder. We report the pattern as observed, in one open system's text, at the mechanism-visibility level this method affords.

**4.4 Robustness.**

*[TODO: thinking-toggle pair (reference route), five-repetition local route (step vs spread), quarter-capacity single repetition (8.5×, l8 failure), single-shot instrument v2 (t=2 stability, no-fit result). Kept per series, no cross-series aggregation.]*

**4.5 Deriving requirements from logs.**

*[TODO: four-stage derivation, rebuild record, 5% yield, question-side finding.]*

**4.6 Traps on the measuring side.**

*[TODO: grader flaw and discarded results; task escape routes; the 62.7× retraction record (cut-off running total, later filled on the separate route).]*

## 5. Limitations

*[TODO: from frozen §5 "What was not measured" + reservations gathered from the body.]*

## 6. Policy implications

*[TODO: compressed merger of frozen §6–§8: log-derived requirements, investment-priority formula with its task-boundedness caveat, open data as digital public good, digital sovereignty. Framed as policy hypotheses consistent with the PSS.]*

## 7. Conclusion and call for collaboration

*[TODO: from frozen Call for Collaboration.]*

## References

*[TODO: Cambridge A (author–date). Set frozen 2026-08-28: 12 new entries (Wei 2022; DeepSeek-AI 2025; Sui et al. 2025; Chen et al. 2024; Wilkinson et al. 2016; Gebru et al. 2021; Sambasivan et al. 2021; Quarati 2023; Nikiforova et al. 2023; European Commission 2023; UNESCO 2023; Bresnahan and Trajtenberg 1995) + carried-over primary sources from `paper/REFERENCES.en.md` (Gartner 2026; Goldman Sachs Research 2026; Luccioni and Gamazaychikov 2025; Tokenomics Foundation n.d.; MLPerf Power; AI Energy Score; TokenPowerBench; OSI OSAID 1.0; model cards). DOI reachability check for the five classics at formatting time.]*
