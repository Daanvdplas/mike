pub mod types;
use corpus::CaseRecord;
use embedding::{Embedder, LocalEmbeddings};
use std::{collections::BTreeMap, path::Path};
use storage::{EXPECTED_COUNT, EXPECTED_IDS_SHA256, Manifest, PIPELINE, Snapshot};
pub use types::*;

mod chunk;
mod corpus;
mod embedding;
mod ranking;
mod storage;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub(super) struct IndexedPassage {
    case_id: String,
    passage: Passage,
    start_byte: usize,
    end_byte: usize,
    #[serde(skip)]
    vector: Vec<f32>,
}

pub struct Engine {
    snapshot: Snapshot,
    embedder: Box<dyn Embedder>,
}

impl Engine {
    pub fn load(database: &Path, cache: &Path) -> Result<Self, EngineError> {
        // Validate storage before loading a model: a missing database never becomes ready.
        let snapshot = storage::load(database, EXPECTED_COUNT, EXPECTED_IDS_SHA256)?;
        let embedder = LocalEmbeddings::new(cache)?;
        if embedder.config() != &snapshot.manifest.embedding {
            return Err(EngineError::new(
                ErrorKind::IndexUnavailable,
                "The embedding configuration changed; import the corpus again.",
            ));
        }
        for item in &snapshot.passages {
            if embedder.token_count(&item.passage.text)? > chunk::TOKEN_BUDGET {
                return Err(EngineError::new(
                    ErrorKind::IndexUnavailable,
                    "A stored passage exceeds the model token budget.",
                ));
            }
        }
        Ok(Self {
            snapshot,
            embedder: Box::new(embedder),
        })
    }
    pub fn search(
        &mut self,
        query: Option<&str>,
        document_text: Option<&str>,
    ) -> Result<SearchResponse, EngineError> {
        let query = query.map(str::trim).filter(|s| !s.is_empty());
        if document_text.is_some_and(|s| s.trim().is_empty()) {
            return Err(EngineError::new(
                ErrorKind::InvalidInput,
                "The supplied document has no usable text.",
            ));
        }
        if query.is_none() && document_text.is_none() {
            return Err(EngineError::new(
                ErrorKind::InvalidInput,
                "Supply a document or query.",
            ));
        }
        let query_vector = query
            .map(|text| text_vector(self.embedder.as_mut(), text, true))
            .transpose()?;
        let document_vector = document_text
            .map(|text| text_vector(self.embedder.as_mut(), text, false))
            .transpose()?;
        let mode = match (query_vector.is_some(), document_vector.is_some()) {
            (true, true) => "combined",
            (true, false) => "query",
            _ => "document",
        };
        let ranking = ranking::rank_cases(
            &self.snapshot.passages,
            query_vector.as_deref(),
            document_vector.as_deref(),
        )?;
        let results = ranking
            .into_iter()
            .map(|(index, score)| {
                let item = &self.snapshot.passages[index];
                SearchResult {
                    metadata: self.snapshot.cases[&item.case_id].metadata.clone(),
                    score,
                    passage: item.passage.clone(),
                    case_url: format!("/api/cases/{}", item.case_id),
                }
            })
            .collect();
        Ok(SearchResponse {
            mode: mode.into(),
            corpus_version: self.snapshot.manifest.corpus_version.clone(),
            ranking_version: "cosine-max-v1".into(),
            results,
        })
    }
    pub fn get_case(&self, id: &str) -> Result<CaseDetail, EngineError> {
        let case = self
            .snapshot
            .cases
            .get(id)
            .ok_or_else(|| EngineError::new(ErrorKind::CaseNotFound, "Case not found."))?;
        Ok(CaseDetail {
            metadata: case.metadata.clone(),
            corpus_version: self.snapshot.manifest.corpus_version.clone(),
            text: case.text.clone(),
        })
    }
    pub fn health(&self) -> HealthResponse {
        HealthResponse {
            status: "ready".into(),
            corpus_version: self.snapshot.manifest.corpus_version.clone(),
            indexed_case_count: self.snapshot.cases.len(),
        }
    }
}

pub fn import_corpus(
    corpus: &Path,
    database: &Path,
    cache: &Path,
) -> Result<ImportReport, EngineError> {
    let cases = corpus::read_cases(corpus)?;
    check_case_ids(&cases, EXPECTED_COUNT, EXPECTED_IDS_SHA256)?;
    let mut embedder = LocalEmbeddings::new(cache)?;
    let snapshot = build_snapshot(cases, &mut embedder, EXPECTED_COUNT, EXPECTED_IDS_SHA256)?;
    storage::persist(database, &snapshot)?;
    Ok(ImportReport {
        corpus_version: snapshot.manifest.corpus_version.clone(),
        case_count: snapshot.cases.len(),
        passage_count: snapshot.passages.len(),
    })
}

fn check_case_ids(
    cases: &BTreeMap<String, CaseRecord>,
    count: usize,
    ids: &str,
) -> Result<(), EngineError> {
    if cases.len() != count
        || corpus::hash(
            cases
                .keys()
                .cloned()
                .collect::<Vec<_>>()
                .join("\n")
                .as_bytes(),
        ) != ids
    {
        return Err(EngineError::new(
            ErrorKind::IndexUnavailable,
            "The agreed corpus case identifiers are incomplete or different.",
        ));
    }
    Ok(())
}

fn build_snapshot(
    cases: BTreeMap<String, CaseRecord>,
    embedder: &mut dyn Embedder,
    count: usize,
    ids: &str,
) -> Result<Snapshot, EngineError> {
    check_case_ids(&cases, count, ids)?;
    let mut passages = Vec::new();
    for (id, case) in &cases {
        for chunk in chunk::chunk_text(&case.text, id, |text| embedder.token_count(text))? {
            passages.push(IndexedPassage {
                case_id: id.clone(),
                passage: chunk.passage,
                start_byte: chunk.start_byte,
                end_byte: chunk.end_byte,
                vector: Vec::new(),
            });
        }
    }
    let texts: Vec<_> = passages.iter().map(|p| p.passage.text.clone()).collect();
    let vectors = embedder.embed(&texts)?;
    if vectors.len() != passages.len() {
        return Err(EngineError::new(
            ErrorKind::IndexUnavailable,
            "Embedding count does not match corpus passages.",
        ));
    }
    for (passage, vector) in passages.iter_mut().zip(vectors) {
        passage.vector = vector;
    }
    let mut snapshot = Snapshot {
        cases,
        passages,
        manifest: Manifest {
            format_version: 2,
            pipeline: PIPELINE.into(),
            embedding: embedder.config().clone(),
            corpus_version: String::new(),
        },
    };
    snapshot.manifest.corpus_version = storage::fingerprint(&snapshot)?;
    storage::validate(&snapshot, count, ids)?;
    Ok(snapshot)
}

fn text_vector(embedder: &mut dyn Embedder, text: &str, is_query: bool) -> Result<Vec<f32>, EngineError> {
    let text = corpus::canonicalize(text);
    let prefix = if is_query { embedder.config().query_prefix.clone() } else { String::new() };
    let chunks = chunk::chunk_text(&text, "input", |s| embedder.token_count(&format!("{prefix}{s}")))?;
    let texts: Vec<_> = chunks.into_iter().map(|c| format!("{prefix}{}", c.passage.text)).collect();
    let vectors = embedder.embed(&texts)?;
    if vectors.len() != texts.len() {
        return Err(EngineError::new(
            ErrorKind::Internal,
            "Embedding count does not match input passages.",
        ));
    }
    ranking::normalized_mean(&vectors)
}

#[cfg(test)]
mod tests {
    use super::*;
    use embedding::EmbeddingConfig;
    use serde_json::json;

    struct KnownEmbeddings(EmbeddingConfig);

    impl Embedder for KnownEmbeddings {
        fn config(&self) -> &EmbeddingConfig {
            &self.0
        }
        fn token_count(&self, text: &str) -> Result<usize, EngineError> {
            Ok(text.chars().count() + 2)
        }
        fn embed(&mut self, texts: &[String]) -> Result<Vec<Vec<f32>>, EngineError> {
            Ok(texts
                .iter()
                .map(|text| {
                    if text.contains("witness") {
                        vec![1., 0.]
                    } else {
                        vec![0., 1.]
                    }
                })
                .collect())
        }
    }

    fn fixture() -> Engine {
        let mut embedder = KnownEmbeddings(EmbeddingConfig {
            model: "known".into(),
            dimensions: 2,
            max_tokens: 512,
            sdk: "test".into(),
            pooling: "test".into(),
            query_prefix: String::new(),
            artifacts_sha256: "test".into(),
        });
        let cases = (1..=4).map(|id| {
            let case = corpus::parse_case(json!({
                "id":id,"name":"Case","decision_date":"1892-01-01", "court":{"name":"Texas Court of Criminal Appeals"},
                "citations":[{"cite":"Example cite","type":"official"}],
                "casebody":{"opinions":[{"type":"majority","text":if id%2==1 {"witness testimony"} else {"appeal procedure"}}]}
            })).unwrap();
            (id.to_string(), case)
        }).collect();
        let snapshot =
            build_snapshot(cases, &mut embedder, 4, &corpus::hash(b"1\n2\n3\n4")).unwrap();
        Engine {
            snapshot,
            embedder: Box::new(embedder),
        }
    }

    #[test]
    fn query_instruction_is_only_added_to_queries_and_counts_toward_token_budget() {
        struct Recorder {
            config: EmbeddingConfig,
            inputs: Vec<String>,
        }
        impl Embedder for Recorder {
            fn config(&self) -> &EmbeddingConfig { &self.config }
            fn token_count(&self, text: &str) -> Result<usize, EngineError> { Ok(text.chars().count() + 2) }
            fn embed(&mut self, texts: &[String]) -> Result<Vec<Vec<f32>>, EngineError> {
                self.inputs.extend_from_slice(texts);
                Ok(texts.iter().map(|_| vec![1., 0.]).collect())
            }
        }
        let mut recorder = Recorder { config: EmbeddingConfig {
            model:"test".into(), dimensions:2, max_tokens:512, sdk:"test".into(),
            pooling:"test".into(), query_prefix:"Represent this sentence for searching relevant passages: ".into(),
            artifacts_sha256:"test".into(),
        }, inputs:Vec::new() };
        text_vector(&mut recorder, &"query ".repeat(400), true).unwrap();
        assert!(recorder.inputs.len() > 1);
        for input in &recorder.inputs {
            assert!(input.starts_with(&recorder.config.query_prefix));
            assert!(input.chars().count() + 2 <= chunk::TOKEN_BUDGET);
        }
        recorder.inputs.clear();
        text_vector(&mut recorder, "Original document text.", false).unwrap();
        assert_eq!(recorder.inputs, ["Original document text."]);
    }

    #[test]
    fn engine_returns_exact_three_cases_with_detail_versions_in_all_modes() {
        let mut engine = fixture();
        for (query, document, mode, expected) in [
            (Some("witness"), None, "query", ["1", "3", "2"]),
            (None, Some("appeal"), "document", ["2", "4", "1"]),
            (Some("witness"), Some("appeal"), "combined", ["1", "3", "2"]),
        ] {
            let result = engine.search(query, document).unwrap();
            assert_eq!(result.mode, mode);
            assert_eq!(
                result
                    .results
                    .iter()
                    .map(|r| r.metadata.case_id.as_str())
                    .collect::<Vec<_>>(),
                expected
            );
            for hit in result.results {
                let detail = engine.get_case(&hit.metadata.case_id).unwrap();
                assert_eq!(detail.corpus_version, result.corpus_version);
                assert_eq!(detail.metadata.text_version, hit.metadata.text_version);
                let units: Vec<_> = detail.text.encode_utf16().collect();
                assert_eq!(
                    String::from_utf16(&units[hit.passage.start_utf16..hit.passage.end_utf16])
                        .unwrap(),
                    hit.passage.text
                );
            }
        }
        assert_eq!(
            engine.get_case("absent").unwrap_err().kind,
            ErrorKind::CaseNotFound
        );
        assert_eq!(engine.health().indexed_case_count, 4);
    }

    #[test]
    fn full_long_query_is_processed_and_blank_inputs_are_rejected() {
        let mut engine = fixture();
        let long = "appeal ".repeat(600);
        assert!(long.len() > 1000);
        let response = engine.search(Some(&long), None).unwrap();
        assert_eq!(response.results[0].metadata.case_id, "2");
        assert_eq!(
            engine.search(Some(" \n"), None).unwrap_err().kind,
            ErrorKind::InvalidInput
        );
        assert_eq!(
            engine.search(None, None).unwrap_err().kind,
            ErrorKind::InvalidInput
        );
    }

    #[test]
    #[ignore = "requires ADAMI_CORPUS and ADAMI_MODEL_CACHE; imports the real local corpus"]
    fn real_corpus_import_persists_complete_index_and_matching_majority_spans() {
        let corpus = std::env::var_os("ADAMI_CORPUS").expect("Set ADAMI_CORPUS");
        let cache = std::env::var_os("ADAMI_MODEL_CACHE").expect("Set ADAMI_MODEL_CACHE");
        let dir = tempfile::tempdir().unwrap();
        let database = std::env::var_os("ADAMI_SMOKE_DATABASE")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| dir.path().join("cases.sqlite"));
        let report = import_corpus(Path::new(&corpus), &database, Path::new(&cache)).unwrap();
        assert_eq!(report.case_count, 135);
        assert!(report.passage_count > 135);
        let mut engine = Engine::load(&database, Path::new(&cache)).unwrap();
        assert_eq!(engine.health().indexed_case_count, 135);
        assert_eq!(engine.health().corpus_version, report.corpus_version);
        let result = engine.search(Some("trial evidence"), None).unwrap();
        assert_eq!(result.results.len(), 3);
        for item in result.results {
            let detail = engine.get_case(&item.metadata.case_id).unwrap();
            assert_eq!(detail.metadata.text_version, item.metadata.text_version);
            let units: Vec<_> = detail.text.encode_utf16().collect();
            assert_eq!(
                String::from_utf16(&units[item.passage.start_utf16..item.passage.end_utf16])
                    .unwrap(),
                item.passage.text
            );
        }
    }
}
