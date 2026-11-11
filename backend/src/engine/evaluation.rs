//! Reproducible development-scenario execution using the production scorer.
use super::{Engine, EngineError, ErrorKind, SearchResponse, corpus};
use crate::eval_metrics::{DocumentRef, MetricScenario, RankedRun};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Component, Path},
    time::{Instant, SystemTime, UNIX_EPOCH},
};

fn validate_evidence(
    evidence: &crate::eval_metrics::Evidence,
    cases: &BTreeMap<String, corpus::CaseRecord>,
) -> EvalResult<()> {
    let case = cases
        .get(&evidence.case_id)
        .ok_or_else(|| invalid("Evidence references an unknown case."))?;
    let utf16: Vec<_> = case.text.encode_utf16().collect();
    if evidence.section != "majority"
        || evidence.text_version != case.metadata.text_version
        || evidence.start_utf16 >= evidence.end_utf16
        || evidence.end_utf16 > utf16.len()
        || String::from_utf16(&utf16[evidence.start_utf16..evidence.end_utf16])? != evidence.text
    {
        return Err(invalid(
            "Label evidence does not match the canonical majority text and version.",
        )
        .into());
    }
    Ok(())
}

type EvalResult<T> = Result<T, Box<dyn std::error::Error>>;
fn invalid(message: &str) -> EngineError {
    EngineError::new(ErrorKind::InvalidInput, message)
}

#[derive(Debug, Deserialize)]
struct Catalog {
    schema_version: u32,
    status: String,
    scenarios: Vec<Scenario>,
}
impl Catalog {
    fn parse(bytes: &[u8]) -> EvalResult<Self> {
        let catalog: Self = serde_json::from_slice(bytes)?;
        if catalog.schema_version != 1
            || catalog.status != "ontwerp"
            || catalog.scenarios.is_empty()
        {
            return Err(
                invalid("Expected a nonempty version-1 development scenario catalog.").into(),
            );
        }
        let mut seen = BTreeSet::new();
        for scenario in &catalog.scenarios {
            if scenario.id.trim().is_empty() || !seen.insert(&scenario.id) {
                return Err(invalid("Duplicate or empty scenario identifier.").into());
            }
            scenario.has_document()?;
            scenario.visible_query()?;
            if scenario.query_case_id != scenario.source_case.id {
                return Err(invalid("Scenario anchor/source identifiers differ.").into());
            }
        }
        Ok(catalog)
    }
}
#[derive(Debug, Deserialize)]
struct Scenario {
    id: String,
    input_mode: String,
    query_case_id: String,
    source_case: SourceCase,
    document: Option<Document>,
    query: Option<Query>,
}
#[derive(Debug, Deserialize)]
struct SourceCase {
    id: String,
    file: String,
    decision_date: String,
}
#[derive(Debug, Deserialize)]
struct Document {
    field: String,
    opinion_type: String,
    sha256: String,
}
#[derive(Debug, Deserialize)]
struct Query {
    en: String,
}
impl Scenario {
    fn has_document(&self) -> EvalResult<bool> {
        let expected = match self.input_mode.as_str() {
            "query" => false,
            "document" | "combined" => true,
            _ => return Err(invalid("Unknown scenario input mode.").into()),
        };
        if self.document.is_some() != expected {
            return Err(invalid("Document conflicts with scenario input mode.").into());
        }
        if let Some(document) = &self.document
            && (document.field != "casebody.opinions[0].text"
                || document.opinion_type != "majority")
        {
            return Err(invalid("Only the specified majority opinion is document input.").into());
        }
        Ok(expected)
    }
    fn visible_query(&self) -> EvalResult<Option<&str>> {
        let expected = match self.input_mode.as_str() {
            "document" => false,
            "query" | "combined" => true,
            _ => return Err(invalid("Unknown scenario input mode.").into()),
        };
        if self.query.is_some() != expected
            || self.query.as_ref().is_some_and(|q| q.en.trim().is_empty())
        {
            return Err(invalid("Query conflicts with scenario input mode or is empty.").into());
        }
        Ok(self.query.as_ref().map(|q| q.en.as_str()))
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SourceReference {
    pub case_id: String,
    pub file: String,
    pub raw_sha256: String,
    pub canonical_sha256: String,
    pub text_version: String,
}
struct PreparedScenario {
    id: String,
    mode: String,
    query: Option<String>,
    document: Option<String>,
    source: SourceReference,
}
pub struct EvaluationPlan {
    scenarios_sha256: String,
    corpus_sources_sha256: String,
    cases: BTreeMap<String, corpus::CaseRecord>,
    scenarios: Vec<PreparedScenario>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RawScenarioRun {
    pub scenario_id: String,
    pub input_mode: String,
    pub ranked_case_ids: Vec<String>,
    pub latency_ms: f64,
    pub excluded_case_ids: Vec<String>,
    pub eligible_case_count: usize,
    pub source: SourceReference,
    pub response: SearchResponse,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct RunArtifact {
    pub schema_version: u32,
    pub runner_version: String,
    pub run_id: String,
    pub executable_sha256: Option<String>,
    pub started_unix_ms: u128,
    pub scenarios_sha256: String,
    pub corpus_sources_sha256: String,
    pub index_manifest: serde_json::Value,
    pub latency_definition: String,
    pub metric_scenarios: Vec<MetricScenario>,
    pub runs: Vec<RawScenarioRun>,
}
impl RunArtifact {
    pub fn ranked_runs(&self) -> Vec<RankedRun> {
        self.runs
            .iter()
            .map(|run| RankedRun {
                scenario_id: run.scenario_id.clone(),
                input_mode: run.input_mode.clone(),
                ranked_case_ids: run.ranked_case_ids.clone(),
                latency_ms: run.latency_ms,
            })
            .collect()
    }
}
impl EvaluationPlan {
    /// Validate all catalog entries before filtering; source roots are explicit, never inferred from a developer's home directory.
    pub fn load(scenario_file: &Path, corpus_root: &Path, selected: &[String]) -> EvalResult<Self> {
        let raw = std::fs::read(scenario_file)?;
        let catalog = Catalog::parse(&raw)?;
        let cases = corpus::read_cases(corpus_root)?;
        let mut source_hashes = BTreeMap::new();
        let source_dir = if corpus_root.join("json").is_dir() {
            corpus_root.join("json")
        } else {
            corpus_root.to_owned()
        };
        for entry in std::fs::read_dir(source_dir)? {
            let path = entry?.path();
            if path
                .extension()
                .is_some_and(|extension| extension == "json")
            {
                source_hashes.insert(
                    path.file_name().unwrap().to_string_lossy().into_owned(),
                    corpus::hash(&std::fs::read(&path)?),
                );
            }
        }
        let corpus_sources_sha256 = corpus::hash(&serde_json::to_vec(&source_hashes)?);
        let requested: BTreeSet<_> = selected.iter().collect();
        if requested.len() != selected.len()
            || requested
                .iter()
                .any(|id| !catalog.scenarios.iter().any(|s| &s.id == *id))
        {
            return Err(invalid("Unknown or duplicate scenario selection.").into());
        }
        let mut prepared = Vec::new();
        for scenario in catalog.scenarios {
            let relative = Path::new(&scenario.source_case.file);
            if relative
                .components()
                .any(|component| !matches!(component, Component::Normal(_)))
            {
                return Err(
                    invalid("Source file must be a relative path without traversal.").into(),
                );
            }
            let raw_source = std::fs::read(corpus_root.join(relative))?;
            let source_value: serde_json::Value = serde_json::from_slice(&raw_source)?;
            let source = corpus::parse_case(source_value.clone())?;
            if source.metadata.case_id != scenario.query_case_id
                || source.metadata.decision_date != scenario.source_case.decision_date
                || cases
                    .get(&source.metadata.case_id)
                    .is_none_or(|c| c.source_json != source.source_json)
            {
                return Err(invalid(
                    "Scenario source identity, metadata or corpus record changed.",
                )
                .into());
            }
            let sha256 = corpus::hash(source.text.as_bytes());
            if let Some(document) = &scenario.document
                && (document.sha256 != sha256
                    || source_value["casebody"]["opinions"][0]["type"] != "majority"
                    || source_value["casebody"]["opinions"][0]["text"].as_str()
                        != Some(source.text.as_str()))
            {
                return Err(invalid("Scenario document hash or majority field changed.").into());
            }
            let query = scenario.visible_query()?.map(str::to_owned);
            let document = scenario.has_document()?.then(|| source.text.clone());
            if requested.is_empty() || requested.contains(&scenario.id) {
                prepared.push(PreparedScenario {
                    id: scenario.id,
                    mode: scenario.input_mode,
                    query,
                    document,
                    source: SourceReference {
                        case_id: source.metadata.case_id,
                        file: scenario.source_case.file,
                        raw_sha256: corpus::hash(&raw_source),
                        canonical_sha256: sha256,
                        text_version: source.metadata.text_version,
                    },
                });
            }
        }
        Ok(Self {
            scenarios_sha256: corpus::hash(&raw),
            corpus_sources_sha256,
            cases,
            scenarios: prepared,
        })
    }
    fn validate_snapshot(&self, snapshot: &super::storage::Snapshot) -> EvalResult<()> {
        if self.cases.len() != snapshot.cases.len()
            || self.cases.iter().any(|(id, source)| {
                snapshot.cases.get(id).is_none_or(|indexed| {
                    indexed.source_json != source.source_json
                        || indexed.metadata != source.metadata
                        || indexed.text != source.text
                })
            })
        {
            return Err(invalid("Evaluation corpus differs from the loaded search index.").into());
        }
        Ok(())
    }
    fn validate_artifact(
        &self,
        artifact: &RunArtifact,
        snapshot: &super::storage::Snapshot,
    ) -> EvalResult<()> {
        self.validate_snapshot(snapshot)?;
        if artifact.schema_version != 1
            || artifact.runner_version != "rust-eval-v1"
            || artifact.scenarios_sha256 != self.scenarios_sha256
            || artifact.corpus_sources_sha256 != self.corpus_sources_sha256
            || artifact.index_manifest != serde_json::to_value(&snapshot.manifest)?
            || artifact.runs.len() != self.scenarios.len()
            || artifact.metric_scenarios.len() != self.scenarios.len()
        {
            return Err(invalid(
                "Run artifact versions, source hashes or scenario counts changed.",
            )
            .into());
        }
        for ((scenario, raw), metric) in self
            .scenarios
            .iter()
            .zip(&artifact.runs)
            .zip(&artifact.metric_scenarios)
        {
            let expected = scenario.metric_scenario(&self.cases);
            if raw.scenario_id != scenario.id
                || raw.input_mode != scenario.mode
                || raw.source != scenario.source
                || raw.excluded_case_ids != expected.excluded_case_ids
                || raw.eligible_case_count != expected.eligible_case_ids.len()
                || serde_json::to_value(metric)? != serde_json::to_value(&expected)?
                || raw.response.mode != scenario.mode
                || raw.response.corpus_version != snapshot.manifest.corpus_version
                || raw.response.ranking_version != "cosine-max-v1"
                || raw.ranked_case_ids
                    != raw
                        .response
                        .results
                        .iter()
                        .map(|hit| hit.metadata.case_id.clone())
                        .collect::<Vec<_>>()
            {
                return Err(invalid(
                    "Raw response, ranking and declared evaluation inputs differ.",
                )
                .into());
            }
            for hit in &raw.response.results {
                let case = self
                    .cases
                    .get(&hit.metadata.case_id)
                    .ok_or_else(|| invalid("Unknown result case."))?;
                if hit.metadata != case.metadata
                    || !hit.score.is_finite()
                    || !(-1.0..=1.0).contains(&hit.score)
                    || !snapshot
                        .passages
                        .iter()
                        .any(|p| p.case_id == hit.metadata.case_id && p.passage == hit.passage)
                {
                    return Err(invalid(
                        "Result metadata or passage differs from the indexed source.",
                    )
                    .into());
                }
            }
            for pair in raw.response.results.windows(2) {
                if pair[0].score < pair[1].score
                    || (pair[0].score == pair[1].score
                        && pair[0].metadata.case_id > pair[1].metadata.case_id)
                {
                    return Err(invalid(
                        "Result ordering conflicts with score and case tie-breaking.",
                    )
                    .into());
                }
            }
        }
        crate::eval_metrics::report(&artifact.metric_scenarios, &artifact.ranked_runs(), None)
            .map_err(|error| invalid(&error))?;
        Ok(())
    }
    pub fn execute(self, engine: &mut Engine) -> EvalResult<RunArtifact> {
        self.validate_snapshot(&engine.snapshot)?;
        let started_unix_ms = SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis();
        let mut artifact = RunArtifact {schema_version:1, runner_version:"rust-eval-v1".into(), run_id:format!("{started_unix_ms}-{}", &self.scenarios_sha256[..12]), executable_sha256:None, started_unix_ms,
            scenarios_sha256:self.scenarios_sha256, corpus_sources_sha256:self.corpus_sources_sha256,
            index_manifest:serde_json::to_value(&engine.snapshot.manifest)?,
            latency_definition:"Sequential search wall time: query/document canonicalization, embedding and exhaustive ranking; excludes catalog/source/index/model loading and report serialization. First scenario is the first inference after model load; later scenarios share the same loaded model. No synthetic warm-up or repeated samples.".into(), metric_scenarios:Vec::new(), runs:Vec::new()};
        for scenario in self.scenarios {
            let metric = scenario.metric_scenario(&self.cases);
            let excluded_case_ids = metric.excluded_case_ids.clone();
            let eligible_case_count = metric.eligible_case_ids.len();
            artifact.metric_scenarios.push(metric);
            let start = Instant::now();
            let response = engine.search_excluding(
                scenario.query.as_deref(),
                scenario.document.as_deref(),
                &excluded_case_ids,
            )?;
            let latency_ms = start.elapsed().as_secs_f64() * 1000.;
            if response.mode != scenario.mode {
                return Err(invalid("Reported input mode differs from the scenario.").into());
            }
            let ranked_case_ids: Vec<_> = response
                .results
                .iter()
                .map(|hit| hit.metadata.case_id.clone())
                .collect();
            for hit in &response.results {
                let detail = engine.get_case(&hit.metadata.case_id)?;
                let utf16: Vec<_> = detail.text.encode_utf16().collect();
                if hit.metadata.text_version != detail.metadata.text_version
                    || response.corpus_version != detail.corpus_version
                    || hit.passage.start_utf16 > hit.passage.end_utf16
                    || hit.passage.end_utf16 > utf16.len()
                    || String::from_utf16(&utf16[hit.passage.start_utf16..hit.passage.end_utf16])?
                        != hit.passage.text
                {
                    return Err(
                        invalid("Result passage is not bound to the indexed source text.").into(),
                    );
                }
            }
            artifact.runs.push(RawScenarioRun {
                scenario_id: scenario.id,
                input_mode: scenario.mode,
                ranked_case_ids,
                latency_ms,
                excluded_case_ids,
                eligible_case_count,
                source: scenario.source,
                response,
            });
        }
        Ok(artifact)
    }
}
impl PreparedScenario {
    fn metric_scenario(&self, cases: &BTreeMap<String, corpus::CaseRecord>) -> MetricScenario {
        let excluded_case_ids = vec![self.source.case_id.clone()];
        MetricScenario {
            scenario_id: self.id.clone(),
            input_mode: self.mode.clone(),
            eligible_case_ids: cases
                .keys()
                .filter(|id| !excluded_case_ids.contains(id))
                .cloned()
                .collect(),
            excluded_case_ids,
            query_case_id: Some(self.source.case_id.clone()),
            query: self.query.clone(),
            document_ref: self.document.as_ref().map(|_| DocumentRef {
                case_id: self.source.case_id.clone(),
                text_version: self.source.text_version.clone(),
                sha256: self.source.canonical_sha256.clone(),
            }),
        }
    }
}

/// Optional labels are checked against exact corpus text before scoring.
pub fn score_labels(
    artifact: &RunArtifact,
    labels: Option<&crate::eval_metrics::LabelSet>,
    corpus_root: &Path,
) -> EvalResult<crate::eval_metrics::EvaluationReport> {
    if let Some(labels) = labels {
        let cases = corpus::read_cases(corpus_root)?;
        for judgment in &labels.judgments {
            for evidence in &judgment.evidence {
                validate_evidence(evidence, &cases)?;
            }
        }
    }
    Ok(
        crate::eval_metrics::report(&artifact.metric_scenarios, &artifact.ranked_runs(), labels)
            .map_err(|error| invalid(&error))?,
    )
}

/// Re-score a recorded run without loading an embedding model.
pub fn read_validated_run(
    run_file: &Path,
    scenario_file: &Path,
    corpus_root: &Path,
    database: &Path,
) -> EvalResult<RunArtifact> {
    let artifact: RunArtifact = serde_json::from_slice(&std::fs::read(run_file)?)?;
    let ids: Vec<_> = artifact
        .runs
        .iter()
        .map(|run| run.scenario_id.clone())
        .collect();
    let plan = EvaluationPlan::load(scenario_file, corpus_root, &ids)?;
    let snapshot = super::storage::load(
        database,
        super::storage::EXPECTED_COUNT,
        super::storage::EXPECTED_IDS_SHA256,
    )?;
    plan.validate_artifact(&artifact, &snapshot)?;
    Ok(artifact)
}

fn write_json(directory: &Path, name: &str, value: &impl Serialize) -> EvalResult<()> {
    use std::io::Write;
    std::fs::create_dir_all(directory)?;
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(directory.join(name))?;
    serde_json::to_writer_pretty(&mut file, value)?;
    file.write_all(b"\n")?;
    Ok(())
}

pub fn write_outputs(
    output: &Path,
    artifact: &RunArtifact,
    report: &crate::eval_metrics::EvaluationReport,
) -> EvalResult<()> {
    use std::io::Write;
    std::fs::create_dir(output)?;
    write_json(output, "run.json", artifact)?;
    write_json(output, "rankings.json", &artifact.ranked_runs())?;
    write_json(output, "report.json", report)?;
    let mut markdown = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(output.join("report.md"))?;
    markdown.write_all(report.markdown().as_bytes())?;
    Ok(())
}

pub fn executable_sha256() -> EvalResult<String> {
    use sha2::{Digest, Sha256};
    use std::io::Read;
    let mut file = std::fs::File::open(std::env::current_exe()?)?;
    let mut hash = Sha256::new();
    let mut buffer = [0; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn exact_visible_mode_inputs_reject_hidden_documents_and_empty_queries() {
        let scenario = json!({"id":"E1", "input_mode":"query", "query_case_id":"1",
            "source_case":{"id":"1", "name":"Case", "file":"json/a.json", "decision_date":"1892-01-01"},
            "document":null,"query":{"en":"visible question","nl":"read translation"}});
        let parsed: Scenario = serde_json::from_value(scenario.clone()).unwrap();
        assert_eq!(parsed.visible_query().unwrap(), Some("visible question"));
        assert!(!parsed.has_document().unwrap());
        let mut invalid = scenario.clone();
        invalid["document"] =
            json!({"field":"casebody.opinions[0].text", "opinion_type":"majority", "sha256":"abc"});
        assert!(
            serde_json::from_value::<Scenario>(invalid)
                .unwrap()
                .has_document()
                .is_err()
        );
        let mut invalid = scenario;
        invalid["query"]["en"] = json!("   ");
        assert!(
            serde_json::from_value::<Scenario>(invalid)
                .unwrap()
                .visible_query()
                .is_err()
        );
    }

    #[test]
    fn shipped_catalog_has_twenty_five_unique_designs_in_fixed_order() {
        let raw = include_bytes!("../../../docs/evals/scenarios.json");
        let catalog = Catalog::parse(raw).unwrap();
        assert_eq!(catalog.scenarios.len(), 25);
        assert_eq!(catalog.scenarios[0].id, "E01");
        assert_eq!(catalog.scenarios[24].id, "E25");
        let mut value: serde_json::Value = serde_json::from_slice(raw).unwrap();
        value["scenarios"][1] = value["scenarios"][0].clone();
        assert!(Catalog::parse(&serde_json::to_vec(&value).unwrap()).is_err());
        value["schema_version"] = json!(2);
        assert!(Catalog::parse(&serde_json::to_vec(&value).unwrap()).is_err());
    }
    #[test]
    fn plan_binds_source_and_hashes_runs_each_mode_without_self_matches() {
        let mut engine = super::super::tests::fixture();
        let directory = tempfile::tempdir().unwrap();
        std::fs::create_dir(directory.path().join("json")).unwrap();
        for (id, case) in &engine.snapshot.cases {
            std::fs::write(
                directory.path().join(format!("json/{id}.json")),
                &case.source_json,
            )
            .unwrap();
        }
        let sha = corpus::hash(engine.snapshot.cases["1"].text.as_bytes());
        let scenarios: Vec<_> = ["query", "document", "combined"].iter().enumerate().map(|(i, mode)| json!({
            "id":format!("E{i}"),"input_mode":mode,"query_case_id":"1",
            "source_case":{"id":"1","name":"Display alias only","file":"json/1.json","decision_date":"1892-01-01"},
            "document":if *mode == "query" {serde_json::Value::Null} else {json!({"field":"casebody.opinions[0].text","opinion_type":"majority","sha256":sha})},
            "query":if *mode == "document" {serde_json::Value::Null} else {json!({"en":"appeal","nl":"NOT INPUT"})}
        })).collect();
        let path = directory.path().join("scenarios.json");
        std::fs::write(
            &path,
            serde_json::to_vec(
                &json!({"schema_version":1,"status":"ontwerp","scenarios":scenarios}),
            )
            .unwrap(),
        )
        .unwrap();
        let plan = EvaluationPlan::load(&path, directory.path(), &[]).unwrap();
        let run = plan.execute(&mut engine).unwrap();
        assert_eq!(run.runs.len(), 3);
        assert_eq!(run.runs[0].ranked_case_ids, ["2", "4", "3"]);
        for row in &run.runs {
            assert_eq!(row.ranked_case_ids.len(), 3);
            assert!(!row.ranked_case_ids.contains(&"1".into()));
            assert_eq!(row.eligible_case_count, 3);
        }
        assert!(run.metric_scenarios[0].document_ref.is_none());
        assert_eq!(run.metric_scenarios[0].query.as_deref(), Some("appeal"));
        assert!(EvaluationPlan::load(&path, directory.path(), &["missing".into()]).is_err());
        let mut changed_source: serde_json::Value =
            serde_json::from_str(&engine.snapshot.cases["1"].source_json).unwrap();
        changed_source["casebody"]["opinions"][0]["text"] = json!("\r\nwitness testimony\r\n");
        std::fs::write(
            directory.path().join("json/1.json"),
            serde_json::to_vec(&changed_source).unwrap(),
        )
        .unwrap();
        assert!(
            EvaluationPlan::load(&path, directory.path(), &[]).is_err(),
            "v1 must not silently normalize a different exact document input"
        );
        std::fs::write(
            directory.path().join("json/1.json"),
            &engine.snapshot.cases["1"].source_json,
        )
        .unwrap();
        let mut bad: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        bad["scenarios"][1]["document"]["sha256"] = json!("wrong");
        std::fs::write(&path, serde_json::to_vec(&bad).unwrap()).unwrap();
        assert!(EvaluationPlan::load(&path, directory.path(), &[]).is_err());
    }

    #[test]
    fn evidence_validation_checks_actual_canonical_text_not_only_span_length() {
        let engine = super::super::tests::fixture();
        let mut evidence = crate::eval_metrics::Evidence {
            case_id: "1".into(),
            section: "majority".into(),
            text: "witness".into(),
            start_utf16: 0,
            end_utf16: 7,
            text_version: engine.snapshot.cases["1"].metadata.text_version.clone(),
        };
        assert!(validate_evidence(&evidence, &engine.snapshot.cases).is_ok());
        evidence.text = "factual".into();
        assert!(validate_evidence(&evidence, &engine.snapshot.cases).is_err());
        evidence.text = "witness".into();
        evidence.text_version = "old".into();
        assert!(validate_evidence(&evidence, &engine.snapshot.cases).is_err());
    }

    #[test]
    fn raw_artifact_validation_rejects_ranking_and_source_tampering() {
        let mut engine = super::super::tests::fixture();
        let case = engine.snapshot.cases["1"].clone();
        let source = SourceReference {
            case_id: "1".into(),
            file: "json/1.json".into(),
            raw_sha256: corpus::hash(case.source_json.as_bytes()),
            canonical_sha256: corpus::hash(case.text.as_bytes()),
            text_version: case.metadata.text_version,
        };
        let prepared = || PreparedScenario {
            id: "E0".into(),
            mode: "query".into(),
            query: Some("appeal".into()),
            document: None,
            source: source.clone(),
        };
        let plan = || EvaluationPlan {
            scenarios_sha256: corpus::hash(b"catalog"),
            corpus_sources_sha256: corpus::hash(b"sources"),
            cases: engine.snapshot.cases.clone(),
            scenarios: vec![prepared()],
        };
        let first_plan = plan();
        let validation_plan = plan();
        let mut artifact = first_plan.execute(&mut engine).unwrap();
        assert!(
            validation_plan
                .validate_artifact(&artifact, &engine.snapshot)
                .is_ok()
        );
        artifact.runs[0].ranked_case_ids.swap(0, 1);
        assert!(
            validation_plan
                .validate_artifact(&artifact, &engine.snapshot)
                .is_err()
        );
        artifact.runs[0].ranked_case_ids.swap(0, 1);
        artifact.runs[0].source.raw_sha256 = "changed".into();
        assert!(
            validation_plan
                .validate_artifact(&artifact, &engine.snapshot)
                .is_err()
        );
    }

    #[test]
    fn output_directory_is_created_once_and_never_overwrites_a_run() {
        let directory = tempfile::tempdir().unwrap();
        let output = directory.path().join("run");
        write_json(&output, "test.json", &serde_json::json!({"synthetic":true})).unwrap();
        assert!(
            write_json(
                &output,
                "test.json",
                &serde_json::json!({"synthetic":false})
            )
            .is_err()
        );
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(
                &std::fs::read(output.join("test.json")).unwrap()
            )
            .unwrap()["synthetic"],
            true
        );
    }
}
