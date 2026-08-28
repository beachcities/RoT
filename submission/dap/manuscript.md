# Return on Token: An Indicator Linking Data Self-Description to AI Inference Token Consumption

*Working draft for Data & Policy (standard track, Research Article). Derived from Frozen Public Release v0.2.0 (`d483d6b`). The frozen files under `paper/` are not modified by this derivative. Front-matter statements (Abstract, Policy Significance Statement, Keywords, disclosure statements) are maintained in [`statements.md`](statements.md).*

## 1. Introduction

*[TODO: derive from frozen §1 (the humming chain of thought), add contributions paragraph and the RoT-name disambiguation note. Per the conversion plan approved 2026-08-28.]*

## 2. Background and related work

**Inference-time scaling and its cost.** Chain-of-thought prompting showed that eliciting intermediate reasoning steps as generated text improves task performance (Wei et al. 2022), and reinforcement-learning-trained reasoning models have since made long generated reasoning a standard operating mode rather than a prompting technique (DeepSeek-AI 2025). The cost side of this shift has been measured: the AI Energy Score comparisons report output-token multipliers of 300–800 and energy multipliers of 150–700 for the same models with reasoning enabled versus disabled (Luccioni and Gamazaychikov 2025). Market projections point the same direction at the aggregate level: Goldman Sachs projects a twenty-four-fold growth in token consumption between 2026 and 2030, and Gartner expects consumption growth to outpace the fall in inference unit costs, so that total inference spending rises (Goldman Sachs Research 2026; Gartner 2026). Token consumption is thus becoming a measurable, growing, and policy-relevant resource.

**Model-side efficiency.** A rapidly growing body of work responds by making the model reason more efficiently. "Overthinking" — reasoning far longer than a problem requires — has been documented directly (Chen et al. 2024), and the first structured survey of efficient reasoning organizes the responses: compressing or shortening reasoning chains, imposing token budgets, exiting early, and switching between reasoning regimes (Sui et al. 2025). Engineering control stacks such as the Tokenomics Foundation's five-layer framework extend this logic from silicon to routing (Tokenomics Foundation n.d.). What these approaches share is the side of the system they act on: they manage the denominator of consumption by constraining the model's output, while treating the input data — and whatever the model must guess about it — as given.

**Documentation of data.** A separate literature treats the description of data as the object of design. The FAIR principles made machine-actionable metadata a general target for scientific data (Wilkinson et al. 2016), and datasheets brought standardized documentation practice to machine-learning datasets (Gebru et al. 2021). At the same time, field evidence shows that this documentation work is systematically undervalued relative to model work (Sambasivan et al. 2021) — an undervaluation consistent with the economics of complementary investment in general purpose technologies, where the returns to a one-off improvement of a non-rival input accrue to downstream users rather than to the investor (Bresnahan and Trajtenberg 1995). This literature establishes what good description is and why it is underprovided; what it measures is conformance and practice, not what description does to a model's consumption at inference time.

**Open government data: metadata and value.** In the open-government-data literature the same questions appear at portal scale, and empirically. Quarati (2023) assessed roughly 400,000 datasets across national, municipal, and international portals, measuring their usage alongside programmatically assessed metadata quality and examining the relationship between the two; notably, the study did not find a clear positive correlation between better metadata publishing practices and usage — a caution against treating metadata quality as an established driver of use. On the value side, systematic work asks how "high-value datasets" should be determined (Nikiforova et al. 2023), the European Union has fixed a legal list of high-value dataset categories to be published free of charge in machine-readable form (European Commission 2023), and UNESCO's guidance places making data AI-ready among the preparation steps for opening data (UNESCO 2023). Across this line, the value and priority of public data are assessed through publication, usage, quality conformance, and enumerated categories; the consumption of inference compute does not yet appear among the evaluation axes.

**Where this paper sits.** The four groups above have developed largely separately: the first measures a growing consumption problem, the second manages it from the model side, and the third and fourth build and prioritize data description without measuring its consequences for that consumption. This paper connects them by measurement: it varies the description available to the model and reads the result in tokens per outcome. Within this bounded review, we did not identify prior work that directly measures inference token consumption as a function of whether task-relevant data descriptions are available to the model.

## 3. The RoT indicator and the self-description hypothesis

*[TODO: from frozen §3 (definition, suppression/sufficiency) + §4 (self-description, stack layers, training-side and framing-side hypotheses) + the macro-indicator reservations.]*

## 4. Measurements

*[TODO: from frozen §5, preserving the chronological measurement series, reorganized into methods / results / robustness per the 2026-08-28 decision. Includes the retraction record and the measuring-side traps.]*

## 5. Limitations

*[TODO: from frozen §5 "What was not measured" + reservations gathered from the body.]*

## 6. Policy implications

*[TODO: compressed merger of frozen §6–§8: log-derived requirements, investment-priority formula with its task-boundedness caveat, open data as digital public good, digital sovereignty. Framed as policy hypotheses consistent with the PSS.]*

## 7. Conclusion and call for collaboration

*[TODO: from frozen Call for Collaboration.]*

## References

*[TODO: Cambridge A (author–date). Set frozen 2026-08-28: 12 new entries (Wei 2022; DeepSeek-AI 2025; Sui et al. 2025; Chen et al. 2024; Wilkinson et al. 2016; Gebru et al. 2021; Sambasivan et al. 2021; Quarati 2023; Nikiforova et al. 2023; European Commission 2023; UNESCO 2023; Bresnahan and Trajtenberg 1995) + carried-over primary sources from `paper/REFERENCES.en.md` (Gartner 2026; Goldman Sachs Research 2026; Luccioni and Gamazaychikov 2025; Tokenomics Foundation n.d.; MLPerf Power; AI Energy Score; TokenPowerBench; OSI OSAID 1.0; model cards). DOI reachability check for the five classics at formatting time.]*
