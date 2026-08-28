# Front matter and disclosure statements — Data & Policy submission

*Approved wordings (2026-08-28 decisions). Working file for the manuscript's front matter and end-of-text statements. Bracketed items are pending factual verification — never to be filled by guess.*

## Title

Return on Token: An Indicator Linking Data Self-Description to AI Inference Token Consumption

## Abstract (≤250 words; measured 250)

Inference-time scaling has made compute consumption a policy-relevant resource: reasoning models emit long chains of thought, and part of that expenditure goes to guessing at premises — field meanings, units, code definitions — that the input data never states. We propose Return on Token (RoT), defined as outcome obtained per total tokens invested, with recursive and discarded search tokens in the denominator, and examine the hypothesis that RoT varies with the self-description of data. In a minimal benchmark varying self-description over ten levels across two fixed synthetic tasks, a boundary appeared at the same position in all six systems measured: below the level at which required code meanings appear inside the document, tasks were rarely or never solved within a ten-attempt ceiling, while at that level they were solved in minimal attempts. Total consumption fell by factors of roughly 14–33 across systems measured with repetition. On the five-fold-repetition local route, the step (22–33×) stood against a within-level spread of at most 2.7× — an order of magnitude apart. A single-repetition run at roughly a quarter of the capacity showed an 8.5× step and solved the levels the description reached, but failed one higher level that the larger model solves, showing a limit to how far additional description coincided with successful performance at lower capacity. An external reference alone left consumption on the unsolved side. We also derive candidate requirements from the reasoning of failed attempts. Transfer to real data has not been measured. We discuss implications for prioritising open-data investment.

## Policy significance statement (≤120 words; measured 113)

Open data is shared information infrastructure, and AI systems increasingly consume compute when using it. When data does not state what its fields, units, and codes mean, models can spend inference compute resolving or guessing at missing meanings. On the synthetic tasks we constructed, adding the missing description inside the document cut that consumption by an order of magnitude and let a model a quarter of the size complete most, though not all, of the same levels. Whether these reductions carry over to real operational data has not yet been measured. If they do, Return on Token offers a policy hypothesis for prioritising investments in data description according to recurring downstream compute savings.

## Keywords (≤5)

open government data; data self-description; inference-time scaling; token efficiency; AI governance

## Data availability statement

The measurements reported in this article are supported by a frozen benchmark and artifact release. The benchmark implementation, task data, prompts, raw run records, and analysis scripts are openly available in the beachcities/RoT repository (https://github.com/beachcities/RoT) and archived on Zenodo (all-versions DOI: 10.5281/zenodo.22090097). The release supporting this article is v0.2.0 (DOI: 10.5281/zenodo.22136254; commit d483d6b726fe83fe47cef471270e3982224402bc). Reproduction steps are documented in the repository.

## Funding statement

This work received no specific grant from any funding agency, commercial or not-for-profit sectors.

## Author contributions (CRediT, sole author)

M.Y.: Conceptualization; Methodology; Software; Validation; Formal analysis; Investigation; Data curation; Writing – original draft; Writing – review and editing; Visualization; Project administration.

*(Journal policy: AI tools do not qualify for authorship; AI involvement is declared in the Acknowledgements and cover letter, not here.)*

## Affiliation

Independent researcher, Chiba, Japan.

*(Decision 2026-08-28: the study was conducted, supported, and approved by no institution; employment is disclosed under Competing interests, not here. Internal clearance for outside publication is handled by the author.)*

## Competing interests

Competing interests: The author is employed by the Digital Agency, Government of Japan, where his responsibilities include open data policy. This article is independent, personal work and does not represent the views of the Digital Agency or the Government of Japan. The employer had no role in the study design, measurement, analysis, or the decision to publish.

*(To be fact-checked by the author before submission.)*

## Acknowledgements (including AI-use declaration)

The author made use of large language model assistants in preparing this article and its underlying benchmark: [tools with material contribution, enumerated from provenance records; names, versions, and periods to be verified from the actual records — not to be estimated] for drafting and editing text in Japanese under the author's direction, translating the author's Japanese text into English, and writing and reviewing benchmark and analysis code. All reported measurements were produced by the published benchmark code; the sentence classifiers used in the analysis are rule-based and do not use LLMs, as stated in the text. The author reviewed and verified all content and is entirely responsible for the scientific content of the paper.

*(The same declaration, in two sentences, goes in the cover letter.)*
