//! Import workers exit between bounded batches, releasing all native allocations.
use super::{
    EngineError, ErrorKind, ImportReport, IndexedPassage, check_case_ids, corpus,
    embedding::{Embedder, EmbeddingConfig, LocalEmbeddings},
    prepare_passages,
    storage::{self, EXPECTED_COUNT, EXPECTED_IDS_SHA256, Manifest, PIPELINE, Snapshot},
};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    path::Path,
    process::{Command, Stdio},
};

const WORKER_PASSAGE_LIMIT: usize = 256;

#[derive(Serialize, Deserialize)]
pub struct ImportBatch {
    offset: usize,
    total: usize,
    source_sha256: String,
    embedding: EmbeddingConfig,
    rows: Vec<BatchRow>,
}

#[derive(Serialize, Deserialize)]
struct BatchRow {
    passage: IndexedPassage,
    vector: Vec<f32>,
}

fn invalid(message: &str) -> EngineError {
    EngineError::new(ErrorKind::IndexUnavailable, message)
}

fn source_hash(cases: &BTreeMap<String, corpus::CaseRecord>) -> Result<String, EngineError> {
    serde_json::to_vec(cases)
        .map(|bytes| corpus::hash(&bytes))
        .map_err(|_| invalid("Cannot fingerprint import sources."))
}

/// Internal subprocess command. Only this short-lived worker loads an ONNX model.
pub fn import_batch(
    corpus: &Path,
    cache: &Path,
    offset: usize,
) -> Result<ImportBatch, EngineError> {
    let cases = corpus::read_cases(corpus)?;
    check_case_ids(&cases, EXPECTED_COUNT, EXPECTED_IDS_SHA256)?;
    let mut embedder = LocalEmbeddings::new(cache)?;
    let mut passages = prepare_passages(&cases, &embedder)?;
    let total = passages.len();
    if offset >= total {
        return Err(invalid("Import batch offset is outside the corpus."));
    }
    let selected = passages.drain(offset..total.min(offset + WORKER_PASSAGE_LIMIT));
    let selected: Vec<_> = selected.collect();
    let texts: Vec<_> = selected.iter().map(|p| p.passage.text.clone()).collect();
    let vectors = embedder.embed(&texts)?;
    if vectors.len() != selected.len() {
        return Err(invalid("Import batch has missing embeddings."));
    }
    Ok(ImportBatch {
        offset,
        total,
        source_sha256: source_hash(&cases)?,
        embedding: embedder.config().clone(),
        rows: selected
            .into_iter()
            .zip(vectors)
            .map(|(passage, vector)| BatchRow { passage, vector })
            .collect(),
    })
}

/// The parent owns source records and vectors, but never initializes a model.
pub fn import_corpus(
    corpus: &Path,
    database: &Path,
    cache: &Path,
) -> Result<ImportReport, EngineError> {
    let binary = std::env::current_exe()
        .map_err(|_| invalid("Cannot find the import worker executable."))?;
    import_with_binary(corpus, database, cache, &binary)
}

pub(super) fn import_with_binary(
    corpus: &Path,
    database: &Path,
    cache: &Path,
    binary: &Path,
) -> Result<ImportReport, EngineError> {
    let cases = corpus::read_cases(corpus)?;
    check_case_ids(&cases, EXPECTED_COUNT, EXPECTED_IDS_SHA256)?;
    import_with_worker(
        cases,
        database,
        EXPECTED_COUNT,
        EXPECTED_IDS_SHA256,
        |offset| {
            // No new process group: all sequential children remain inside the outer guard.
            let output = Command::new(binary)
                .arg("import-batch")
                .arg(corpus)
                .arg(offset.to_string())
                .env("ADAMI_CACHE_DIR", cache)
                .stdout(Stdio::piped())
                .stderr(Stdio::inherit())
                .output()
                .map_err(|_| invalid("Cannot launch the bounded import worker."))?;
            if !output.status.success() {
                return Err(invalid(
                    "The bounded import worker failed; no index was published.",
                ));
            }
            serde_json::from_slice(&output.stdout)
                .map_err(|_| invalid("Invalid import worker output."))
        },
    )
}

fn import_with_worker(
    cases: BTreeMap<String, corpus::CaseRecord>,
    database: &Path,
    count: usize,
    ids: &str,
    worker: impl FnMut(usize) -> Result<ImportBatch, EngineError>,
) -> Result<ImportReport, EngineError> {
    let snapshot = collect_batches(cases, count, ids, worker)?;
    publish(database, &snapshot)
}

fn collect_batches(
    cases: BTreeMap<String, corpus::CaseRecord>,
    count: usize,
    ids: &str,
    mut worker: impl FnMut(usize) -> Result<ImportBatch, EngineError>,
) -> Result<Snapshot, EngineError> {
    let expected_source = source_hash(&cases)?;
    let mut passages = Vec::new();
    let mut total = None;
    let mut embedding = None;
    loop {
        let batch = worker(passages.len())?;
        if batch.offset != passages.len()
            || batch.total <= batch.offset
            || batch.rows.len() != WORKER_PASSAGE_LIMIT.min(batch.total - batch.offset)
            || batch.source_sha256 != expected_source
            || total.is_some_and(|total| total != batch.total)
            || embedding
                .as_ref()
                .is_some_and(|config| config != &batch.embedding)
        {
            return Err(invalid(
                "Import batch offset, size, source or model configuration changed.",
            ));
        }
        total = Some(batch.total);
        embedding = Some(batch.embedding);
        for mut row in batch.rows {
            row.passage.vector = row.vector;
            passages.push(row.passage);
        }
        eprintln!(
            "Imported {}/{} passages; worker process exited",
            passages.len(),
            batch.total
        );
        if passages.len() == batch.total {
            break;
        }
    }
    let mut snapshot = Snapshot {
        cases,
        passages,
        manifest: Manifest {
            format_version: 3,
            pipeline: PIPELINE.into(),
            embedding: embedding.ok_or_else(|| invalid("No import configuration."))?,
            corpus_version: String::new(),
        },
    };
    snapshot.manifest.corpus_version = storage::fingerprint(&snapshot)?;
    storage::validate(&snapshot, count, ids)?;
    Ok(snapshot)
}

fn publish(database: &Path, snapshot: &Snapshot) -> Result<ImportReport, EngineError> {
    storage::persist(database, snapshot)?;
    Ok(ImportReport {
        corpus_version: snapshot.manifest.corpus_version.clone(),
        case_count: snapshot.cases.len(),
        passage_count: snapshot.passages.len(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn batch(engine: &super::super::Engine, offset: usize) -> ImportBatch {
        ImportBatch {
            offset,
            total: engine.snapshot.passages.len(),
            source_sha256: source_hash(&engine.snapshot.cases).unwrap(),
            embedding: engine.snapshot.manifest.embedding.clone(),
            rows: engine
                .snapshot
                .passages
                .iter()
                .skip(offset)
                .take(WORKER_PASSAGE_LIMIT)
                .map(|p| BatchRow {
                    passage: p.clone(),
                    vector: p.vector.clone(),
                })
                .collect(),
        }
    }

    #[test]
    fn complete_bounded_batches_preserve_every_passage_and_publish_once() {
        let engine = super::super::tests::fixture();
        let mut offsets = Vec::new();
        let snapshot = collect_batches(
            engine.snapshot.cases.clone(),
            4,
            &corpus::hash(b"1\n2\n3\n4"),
            |offset| {
                offsets.push(offset);
                Ok(batch(&engine, offset))
            },
        )
        .unwrap();
        assert_eq!(offsets, [0]);
        assert_eq!(snapshot.passages.len(), 8);
        let dir = tempfile::tempdir().unwrap();
        let database = dir.path().join("cases.sqlite");
        publish(&database, &snapshot).unwrap();
        let loaded = storage::load(&database, 4, &corpus::hash(b"1\n2\n3\n4")).unwrap();
        assert_eq!(
            loaded.manifest.corpus_version,
            snapshot.manifest.corpus_version
        );
    }

    #[test]
    fn partial_worker_failure_never_publishes_a_database_or_runs_parallel_workers() {
        let engine = super::super::tests::fixture();
        let dir = tempfile::tempdir().unwrap();
        let database = dir.path().join("not-published.sqlite");
        let mut offsets = Vec::new();
        let result = import_with_worker(
            engine.snapshot.cases.clone(),
            &database,
            4,
            &corpus::hash(b"1\n2\n3\n4"),
            |offset| {
                offsets.push(offset);
                if offset != 0 {
                    return Err(invalid("Simulated second worker failure."));
                }
                let mut value = batch(&engine, 0);
                value.total = WORKER_PASSAGE_LIMIT + 1;
                while value.rows.len() < WORKER_PASSAGE_LIMIT {
                    let p = engine.snapshot.passages[0].clone();
                    value.rows.push(BatchRow {
                        vector: p.vector.clone(),
                        passage: p,
                    });
                }
                Ok(value)
            },
        );
        assert!(result.is_err());
        assert_eq!(offsets, [0, WORKER_PASSAGE_LIMIT]);
        assert!(!database.exists());
    }

    #[test]
    fn changing_model_or_total_between_sequential_batches_is_rejected_before_publication() {
        let engine = super::super::tests::fixture();
        for change_total in [false, true] {
            let directory = tempfile::tempdir().unwrap();
            let database = directory.path().join("existing.sqlite");
            publish(&database, &engine.snapshot).unwrap();
            let before = std::fs::read(&database).unwrap();
            let mut offsets = Vec::new();
            let result = import_with_worker(
                engine.snapshot.cases.clone(),
                &database,
                4,
                &corpus::hash(b"1\n2\n3\n4"),
                |offset| {
                    offsets.push(offset);
                    let mut value = batch(&engine, 0);
                    value.offset = offset;
                    value.total = WORKER_PASSAGE_LIMIT + 1;
                    value.rows.clear();
                    if offset == WORKER_PASSAGE_LIMIT {
                        if change_total {
                            value.total += 1;
                        } else {
                            value.embedding.sdk = "changed model configuration".into();
                        }
                    }
                    let row_count = WORKER_PASSAGE_LIMIT.min(value.total - offset);
                    for _ in 0..row_count {
                        let passage = engine.snapshot.passages[0].clone();
                        value.rows.push(BatchRow {
                            vector: passage.vector.clone(),
                            passage,
                        });
                    }
                    Ok(value)
                },
            );
            assert_eq!(offsets, [0, WORKER_PASSAGE_LIMIT]);
            assert_eq!(
                result.unwrap_err().message,
                "Import batch offset, size, source or model configuration changed."
            );
            assert_eq!(std::fs::read(&database).unwrap(), before);
        }
    }

    #[test]
    fn malformed_or_changed_batches_and_invalid_vectors_are_rejected() {
        let engine = super::super::tests::fixture();
        for mutation in 0..5 {
            let result = collect_batches(
                engine.snapshot.cases.clone(),
                4,
                &corpus::hash(b"1\n2\n3\n4"),
                |offset| {
                    let mut value = batch(&engine, offset);
                    match mutation {
                        0 => value.offset += 1,
                        1 => {
                            value.rows.pop();
                        }
                        2 => value.source_sha256 = "changed".into(),
                        3 => value.rows[0].vector = vec![f32::NAN, 0.],
                        _ => value.rows[0].passage.passage.text_version = Some("wrong".into()),
                    }
                    Ok(value)
                },
            );
            assert!(result.is_err());
        }
    }
}
