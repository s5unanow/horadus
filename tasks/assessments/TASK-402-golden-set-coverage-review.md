# TASK-402 Golden-Set Coverage Review

Review date: 2026-04-27
Status: signed off for approved subset

Scope:
- Promote `INTAKE-0029` into a human-gated golden-set curation task.
- Prepare source-backed candidate rows for weak trend/signal coverage.
- Do not change `config/trends/*.yaml`, eval validators, benchmark logic, or
  prompt/model baselines in this task.

Autonomous stop point:
- Human sign-off was provided in-thread on 2026-04-28: "Proceed with
  recommended path. Signed."
- Approved rows may be added to `ai/eval/gold_set.jsonl` with
  `label_verification="human_verified"`.
- Held/rejected rows remain review candidates only and must not be inserted
  without a later explicit review decision.

Human sign-off:
- Reviewer: repo owner, in-thread sign-off
- Review date: 2026-04-28
- Decision: approve recommended subset
- Notes: Add accepted source-backed rows; hold rows requiring exact extraction;
  reject/replace the Su-24 proxy-label candidate; drop the duplicative Montreux
  trigger candidate.

Validation notes:
- Docs updates: N/A unless final row curation changes operator-facing eval
  policy. This artifact records the review trail requested by the task.
- Integration proof: N/A. This task is data/assessment only and does not touch
  integration-covered runtime paths.
- Benchmark baseline promotion: N/A. Gold-set content changes supersede prior
  baseline comparisons; this task does not promote a new accepted benchmark
  baseline artifact.

Coverage snapshot before candidate additions:
- Current gold-set rows: 325, last ID `eval-0325`.
- All rows are currently `human_verified`.
- Priority zero Tier-2 coverage signals:
  - `ai-control.ai_safety_incident`
  - `ai-control.llm_gatekeeping_deployment`
  - `global-infectious-threat.hospitalization_surge`
  - `global-infectious-threat.international_travel_restriction`
  - `global-infectious-threat.lab_biosafety_incident`
  - `parallel-enclaves-europe.segregation_index_change`
  - `parallel-enclaves-europe.institutional_trust_collapse`
  - `parallel-enclaves-europe.education_integration_metrics`
  - `fertility-decline.childcare_affordability_gain`
  - `fertility-decline.immigration_fertility_offset`
  - `dollar-hegemony-erosion.sanctions_deescalation`

Candidate rows for human review:

Review constraints before insertion:
- Proposed IDs are provisional. After rejects/holds are removed, accepted rows
  must be renumbered contiguously after `eval-0325`.
- The label shapes below are not complete insertion labels yet. Final gold-set
  rows must include full `expected.tier1.trend_scores` dictionaries, including
  plausible cross-trend scores where applicable.
- Single-source rows in contested or ambiguity-prone domains need corroboration
  before sign-off, especially `eval-0329`, `eval-0337`, and any retained
  Russia-Turkey incident row.
- Historical training examples are acceptable, but final row text must state the
  event date clearly so reviewers do not read older events as current activity.

Applied sign-off mapping:
- Added to `ai/eval/gold_set.jsonl` as `eval-0326` through `eval-0339`:
  original candidates `eval-0326` through `eval-0331`, `eval-0335` through
  `eval-0340`, `eval-0342`, and `eval-0343`.
- Held for later extraction: original candidates `eval-0332`, `eval-0333`,
  `eval-0334`, and `eval-0341`.
- Rejected or dropped: original candidates `eval-0344` and `eval-0345`.
- Accepted rows were renumbered contiguously after `eval-0325`.

| Proposed ID | Trend | Signal | Direction | Suggested title | Label shape | Source trail | Human decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `eval-0326` | `ai-control` | `ai_safety_incident` | escalatory | California suspends Cruise robotaxi permits after pedestrian-dragging incident | max relevance 8; severity 0.64; confidence 0.88 | California DMV suspended Cruise driverless testing and deployment permits on October 24, 2023, citing public-safety risk and alleged safety misrepresentation. Source: https://www.dmv.ca.gov/portal/news-and-media/dmv-statement-on-cruise-llc-suspension/ | accepted and inserted as `eval-0326` |
| `eval-0327` | `ai-control` | `llm_gatekeeping_deployment` | escalatory | Meta documents automated AI systems used to detect and remove violating content | max relevance 8; severity 0.62; confidence 0.78; needs full cross-trend scores, plausibly including low/moderate `elite-mass-polarization` relevance | Meta transparency materials describe automated technology that detects likely policy violations and actions content at platform scale. Source: https://transparency.meta.com/enforcement/detecting-violations/technology-detects-violations/ | accepted and inserted as `eval-0327` |
| `eval-0328` | `ai-control` | `llm_gatekeeping_deployment` | escalatory | YouTube expands machine-learning age estimation to gate teen protections and access | max relevance 7; severity 0.50; confidence 0.78 | YouTube announced machine-learning age estimation that infers whether users are likely under 18 and applies teen-specific experience restrictions. Source: https://blog.youtube/news-and-events/improving-age-estimation-to-protect-teens/ | accepted and inserted as `eval-0328` |
| `eval-0329` | `global-infectious-threat` | `hospitalization_surge` | escalatory | WHO requests China respiratory-illness data after reports of pediatric hospital pressure | max relevance 7; severity 0.55; confidence 0.84 | WHO DON494, "Upsurge of respiratory illnesses among children - Northern China," dated November 23, 2023, reported increased outpatient consultations and hospital admissions among children while noting known pathogens and no exceeded hospital capacity. Source: https://www.who.int/emergencies/disease-outbreak-news/item/2023-DON494. Needs corroborating source before sign-off because China outbreak reporting is contested. | accepted and inserted as `eval-0329` |
| `eval-0330` | `global-infectious-threat` | `international_travel_restriction` | escalatory | United States restricts travel from southern Africa after Omicron variant detection | max relevance 8; severity 0.70; confidence 0.88 | Historical training example from November 2021. The U.S. restricted entry from several southern African countries after Omicron detection; WHO separately advised against blanket travel bans. Sources: https://www.whitehouse.gov/briefing-room/presidential-actions/2021/11/26/a-proclamation-on-suspension-of-entry-as-immigrants-and-nonimmigrants-of-certain-additional-persons-who-pose-a-risk-of-transmitting-coronavirus-disease-2019/ and https://www.who.int/news-room/articles-detail/who-advice-for-international-traffic-in-relation-to-the-sars-cov-2-omicron-variant | accepted and inserted as `eval-0330` |
| `eval-0331` | `global-infectious-threat` | `lab_biosafety_incident` | escalatory | CDC anthrax lab incident exposes biosafety-control failure | max relevance 6; severity 0.48; confidence 0.86 | Historical training example from 2014. CDC's internal review documented a laboratory incident creating potential anthrax exposure for staff. Source: https://www.cdc.gov/od/science/integrity/docs/FINAL_Anthrax_Report.pdf | accepted and inserted as `eval-0331` |
| `eval-0332` | `parallel-enclaves-europe` | `segregation_index_change` | escalatory | Sweden's segregation barometer tracks municipality-level residential segregation | max relevance 6; severity 0.45; confidence 0.70 | Boverket's official Segregationsbarometern provides municipality and residential-area segregation trend data; final row needs a concrete municipality/time-window extract. Source: https://segregationsbarometern.boverket.se/ | held for extraction |
| `eval-0333` | `parallel-enclaves-europe` | `institutional_trust_collapse` | escalatory | Swedish Crime Survey provides justice-system trust indicators for enclave-risk contexts | max relevance 6; severity 0.45; confidence 0.72 | Brå's Swedish Crime Survey provides trend data on confidence in the criminal justice system; final row must avoid "collapse" language unless the selected table supports a sharp decline. Source: https://bra.se/bra-in-english/home/publications/archive/publications/2024-10-09-swedish-crime-survey-2024.html | held for extraction |
| `eval-0334` | `parallel-enclaves-europe` | `education_integration_metrics` | de_escalatory | OECD PISA immigrant-background results support education-integration metric review | max relevance 6; severity 0.42; confidence 0.70 | OECD PISA 2022 reports comparable outcomes by immigrant background and socioeconomic controls; final row should use a specific country metric showing convergence or improvement. Source: https://www.oecd.org/en/publications/pisa-2022-results-volume-i_53f23881-en.html | held for extraction |
| `eval-0335` | `fertility-decline` | `childcare_affordability_gain` | de_escalatory | Canada expands reduced-fee child care under national early learning agreements | max relevance 7; severity 0.50; confidence 0.86 | Government of Canada materials document reduced child-care fees and federal-provincial early learning agreements. Source: https://www.canada.ca/en/employment-social-development/campaigns/child-care.html | accepted and inserted as `eval-0332` |
| `eval-0336` | `fertility-decline` | `immigration_fertility_offset` | de_escalatory | ONS reports births by parents' country of birth in England and Wales | max relevance 6; severity 0.44; confidence 0.82 | ONS birth statistics separate births by parents' country of birth, supporting a demographic-composition offset row if the final text avoids overstating fertility recovery. Source: https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages/livebirths/bulletins/parentscountryofbirthenglandandwales/2024 | accepted and inserted as `eval-0333` |
| `eval-0337` | `dollar-hegemony-erosion` | `sanctions_deescalation` | de_escalatory | OFAC General License 44 temporarily authorizes Venezuela oil and gas transactions | max relevance 7; severity 0.48; confidence 0.88 | Historical sanctions-relief example. OFAC GL 44 was issued October 18, 2023 and temporarily authorized Venezuela oil and gas transactions through April 18, 2024; OFAC GL 44A superseded it on April 17, 2024 as a wind-down license through May 31, 2024. Sources: https://ofac.treasury.gov/media/932231/download?inline= and https://ofac.treasury.gov/system/files/2024-04/venezuela_gl44a.pdf. Needs corroborating context before sign-off because later wind-down materially changes current-state interpretation. | accepted and inserted as `eval-0334` |
| `eval-0338` | `south-america-agri-supply-shift` | `trade_agreement_expansion` | escalatory | EU-Mercosur agreement creates market-access pathway for South American agricultural exports | max relevance 7; severity 0.55; confidence 0.82 | European Commission materials describe the EU-Mercosur agreement framework and market-access provisions. Source: https://policy.trade.ec.europa.eu/eu-trade-relationships-country-and-region/countries-and-regions/mercosur/eu-mercosur-agreement_en | accepted and inserted as `eval-0335` |
| `eval-0339` | `south-america-agri-supply-shift` | `trade_agreement_expansion` | escalatory | USDA APHIS finalizes rule allowing fresh beef imports from Paraguay | max relevance 7; severity 0.58; confidence 0.90 | USDA APHIS finalized a rule allowing fresh beef imports from Paraguay under animal-health conditions. Source: https://www.aphis.usda.gov/news/agency-announcements/aphis-finalizes-rule-import-fresh-beef-paraguay | accepted and inserted as `eval-0336` |
| `eval-0340` | `south-america-agri-supply-shift` | `export_volume_cagr_growth` | escalatory | Argentina grain report supports corn export-growth candidate row | max relevance 6; severity 0.46; confidence 0.76 | USDA FAS reporting supports a modest Argentina corn export recovery row: production around 49 million tons and exports around 34-35 million tons, about one million tons above 2023-24 and highest since 2020-21. Source: https://www.fas.usda.gov/data/argentina-grain-and-feed-update-26 | accepted and inserted as `eval-0337` |
| `eval-0341` | `south-america-agri-supply-shift` | `export_volume_cagr_growth` | pending | Uruguay livestock report supports beef export-volume candidate row | direction, max relevance, severity, and confidence pending extraction | USDA FAS Uruguay livestock reporting provides beef production, slaughter, and export estimates. Direction must be decided only after exact values are extracted; do not pre-label escalatory if volumes are flat. Source: https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Livestock%20and%20Products%20Annual_Montevideo_Uruguay_UY2024-0010.pdf | hold for extraction |
| `eval-0342` | `africa-agri-supply-shift` | `yield_productivity_jump` | escalatory | USDA Ethiopia grain report documents wheat production and yield context | max relevance 6; severity 0.50; confidence 0.76 | USDA FAS forecasts Ethiopia wheat production at about 6.5 million metric tons in MY 2025/26, driven by improved yields and expanded irrigated farmland. Source: https://www.fas.usda.gov/data/ethiopia-grain-and-feed-annual-8 | accepted and inserted as `eval-0338` |
| `eval-0343` | `africa-agri-supply-shift` | `agri_infrastructure_investment` | escalatory | World Bank Tanzania transport project targets corridor and port logistics improvements | max relevance 6; severity 0.46; confidence 0.78 | The World Bank Tanzania Transport Integration Project targets transport/corridor improvements relevant to export logistics. Source: https://projects.worldbank.org/en/projects-operations/project-detail/P165660 | accepted and inserted as `eval-0339` |
| `eval-0344` | `russia-turkey` | `syria_proxy_clash` | escalatory | Turkey shoots down Russian Su-24 after border violation claim | reject or replace | Historical 2015 direct state-on-state shootdown. This is strong Russia-Turkey conflict evidence but is an odd fit for `syria_proxy_clash`; only the broader deconfliction-failure concept fits. Replace with a cleaner Syria proxy/deconfliction row or document the signal-name fuzziness before sign-off. Source: https://www.nato.int/cps/en/natohq/news_125052.htm | reject/replace |
| `eval-0345` | `russia-turkey` | `straits_restriction` | escalatory | Turkey closes Bosphorus and Dardanelles to warships under Montreux during Ukraine war | drop as duplicative by default; if retained, severity should be at least 0.70 and full cross-trend scores should include `eu-russia` | Historical February 2022 trigger for the same straits closure already covered by `eval-0047` and `eval-0048`; the existing ongoing-enforcement row has severity 0.65, so this initiating event should not be weaker if retained. Source: https://news.usni.org/2022/02/28/turkey-closes-bosphorus-dardanelles-to-warships | drop unless explicitly retained |

Rows needing extra extraction before gold-set insertion:
- `eval-0332`: extract one concrete segregation time series from Boverket rather
  than using the portal generically.
- `eval-0333`: extract the exact Brå confidence metric and use neutral wording
  if there is no sharp decline.
- `eval-0334`: extract a specific PISA country metric showing convergence or
  improvement before using a de-escalatory Tier-2 label.
- `eval-0340`, `eval-0341`, and `eval-0342`: quote exact USDA FAS marketing-year
  figures before finalizing row content.
- `eval-0341`: decide direction only after Uruguay beef figures are extracted.
  Do not keep the preliminary escalatory label if volumes are flat.
- `eval-0344`: replace with a cleaner `syria_proxy_clash`/deconfliction example
  or document an explicit signal-name mismatch waiver.
- `eval-0345`: drop as duplicative unless reviewer specifically wants the
  initiating February 2022 closure row; if retained, recalibrate severity above
  the existing ongoing-enforcement row and include `eu-russia` in Tier-1 scores.
- All retained rows: complete full multi-trend `tier1.trend_scores` before
  insertion.

Post-sign-off application checklist:
- [ ] Confirm accepted row IDs remain contiguous after the current tail row.
- [ ] Add accepted rows to `ai/eval/gold_set.jsonl`.
- [ ] Set accepted rows to `label_verification="human_verified"` only after the
      reviewer decision above is completed.
- [ ] Re-run taxonomy validation:
      `uv run --no-sync horadus eval validate-taxonomy --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --tier1-trend-mode subset --signal-type-mode warn --unknown-trend-mode warn`
- [ ] Re-run audit:
      `uv run --no-sync horadus eval audit --gold-set ai/eval/gold_set.jsonl --output-dir ai/eval/results --max-items 0 --fail-on-warnings`
- [ ] Re-run targeted eval tests:
      `uv run --no-sync pytest tests/unit/eval/test_taxonomy_validation.py tests/unit/eval/test_audit.py tests/unit/eval/test_benchmark.py`
- [ ] Re-run benchmark:
      `uv run --no-sync horadus eval benchmark --gold-set ai/eval/gold_set.jsonl --trend-config-dir config/trends --output-dir ai/eval/results --max-items 200 --require-human-verified`
- [ ] Re-run strict local gate:
      `uv run --no-sync horadus tasks local-gate --full`
