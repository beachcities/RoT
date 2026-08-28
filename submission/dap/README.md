# submission/dap/ — Data & Policy 投稿用派生版

このディレクトリは、公開固定版 **v0.2.0**（コミット `d483d6b726fe83fe47cef471270e3982224402bc`、Zenodo版DOI 10.5281/zenodo.22136254）から派生する、Data & Policy（Cambridge University Press）**standard track・Research Article** 投稿用の原稿と付属文書を置く場所です。

- 固定版 `paper/return-on-token.md`（ja正本）・`paper/return-on-token.en.md` は**変更しません**。投稿版はここに別ファイルとして作ります。
- 投稿版の正本は英語です（試論の正本＝jaという関係は固定版側で不変）。
- 決定事項（2026-08-28決裁）：タイトル "Return on Token: An Indicator Linking Data Self-Description to AI Inference Token Consumption"／頭字語の言葉遊びの一文は投稿版では削除／Affiliation＝Independent researcher基本／Keywords＝open government data; data self-description; inference-time scaling; token efficiency; AI governance／Measurementsは時系列を保存しつつ方法・結果・robustness等へ再構成。
- 表記統一（2026-08-28決裁）：投稿派生版は全体で **RoT** 表記に統一する。固定版の **ROT** 表記は変更しない。
- 「公」の扱い（2026-08-28決裁）：政府支出・財政論として前景化しない。shared / collective information infrastructure（社会の器として共有される情報基盤）を中心語彙とし、政府はその担い手の一つに留める。本稿の主線は data self-description → inference token consumption → measurement であり、公的含意はRoTを測定した**結果として最後に届く含意**として扱う。公共支援への言及上限は "some form of shared or collective provision may be worth considering where downstream benefits are difficult for the party making the description investment to capture" 程度。
- Provenance clarification（2026-08-28）：Frozen v0.2.0 第5節の「l5 の151,416字と l6 の2,796字」は、l5側が2課題のcondition-level median、l6側がmain task単独値という集計粒度の混在を含む。投稿派生版4.3ではmain task単独の粒度（279,148字 → 2,796字）に統一した。raw resultの変更ではなく、Frozen側は不変。
- 関連研究のgap文（凍結）："Within this bounded review, we did not identify prior work that directly measures inference token consumption as a function of whether task-relevant data descriptions are available to the model."
- 新規参照文献セット（12件、2026-08-28凍結）はこのREADMEと同じ決裁で確定。既存 `paper/REFERENCES.en.md` 収載の一次資料は続投。

予定ファイル：`manuscript.md`（投稿原稿）／`statements.md`（Abstract・PSS・Keywords・Data Availability・Funding・Author Contributions・Affiliation・Competing Interests・Acknowledgements/AI申告）／`cover-letter.md`／`references.md`（Cambridge A整形）。

進行の正本は本ディレクトリ、経緯はチャット決裁録による。
