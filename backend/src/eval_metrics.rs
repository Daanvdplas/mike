//! Model-free scoring of top-three runs. Synthetic examples are not legal judgments.
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DocumentRef {
    pub case_id: String,
    pub text_version: String,
    pub sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MetricScenario {
    pub scenario_id: String,
    pub input_mode: String,
    pub eligible_case_ids: Vec<String>,
    pub excluded_case_ids: Vec<String>,
    pub query_case_id: Option<String>,
    pub document_ref: Option<DocumentRef>,
    pub query: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RankedRun {
    pub scenario_id: String,
    pub input_mode: String,
    pub ranked_case_ids: Vec<String>,
    pub latency_ms: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LabelManifest {
    /// `synthetic` for fixtures or `ai`; neither means human legal validation.
    pub method: String,
    pub model: Option<String>,
    pub created_at: String,
    pub description: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LabelSet {
    pub manifest: LabelManifest,
    pub judgments: Vec<Judgment>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Evidence {
    pub case_id: String,
    pub section: String,
    pub text: String,
    pub start_utf16: usize,
    pub end_utf16: usize,
    pub text_version: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Judgment {
    pub scenario_id: String,
    pub input_mode: String,
    pub query_case_id: Option<String>,
    pub document_ref: Option<DocumentRef>,
    pub query: Option<String>,
    pub candidate_case_id: String,
    pub relevance_grade: u8,
    pub reasoning: String,
    pub evidence: Vec<Evidence>,
    pub judgment_status: String,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Scores {
    pub recall_at_3: Option<f64>,
    pub ndcg_at_3: Option<f64>,
    pub rr_at_3: Option<f64>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ScenarioReport {
    pub scenario_id: String,
    pub input_mode: String,
    pub status: String,
    pub eligible_count: usize,
    pub judged_count: usize,
    pub coverage: f64,
    pub known_positives: usize,
    pub unjudged_case_ids: Vec<String>,
    pub unjudged_ranked_case_ids: Vec<String>,
    pub ranked_case_ids: Vec<String>,
    pub recall_ceiling: Option<f64>,
    pub scores: Scores,
    pub reasons: Vec<String>,
    pub latency_ms: f64,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct MetricMean {
    pub value: Option<f64>,
    pub denominator: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Aggregate {
    pub scope: String,
    pub input_mode: Option<String>,
    pub scenario_count: usize,
    pub scored_count: usize,
    pub no_known_positive_count: usize,
    pub not_scored_count: usize,
    pub recall_at_3: MetricMean,
    pub ndcg_at_3: MetricMean,
    pub mrr_at_3: MetricMean,
    pub latency_sample_count: usize,
    pub latency_small_sample: bool,
    pub latency_p50_ms: Option<f64>,
    pub latency_p95_ms: Option<f64>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EvaluationReport {
    pub schema_version: u32,
    pub quality_status: String,
    pub label_manifest: Option<LabelManifest>,
    pub limitations: Vec<String>,
    pub scenarios: Vec<ScenarioReport>,
    pub aggregates: Vec<Aggregate>,
}

pub fn report(
    scenarios: &[MetricScenario],
    runs: &[RankedRun],
    labels: Option<&LabelSet>,
) -> Result<EvaluationReport, String> {
    use std::collections::{BTreeMap, BTreeSet};
    if scenarios.is_empty() {
        return Err("scenario set must not be empty".into());
    }
    let mut scenario_index = BTreeMap::new();
    for scenario in scenarios {
        validate_scenario(scenario)?;
        if scenario_index
            .insert(&scenario.scenario_id, scenario)
            .is_some()
        {
            return Err(format!("duplicate scenario {}", scenario.scenario_id));
        }
    }
    let mut run_index = BTreeMap::new();
    for run in runs {
        let scenario = scenario_index
            .get(&run.scenario_id)
            .ok_or_else(|| format!("unknown run scenario {}", run.scenario_id))?;
        if run_index.insert(&run.scenario_id, run).is_some() {
            return Err(format!("duplicate run scenario {}", run.scenario_id));
        }
        if run.input_mode != scenario.input_mode || run.ranked_case_ids.len() > 3 {
            return Err(format!(
                "invalid run mode or ranking length for {}",
                run.scenario_id
            ));
        }
        if !run.latency_ms.is_finite() || run.latency_ms < 0.0 {
            return Err(format!("invalid latency for {}", run.scenario_id));
        }
        let mut seen = BTreeSet::new();
        for id in &run.ranked_case_ids {
            if !scenario.eligible_case_ids.contains(id) || !seen.insert(id) {
                return Err(format!(
                    "unknown, excluded or duplicate ranked ID {id} in {}",
                    run.scenario_id
                ));
            }
        }
    }
    if run_index.len() != scenarios.len() {
        return Err("missing scenario run".into());
    }
    let mut judgments = BTreeMap::new();
    if let Some(labels) = labels {
        validate_manifest(&labels.manifest)?;
        for judgment in &labels.judgments {
            let scenario = scenario_index
                .get(&judgment.scenario_id)
                .ok_or_else(|| format!("unknown judgment scenario {}", judgment.scenario_id))?;
            validate_judgment(scenario, judgment)?;
            let key = (&judgment.scenario_id, &judgment.candidate_case_id);
            if judgments.insert(key, judgment.relevance_grade).is_some() {
                return Err(format!(
                    "duplicate judgment for {} / {}",
                    judgment.scenario_id, judgment.candidate_case_id
                ));
            }
        }
    }
    let mut rows = Vec::new();
    for scenario in scenarios {
        let run = run_index[&scenario.scenario_id];
        let grade = |id: &String| judgments.get(&(&scenario.scenario_id, id)).copied();
        let unjudged: Vec<_> = scenario
            .eligible_case_ids
            .iter()
            .filter(|id| grade(id).is_none())
            .cloned()
            .collect();
        let unjudged_ranked: Vec<_> = run
            .ranked_case_ids
            .iter()
            .filter(|id| grade(id).is_none())
            .cloned()
            .collect();
        let judged_count = scenario.eligible_case_ids.len() - unjudged.len();
        let positives = scenario
            .eligible_case_ids
            .iter()
            .filter(|id| grade(id).is_some_and(|g| g >= 2))
            .count();
        let complete = unjudged.is_empty();
        let can_score = judged_count > 0 && unjudged_ranked.is_empty();
        let mut scores = Scores::default();
        let mut reasons = Vec::new();
        let status = if judged_count == 0 {
            reasons
                .push("No eligible candidate judgments; retrieval quality is not scored.".into());
            "not_scored"
        } else if !unjudged_ranked.is_empty() {
            reasons.push("Top-three contains unjudged candidates; no quality score or definitive comparison.".into());
            "unjudged_top3"
        } else if complete {
            "scored_complete"
        } else {
            reasons.push("Pooled/provisional: recall denominator and ideal ranking include only known judgments, not the full corpus.".into());
            "scored_pooled"
        };
        if run.ranked_case_ids.len() < 3 {
            reasons.push("Ranking contains fewer than three cases.".into());
        }
        if can_score {
            let ranked_grades: Vec<_> = run
                .ranked_case_ids
                .iter()
                .map(|id| grade(id).expect("all ranked cases judged"))
                .collect();
            scores.rr_at_3 = Some(
                ranked_grades
                    .iter()
                    .position(|g| *g >= 2)
                    .map_or(0.0, |i| 1.0 / (i + 1) as f64),
            );
            if positives > 0 {
                scores.recall_at_3 = Some(
                    ranked_grades.iter().filter(|g| **g >= 2).count() as f64 / positives as f64,
                );
            } else {
                reasons.push("No known positive candidates: Recall@3 is undefined and excluded from primary macro metrics.".into());
            }
            let mut ideal: Vec<_> = scenario
                .eligible_case_ids
                .iter()
                .filter_map(grade)
                .collect();
            ideal.sort_unstable_by(|a, b| b.cmp(a));
            let ideal_dcg = dcg(&ideal);
            if ideal_dcg > 0.0 {
                scores.ndcg_at_3 = Some(dcg(&ranked_grades) / ideal_dcg);
            } else {
                reasons.push("IDCG@3 is zero: nDCG@3 is undefined.".into());
            }
        }
        rows.push(ScenarioReport {
            scenario_id: scenario.scenario_id.clone(),
            input_mode: scenario.input_mode.clone(),
            status: status.into(),
            eligible_count: scenario.eligible_case_ids.len(),
            judged_count,
            coverage: judged_count as f64 / scenario.eligible_case_ids.len() as f64,
            known_positives: positives,
            unjudged_case_ids: unjudged,
            unjudged_ranked_case_ids: unjudged_ranked,
            ranked_case_ids: run.ranked_case_ids.clone(),
            recall_ceiling: (complete && positives > 0)
                .then(|| positives.min(3) as f64 / positives as f64),
            scores,
            reasons,
            latency_ms: run.latency_ms,
        });
    }
    let mut aggregates = Vec::new();
    for mode in [None, Some("document"), Some("query"), Some("combined")] {
        for scope in ["complete", "pooled"] {
            aggregates.push(aggregate(&rows, scope, mode));
        }
    }
    let any_scored = rows.iter().any(|r| r.scores.rr_at_3.is_some());
    Ok(EvaluationReport {
        schema_version: 1,
        quality_status: if !any_scored { "not_scored" } else if rows.iter().all(|r| r.status == "scored_complete") { "scored_complete" } else { "provisional" }.into(),
        label_manifest: labels.map(|l| l.manifest.clone()),
        limitations: vec![
            "Visible development scenarios; no hidden test-set or general legal accuracy claim.".into(),
            "AI and synthetic judgments are not human legal validation. No labels are generated by this evaluator.".into(),
            "Primary macro metrics include only scenarios with known positives; complete and pooled scores are separate.".into(),
            "Evidence structure is validated here; the runner must verify quotes and versions against canonical source text.".into(),
            "Latency is search only; percentiles use nearest rank and are descriptive for small samples.".into(),
        ],
        scenarios: rows, aggregates,
    })
}

fn validate_scenario(scenario: &MetricScenario) -> Result<(), String> {
    use std::collections::BTreeSet;
    let eligible: BTreeSet<_> = scenario.eligible_case_ids.iter().collect();
    let excluded: BTreeSet<_> = scenario.excluded_case_ids.iter().collect();
    if scenario.scenario_id.trim().is_empty()
        || eligible.is_empty()
        || eligible.len() != scenario.eligible_case_ids.len()
        || excluded.len() != scenario.excluded_case_ids.len()
        || eligible.intersection(&excluded).next().is_some()
        || eligible
            .iter()
            .chain(excluded.iter())
            .any(|s| s.trim().is_empty())
    {
        return Err(format!(
            "invalid candidate universe for {}",
            scenario.scenario_id
        ));
    }
    let has_query = scenario
        .query
        .as_ref()
        .is_some_and(|q| !q.trim().is_empty());
    let valid_mode = match scenario.input_mode.as_str() {
        "query" => has_query && scenario.document_ref.is_none(),
        "document" => scenario.document_ref.is_some() && scenario.query.is_none(),
        "combined" => scenario.document_ref.is_some() && has_query,
        _ => false,
    };
    if !valid_mode {
        return Err(format!("invalid input mode for {}", scenario.scenario_id));
    }
    if let Some(document) = &scenario.document_ref
        && (document.case_id.is_empty()
            || document.text_version.is_empty()
            || document.sha256.len() != 64
            || !document.sha256.bytes().all(|b| b.is_ascii_hexdigit())
            || !excluded.contains(&document.case_id))
    {
        return Err(format!(
            "invalid or non-excluded document reference for {}",
            scenario.scenario_id
        ));
    }
    if let Some(anchor) = &scenario.query_case_id
        && (anchor.is_empty() || !excluded.contains(anchor))
    {
        return Err(format!(
            "source anchor must be excluded for {}",
            scenario.scenario_id
        ));
    }
    Ok(())
}

fn validate_manifest(manifest: &LabelManifest) -> Result<(), String> {
    if !["ai", "synthetic"].contains(&manifest.method.as_str())
        || manifest.created_at.trim().is_empty()
        || manifest.description.trim().is_empty()
        || (manifest.method == "ai" && manifest.model.as_ref().is_none_or(|m| m.trim().is_empty()))
    {
        return Err("label manifest requires explicit synthetic/AI provenance, date, description and AI model".into());
    }
    Ok(())
}

fn validate_judgment(scenario: &MetricScenario, judgment: &Judgment) -> Result<(), String> {
    if judgment.input_mode != scenario.input_mode
        || judgment.query_case_id != scenario.query_case_id
        || judgment.document_ref != scenario.document_ref
        || judgment.query != scenario.query
        || judgment.relevance_grade > 3
        || judgment.judgment_status != "verified"
        || judgment.reasoning.trim().is_empty()
        || (!scenario
            .eligible_case_ids
            .contains(&judgment.candidate_case_id)
            && !scenario
                .excluded_case_ids
                .contains(&judgment.candidate_case_id))
    {
        return Err(format!(
            "invalid judgment/input binding for {} / {}",
            judgment.scenario_id, judgment.candidate_case_id
        ));
    }
    let source = scenario
        .query_case_id
        .as_ref()
        .or_else(|| scenario.document_ref.as_ref().map(|d| &d.case_id));
    let has_candidate = judgment
        .evidence
        .iter()
        .any(|e| e.case_id == judgment.candidate_case_id);
    let has_source = source.is_none_or(|id| judgment.evidence.iter().any(|e| &e.case_id == id));
    if !has_candidate
        || !has_source
        || judgment.evidence.iter().any(|e| {
            e.case_id != judgment.candidate_case_id && source != Some(&e.case_id)
                || e.section != "majority"
                || e.text.is_empty()
                || e.text_version.is_empty()
                || e.end_utf16.checked_sub(e.start_utf16) != Some(e.text.encode_utf16().count())
        })
    {
        return Err(format!(
            "invalid majority evidence for {} / {}",
            judgment.scenario_id, judgment.candidate_case_id
        ));
    }
    Ok(())
}

fn dcg(grades: &[u8]) -> f64 {
    grades
        .iter()
        .take(3)
        .enumerate()
        .map(|(i, g)| (2_f64.powi(i32::from(*g)) - 1.0) / ((i + 2) as f64).log2())
        .sum()
}

fn aggregate(rows: &[ScenarioReport], scope: &str, mode: Option<&str>) -> Aggregate {
    let selected: Vec<_> = rows
        .iter()
        .filter(|r| mode.is_none_or(|m| r.input_mode == m))
        .collect();
    let scored: Vec<_> = selected
        .iter()
        .copied()
        .filter(|r| r.status == format!("scored_{scope}"))
        .collect();
    let primary: Vec<_> = scored
        .iter()
        .copied()
        .filter(|r| r.known_positives > 0)
        .collect();
    let mean = |values: Vec<f64>| MetricMean {
        value: (!values.is_empty()).then(|| values.iter().sum::<f64>() / values.len() as f64),
        denominator: values.len(),
    };
    let mut latencies: Vec<_> = selected.iter().map(|r| r.latency_ms).collect();
    latencies.sort_by(f64::total_cmp);
    let percentile = |p: f64| {
        (!latencies.is_empty())
            .then(|| latencies[((latencies.len() as f64 * p).ceil() as usize).saturating_sub(1)])
    };
    Aggregate {
        scope: scope.into(),
        input_mode: mode.map(String::from),
        scenario_count: selected.len(),
        scored_count: scored.len(),
        no_known_positive_count: scored.iter().filter(|r| r.known_positives == 0).count(),
        not_scored_count: selected
            .iter()
            .filter(|r| r.scores.rr_at_3.is_none())
            .count(),
        recall_at_3: mean(
            primary
                .iter()
                .filter_map(|r| r.scores.recall_at_3)
                .collect(),
        ),
        ndcg_at_3: mean(primary.iter().filter_map(|r| r.scores.ndcg_at_3).collect()),
        mrr_at_3: mean(primary.iter().filter_map(|r| r.scores.rr_at_3).collect()),
        latency_sample_count: latencies.len(),
        latency_small_sample: latencies.len() < 20,
        latency_p50_ms: percentile(0.5),
        latency_p95_ms: percentile(0.95),
    }
}

impl EvaluationReport {
    pub fn markdown(&self) -> String {
        use std::fmt::Write;
        let mut output = format!(
            "# Retrieval evaluation\n\nQuality status: **{}**\n\n",
            self.quality_status
        );
        if let Some(manifest) = &self.label_manifest {
            let _ = writeln!(
                output,
                "Judgments: {} — {}. Human legal validation: none.\n",
                manifest.method, manifest.description
            );
        } else {
            output.push_str("No candidate judgments supplied. Quality metrics are not scored.\n\n");
        }
        output.push_str("| Scenario | Mode | Status | Judged / eligible | Known positives | Recall@3 | nDCG@3 | RR@3 | Search ms |\n|---|---|---|---:|---:|---:|---:|---:|---:|\n");
        let value = |v: Option<f64>| v.map_or_else(|| "undefined".into(), |n| format!("{n:.4}"));
        for row in &self.scenarios {
            let _ = writeln!(
                output,
                "| {} | {} | {} | {} / {} | {} | {} | {} | {} | {:.2} |",
                row.scenario_id,
                row.input_mode,
                row.status,
                row.judged_count,
                row.eligible_count,
                row.known_positives,
                value(row.scores.recall_at_3),
                value(row.scores.ndcg_at_3),
                value(row.scores.rr_at_3),
                row.latency_ms
            );
        }
        output.push_str("\nPrimary macro metrics (known-positive scenarios only; pooled scores are provisional):\n\n| Scope | Mode | Recall@3 (n) | nDCG@3 (n) | MRR@3 (n) |\n|---|---|---:|---:|---:|\n");
        for aggregate in &self.aggregates {
            let _ = writeln!(
                output,
                "| {} | {} | {} ({}) | {} ({}) | {} ({}) |",
                aggregate.scope,
                aggregate.input_mode.as_deref().unwrap_or("all"),
                value(aggregate.recall_at_3.value),
                aggregate.recall_at_3.denominator,
                value(aggregate.ndcg_at_3.value),
                aggregate.ndcg_at_3.denominator,
                value(aggregate.mrr_at_3.value),
                aggregate.mrr_at_3.denominator
            );
        }
        output.push_str("\nSearch latency (nearest-rank percentiles; fewer than 20 samples is a small sample):\n\n| Mode | N | p50 ms | p95 ms | Small sample |\n|---|---:|---:|---:|---|\n");
        for aggregate in self.aggregates.iter().filter(|a| a.scope == "complete") {
            let _ = writeln!(
                output,
                "| {} | {} | {} | {} | {} |",
                aggregate.input_mode.as_deref().unwrap_or("all"),
                aggregate.latency_sample_count,
                value(aggregate.latency_p50_ms),
                value(aggregate.latency_p95_ms),
                aggregate.latency_small_sample
            );
        }
        output.push_str("\nCoverage and limitations:\n\n");
        for row in &self.scenarios {
            let _ = writeln!(
                output,
                "- {}: {}. Unjudged ranked: [{}]. All unjudged: [{}].",
                row.scenario_id,
                row.reasons.join(" "),
                row.unjudged_ranked_case_ids.join(", "),
                row.unjudged_case_ids.join(", ")
            );
        }
        for limitation in &self.limitations {
            let _ = writeln!(output, "- {limitation}");
        }
        output
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scenario() -> MetricScenario {
        MetricScenario {
            scenario_id: "SYNTHETIC-1".into(),
            input_mode: "query".into(),
            eligible_case_ids: ["a", "b", "c", "d"].map(String::from).to_vec(),
            excluded_case_ids: vec!["source".into()],
            query_case_id: Some("source".into()),
            document_ref: None,
            query: Some("Synthetic question".into()),
        }
    }
    fn run(ids: &[&str]) -> RankedRun {
        RankedRun {
            scenario_id: "SYNTHETIC-1".into(),
            input_mode: "query".into(),
            ranked_case_ids: ids.iter().map(|id| (*id).into()).collect(),
            latency_ms: 10.0,
        }
    }
    fn labels(grades: &[(&str, u8)]) -> LabelSet {
        let s = scenario();
        LabelSet {
            manifest: LabelManifest {
                method: "synthetic".into(),
                model: None,
                created_at: "2026-11-11".into(),
                description: "SYNTHETIC formula fixtures, no legal judgments".into(),
            },
            judgments: grades
                .iter()
                .map(|(id, grade)| Judgment {
                    scenario_id: s.scenario_id.clone(),
                    input_mode: s.input_mode.clone(),
                    query_case_id: s.query_case_id.clone(),
                    document_ref: None,
                    query: s.query.clone(),
                    candidate_case_id: (*id).into(),
                    relevance_grade: *grade,
                    reasoning: "Synthetic grade for arithmetic".into(),
                    evidence: ["source", *id]
                        .into_iter()
                        .map(|case| Evidence {
                            case_id: case.into(),
                            section: "majority".into(),
                            text: "x".into(),
                            start_utf16: 0,
                            end_utf16: 1,
                            text_version: "synthetic-v1".into(),
                        })
                        .collect(),
                    judgment_status: "verified".into(),
                })
                .collect(),
        }
    }
    fn score(ids: &[&str], grades: &[(&str, u8)]) -> EvaluationReport {
        report(&[scenario()], &[run(ids)], Some(&labels(grades))).unwrap()
    }
    fn near(actual: Option<f64>, expected: f64) {
        assert!((actual.unwrap() - expected).abs() < 1e-12);
    }

    #[test]
    fn absent_labels_remain_not_scored_and_visible_as_unjudged() {
        let r = report(&[scenario()], &[run(&["a", "b", "c"])], None).unwrap();
        assert_eq!(r.quality_status, "not_scored");
        assert_eq!(r.scenarios[0].scores.rr_at_3, None);
        assert_eq!(r.scenarios[0].coverage, 0.0);
        assert_eq!(r.scenarios[0].unjudged_case_ids.len(), 4);
        assert!(r.markdown().contains("not_scored"));
        assert!(
            serde_json::to_string(&r)
                .unwrap()
                .contains("\"recall_at_3\":null")
        );
    }
    #[test]
    fn hand_computed_grades_preserve_ranking_and_macro_denominators() {
        let r = score(&["b", "c", "a"], &[("a", 3), ("b", 0), ("c", 2), ("d", 1)]);
        let s = &r.scenarios[0];
        near(s.scores.recall_at_3, 1.0);
        near(s.scores.rr_at_3, 0.5);
        near(
            s.scores.ndcg_at_3,
            (3.0 / 3_f64.log2() + 7.0 / 2.0) / (7.0 + 3.0 / 3_f64.log2() + 1.0 / 2.0),
        );
        assert_eq!(r.aggregates[0].mrr_at_3.denominator, 1);
    }
    #[test]
    fn grade_one_only_has_defined_ndcg_without_binary_recall() {
        let r = score(&["b", "a", "c"], &[("a", 1), ("b", 0), ("c", 0), ("d", 0)]);
        let s = &r.scenarios[0];
        assert_eq!(s.scores.recall_at_3, None);
        near(s.scores.rr_at_3, 0.0);
        near(s.scores.ndcg_at_3, 1.0 / 3_f64.log2());
        assert_eq!(r.aggregates[0].ndcg_at_3.denominator, 0);
    }
    #[test]
    fn empty_ranking_and_zero_idcg_are_distinct_from_missing_run() {
        let r = score(&[], &[("a", 2), ("b", 0), ("c", 0), ("d", 0)]);
        near(r.scenarios[0].scores.recall_at_3, 0.0);
        near(r.scenarios[0].scores.ndcg_at_3, 0.0);
        near(r.scenarios[0].scores.rr_at_3, 0.0);
        let r = score(&[], &[("a", 0), ("b", 0), ("c", 0), ("d", 0)]);
        assert_eq!(r.scenarios[0].scores.ndcg_at_3, None);
        assert!(report(&[scenario()], &[], None).is_err());
    }
    #[test]
    fn more_than_three_positives_have_an_actual_complete_recall_ceiling() {
        let r = score(&["a", "b", "c"], &[("a", 2), ("b", 2), ("c", 2), ("d", 2)]);
        near(r.scenarios[0].scores.recall_at_3, 0.75);
        near(r.scenarios[0].recall_ceiling, 0.75);
    }
    #[test]
    fn unknown_top_results_prevent_scoring_not_become_grade_zero() {
        let r = score(&["a", "b", "c"], &[("a", 3)]);
        assert_eq!(r.scenarios[0].status, "unjudged_top3");
        assert_eq!(r.scenarios[0].scores.ndcg_at_3, None);
        assert_eq!(r.scenarios[0].unjudged_ranked_case_ids, vec!["b", "c"]);
        assert_eq!(r.scenarios[0].recall_ceiling, None);
    }
    #[test]
    fn fully_judged_top_three_with_partial_pool_is_separate_from_complete_scores() {
        let r = score(&["a", "b", "c"], &[("a", 3), ("b", 0), ("c", 2)]);
        assert_eq!(r.scenarios[0].status, "scored_pooled");
        near(r.scenarios[0].scores.recall_at_3, 1.0);
        assert_eq!(r.aggregates[0].recall_at_3.denominator, 0);
        assert_eq!(r.aggregates[1].recall_at_3.denominator, 1);
    }
    #[test]
    fn excluded_positive_labels_never_change_eligible_denominator_or_ideal() {
        let r = score(
            &["a", "b", "c"],
            &[("source", 3), ("a", 2), ("b", 0), ("c", 0), ("d", 0)],
        );
        near(r.scenarios[0].scores.recall_at_3, 1.0);
        near(r.scenarios[0].scores.ndcg_at_3, 1.0);
        assert_eq!(r.scenarios[0].known_positives, 1);
    }
    #[test]
    fn rejects_invalid_ranking_and_scenario_manifests() {
        for ids in [
            vec!["a", "a"],
            vec!["unknown"],
            vec!["source"],
            vec!["a", "b", "c", "d"],
        ] {
            assert!(
                report(&[scenario()], &[run(&ids)], None).is_err(),
                "{ids:?}"
            );
        }
        assert!(report(&[scenario(), scenario()], &[run(&[])], None).is_err());
        assert!(report(&[scenario()], &[run(&[]), run(&[])], None).is_err());
        let mut r = run(&[]);
        r.input_mode = "combined".into();
        assert!(report(&[scenario()], &[r], None).is_err());
        let mut s = scenario();
        s.eligible_case_ids.push("source".into());
        assert!(report(&[s], &[run(&[])], None).is_err());
        let mut s = scenario();
        s.excluded_case_ids.clear();
        assert!(report(&[s], &[run(&[])], None).is_err());
    }
    #[test]
    fn rejects_unbound_or_unaccepted_labels_and_invalid_evidence() {
        for mutation in 0..7 {
            let mut l = labels(&[("a", 2)]);
            let j = &mut l.judgments[0];
            match mutation {
                0 => j.relevance_grade = 4,
                1 => j.judgment_status = "draft".into(),
                2 => j.query = Some("Different question".into()),
                3 => j.candidate_case_id = "unknown".into(),
                4 => j.evidence[0].end_utf16 = 3,
                5 => j.evidence.clear(),
                _ => l.judgments.push(l.judgments[0].clone()),
            }
            assert!(
                report(&[scenario()], &[run(&[])], Some(&l)).is_err(),
                "mutation {mutation}"
            );
        }
    }
    #[test]
    fn latency_reports_sample_size_small_sample_warning_and_nearest_rank() {
        let r = report(&[scenario()], &[run(&[])], None).unwrap();
        let json = serde_json::to_value(&r.aggregates[0]).unwrap();
        assert_eq!(json["latency_sample_count"], 1);
        assert_eq!(json["latency_small_sample"], true);
        near(r.aggregates[0].latency_p50_ms, 10.0);
        near(r.aggregates[0].latency_p95_ms, 10.0);
        assert!(r.markdown().contains("p95"));
    }
    #[test]
    fn primary_macro_is_equal_weight_and_keeps_undefined_scenarios_out() {
        let first = scenario();
        let mut second = scenario();
        second.scenario_id = "SYNTHETIC-2".into();
        let mut third = scenario();
        third.scenario_id = "SYNTHETIC-3".into();
        let r1 = run(&["a", "b", "c"]);
        let mut r2 = run(&["b", "c", "a"]);
        r2.scenario_id = second.scenario_id.clone();
        r2.latency_ms = 20.0;
        let mut r3 = run(&[]);
        r3.scenario_id = third.scenario_id.clone();
        r3.latency_ms = 30.0;
        let mut l = labels(&[("a", 2), ("b", 0), ("c", 0), ("d", 0)]);
        let other: Vec<_> = l
            .judgments
            .iter()
            .cloned()
            .map(|mut j| {
                j.scenario_id = second.scenario_id.clone();
                j
            })
            .collect();
        l.judgments.extend(other);
        let other: Vec<_> = l
            .judgments
            .iter()
            .take(4)
            .cloned()
            .map(|mut j| {
                j.scenario_id = third.scenario_id.clone();
                j.relevance_grade = 0;
                j
            })
            .collect();
        l.judgments.extend(other);
        let r = report(&[first, second, third], &[r1, r2, r3], Some(&l)).unwrap();
        assert_eq!(r.aggregates[0].mrr_at_3.denominator, 2);
        near(r.aggregates[0].mrr_at_3.value, 2.0 / 3.0);
        near(r.aggregates[0].latency_p50_ms, 20.0);
        near(r.aggregates[0].latency_p95_ms, 30.0);
        assert_eq!(r.aggregates[0].no_known_positive_count, 1);
    }
    #[test]
    fn ai_manifest_requires_a_model_and_invalid_latencies_are_rejected() {
        let mut l = labels(&[("a", 2)]);
        l.manifest.method = "ai".into();
        assert!(report(&[scenario()], &[run(&[])], Some(&l)).is_err());
        for latency in [-1.0, f64::NAN, f64::INFINITY] {
            let mut r = run(&[]);
            r.latency_ms = latency;
            assert!(report(&[scenario()], &[r], None).is_err());
        }
    }
    #[test]
    fn document_reference_hashes_are_bound_to_judgments() {
        let mut s = scenario();
        s.input_mode = "combined".into();
        s.document_ref = Some(DocumentRef {
            case_id: "source".into(),
            text_version: "synthetic-v1".into(),
            sha256: "a".repeat(64),
        });
        let mut r = run(&[]);
        r.input_mode = "combined".into();
        let mut l = labels(&[("a", 2)]);
        l.judgments[0].input_mode = "combined".into();
        assert!(report(&[s.clone()], &[r.clone()], Some(&l)).is_err());
        l.judgments[0].document_ref = s.document_ref.clone();
        assert!(report(&[s], &[r], Some(&l)).is_ok());
    }
}
