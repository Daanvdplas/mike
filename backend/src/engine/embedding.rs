//! Cache/session/thread setup reuses COA's tested local fastembed path:
//! https://github.com/Daanvdplas/meedoenbalie-rag-learning/blob/cada34fbb4d22bde46d31c3cdbcda495e6d93e9b/src/lib.rs#L100
//! English retrieval model, CLS pooling and query instruction follow:
//! https://huggingface.co/BAAI/bge-small-en-v1.5
use super::{EngineError, ErrorKind, chunk::TOKEN_BUDGET, ranking::cosine};
use serde::{Deserialize, Serialize};
use std::{io::Read, path::Path, sync::OnceLock};

static ENVIRONMENT: OnceLock<Result<ort::environment::Environment, String>> = OnceLock::new();

pub(super) const MODEL: &str = "Xenova/bge-small-en-v1.5";
const QUERY_PREFIX: &str = "Represent this sentence for searching relevant passages: ";
const INFERENCE_BATCH_SIZE: usize = 1;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct EmbeddingConfig {
    pub model: String,
    pub dimensions: usize,
    pub max_tokens: usize,
    pub sdk: String,
    pub pooling: String,
    pub query_prefix: String,
    pub artifacts_sha256: String,
}

pub(super) trait Embedder: Send {
    fn config(&self) -> &EmbeddingConfig;
    fn token_count(&self, text: &str) -> Result<usize, EngineError>;
    fn embed(&mut self, texts: &[String]) -> Result<Vec<Vec<f32>>, EngineError>;
}

pub(super) struct LocalEmbeddings {
    model: fastembed::TextEmbedding,
    config: EmbeddingConfig,
}

impl LocalEmbeddings {
    pub(super) fn new(cache: &Path) -> Result<Self, EngineError> {
        eprintln!(
            "Initializing local model {MODEL} (batch <= {INFERENCE_BATCH_SIZE}, threads = 2, CPU arena = off)"
        );
        let environment = ENVIRONMENT
            .get_or_init(|| {
                ort::init()
                    .with_name("adami-case")
                    .build()
                    .map_err(|e| e.to_string())
            })
            .as_ref()
            .map_err(|_| unavailable())?
            .clone();
        let mut model = fastembed::TextEmbedding::try_new(
            fastembed::TextInitOptions::new(fastembed::EmbeddingModel::BGESmallENV15)
                .with_environment(environment)
                // Explicit CPU policy: release variable-shape working allocations.
                .with_execution_providers(vec![
                    ort::ep::CPU::default()
                        .with_arena_allocator(false)
                        .build()
                        .error_on_failure(),
                ])
                .with_cache_dir(cache.to_owned())
                .with_show_download_progress(true)
                .with_max_length(512)
                .with_intra_threads(2),
        )
        .map_err(|error| {
            eprintln!("Local embedding model initialization failed: {error}");
            unavailable()
        })?;
        // Count the full input. The caller splits it before embedding, never truncates.
        model
            .tokenizer
            .with_truncation(None)
            .map_err(|_| unavailable())?;
        let config = EmbeddingConfig {
            model: MODEL.into(),
            dimensions: 384,
            max_tokens: 512,
            sdk: "fastembed 7.1.2; intra_threads=2".into(),
            pooling: "Cls".into(),
            query_prefix: QUERY_PREFIX.into(),
            artifacts_sha256: artifacts_fingerprint(cache, "onnx/model.onnx")?,
        };
        eprintln!("Local embedding model ready");
        Ok(Self { model, config })
    }
}

impl Embedder for LocalEmbeddings {
    fn config(&self) -> &EmbeddingConfig {
        &self.config
    }
    fn token_count(&self, text: &str) -> Result<usize, EngineError> {
        self.model
            .tokenizer
            .encode(text, true)
            .map(|encoding| encoding.len())
            .map_err(|_| {
                EngineError::new(ErrorKind::InvalidInput, "Cannot tokenize the input text.")
            })
    }
    fn embed(&mut self, texts: &[String]) -> Result<Vec<Vec<f32>>, EngineError> {
        for text in texts {
            if self.token_count(text)? > TOKEN_BUDGET {
                return Err(EngineError::new(
                    ErrorKind::InvalidInput,
                    "Text must be split before embedding.",
                ));
            }
        }
        let dimensions = self.config.dimensions;
        embed_in_batches(texts, |batch| {
            // Each call exports normalized rows before the next native batch starts.
            // A single all-corpus call retains every raw ONNX batch until export.
            let vectors = self
                .model
                .embed(batch, Some(INFERENCE_BATCH_SIZE))
                .map_err(|_| unavailable())?;
            for vector in &vectors {
                if vector.len() != dimensions {
                    return Err(unavailable());
                }
                cosine(vector, vector).map_err(|_| unavailable())?;
            }
            Ok(vectors)
        })
    }
}

fn unavailable() -> EngineError {
    EngineError::new(
        ErrorKind::IndexUnavailable,
        "The local embedding model or its cached files are unavailable.",
    )
}

fn embed_in_batches(
    texts: &[String],
    mut infer: impl FnMut(&[String]) -> Result<Vec<Vec<f32>>, EngineError>,
) -> Result<Vec<Vec<f32>>, EngineError> {
    let mut vectors = Vec::with_capacity(texts.len());
    for batch in texts.chunks(INFERENCE_BATCH_SIZE) {
        let rows = infer(batch)?;
        if rows.len() != batch.len() {
            return Err(unavailable());
        }
        vectors.extend(rows);
        if texts.len() > INFERENCE_BATCH_SIZE {
            eprintln!("Embedded {}/{} texts", vectors.len(), texts.len());
        }
    }
    Ok(vectors)
}

fn artifacts_fingerprint(cache: &Path, model_file: &str) -> Result<String, EngineError> {
    use sha2::{Digest, Sha256};
    let root = cache.join(format!("models--{}", MODEL.replace('/', "--")));
    let revision = std::fs::read_to_string(root.join("refs/main")).map_err(|_| unavailable())?;
    let snapshot = root.join("snapshots").join(revision.trim());
    let mut digest = Sha256::new();
    digest.update(revision.as_bytes());
    for name in [
        model_file,
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "config.json",
    ] {
        digest.update(name.as_bytes());
        let mut file = std::fs::File::open(snapshot.join(name)).map_err(|_| unavailable())?;
        digest.update(
            file.metadata()
                .map_err(|_| unavailable())?
                .len()
                .to_le_bytes(),
        );
        let mut buffer = [0_u8; 65536];
        loop {
            let read = file.read(&mut buffer).map_err(|_| unavailable())?;
            if read == 0 {
                break;
            }
            digest.update(&buffer[..read]);
        }
    }
    Ok(format!("{:x}", digest.finalize()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_inference_is_bounded_and_all_rows_keep_their_input_order() {
        let texts: Vec<_> = (0..11).map(|i| i.to_string()).collect();
        let mut sizes = Vec::new();
        let vectors = embed_in_batches(&texts, |batch| {
            assert!(batch.len() <= 1);
            sizes.push(batch.len());
            Ok(batch
                .iter()
                .map(|text| vec![text.parse::<f32>().unwrap()])
                .collect())
        })
        .unwrap();
        assert_eq!(sizes, [1; 11]);
        assert_eq!(vectors, (0..11).map(|i| vec![i as f32]).collect::<Vec<_>>());
    }

    #[test]
    fn native_inference_rejects_missing_rows_in_any_batch() {
        let texts = vec!["text".to_owned(); 5];
        assert!(embed_in_batches(&texts, |_| Ok(Vec::new())).is_err());
    }

    #[test]
    #[ignore = "resource gate: run this one model job under scripts/resource_guard.py"]
    fn bounded_model_smoke_reuses_one_session_for_repeated_near_limit_batches() {
        let cache = std::env::var_os("ADAMI_MODEL_CACHE").expect("Set ADAMI_MODEL_CACHE");
        let mut model = LocalEmbeddings::new(Path::new(&cache)).unwrap();
        let texts: Vec<_> = [8, 460, 60, 420, 180, 470, 300, 25]
            .into_iter()
            .enumerate()
            .map(|(i, length)| format!("Trial {i}. {}", "witness ".repeat(length)))
            .collect();
        let counts: Vec<_> = texts
            .iter()
            .map(|text| model.token_count(text).unwrap())
            .collect();
        eprintln!("Resource smoke token lengths: {counts:?}");
        assert!(counts.iter().all(|count| *count <= TOKEN_BUDGET));
        assert!(*counts.iter().min().unwrap() < 50);
        assert!(*counts.iter().max().unwrap() >= 450);
        let first = model.embed(&texts).unwrap();
        for repeat in 1..=3 {
            eprintln!("Resource smoke repetition {repeat}/3");
            let repeated = model.embed(&texts).unwrap();
            assert_eq!(repeated.len(), texts.len());
            for (a, b) in first.iter().zip(&repeated) {
                assert!(cosine(a, b).unwrap() > 0.9999);
            }
        }
    }

    #[test]
    #[ignore = "requires the local embedding model; set ADAMI_MODEL_CACHE explicitly"]
    fn real_model_counts_untruncated_tokens_and_preserves_embedding_dimensions() {
        let cache = std::env::var_os("ADAMI_MODEL_CACHE")
            .expect("Set ADAMI_MODEL_CACHE outside the repository");
        let mut model = LocalEmbeddings::new(Path::new(&cache)).unwrap();
        assert_eq!(model.config().dimensions, 384);
        assert_eq!(model.config().artifacts_sha256.len(), 64);
        let long = "witness testimony ".repeat(800);
        assert!(model.token_count(&long).unwrap() > 512);
        assert!(model.embed(&[long]).is_err());
        let vectors = model
            .embed(&["A witness testified at trial.".into()])
            .unwrap();
        assert_eq!(vectors.len(), 1);
        assert_eq!(vectors[0].len(), 384);
        assert!(vectors[0].iter().all(|v| v.is_finite()));
    }

    #[test]
    #[ignore = "requires the local model; regression for import followed by reload"]
    fn real_model_can_be_recreated_after_previous_session_is_dropped() {
        let cache = std::env::var_os("ADAMI_MODEL_CACHE").expect("Set ADAMI_MODEL_CACHE");
        let first_signature;
        {
            let model = LocalEmbeddings::new(Path::new(&cache)).unwrap();
            first_signature = model.config().clone();
        }
        let mut second = LocalEmbeddings::new(Path::new(&cache)).unwrap();
        assert_eq!(second.config(), &first_signature);
        assert_eq!(second.embed(&["trial evidence".into()]).unwrap().len(), 1);
    }

    #[test]
    #[ignore = "diagnostic/regression: requires ADAMI_DATABASE and local model cache"]
    fn persisted_passage_embeddings_agree_with_single_and_original_batch_contexts() {
        use crate::engine::{ranking::cosine, storage};
        let cache = std::env::var_os("ADAMI_MODEL_CACHE").expect("Set ADAMI_MODEL_CACHE");
        let database = std::env::var_os("ADAMI_DATABASE").expect("Set ADAMI_DATABASE");
        let snapshot = storage::load(
            Path::new(&database),
            storage::EXPECTED_COUNT,
            storage::EXPECTED_IDS_SHA256,
        )
        .unwrap();
        let mut model = LocalEmbeddings::new(Path::new(&cache)).unwrap();
        assert_eq!(model.config(), &snapshot.manifest.embedding);
        let starts = [
            0,
            (snapshot.passages.len() / 2 / 16) * 16,
            (snapshot.passages.len() - 1) / 16 * 16,
        ];
        let mut min_stored_batch = 1.0_f32;
        let mut min_single_batch = 1.0_f32;
        for start in starts {
            let end = (start + 16).min(snapshot.passages.len());
            let items = &snapshot.passages[start..end];
            let texts: Vec<_> = items.iter().map(|p| p.passage.text.clone()).collect();
            let batch = model.embed(&texts).unwrap();
            for (offset, item) in items.iter().enumerate() {
                let single = model.embed(&[texts[offset].clone()]).unwrap();
                let stored_batch = cosine(&item.vector, &batch[offset]).unwrap();
                let single_batch = cosine(&single[0], &batch[offset]).unwrap();
                min_stored_batch = min_stored_batch.min(stored_batch);
                min_single_batch = min_single_batch.min(single_batch);
                eprintln!(
                    "{} chars={} tokens={} stored_vs_batch={stored_batch:.7} single_vs_batch={single_batch:.7}",
                    item.passage.passage_id,
                    texts[offset].chars().count(),
                    model.token_count(&texts[offset]).unwrap()
                );
            }
        }
        eprintln!(
            "minimum stored/batch={min_stored_batch:.7}; minimum single/batch={min_single_batch:.7}"
        );
        assert!(
            min_stored_batch > 0.999,
            "Persisted vectors differ from the same batch computation"
        );
        assert!(
            min_single_batch > 0.999,
            "The same text changes meaning with its batch companions"
        );
    }

    #[test]
    #[ignore = "diagnostic: exact self-match and separate simple semantic controls, no gold questions"]
    fn exact_passages_self_match_and_distinct_topics_are_separated() {
        use crate::engine::{Engine, ranking::cosine, storage};
        let cache = std::env::var_os("ADAMI_MODEL_CACHE").expect("Set ADAMI_MODEL_CACHE");
        let database = std::env::var_os("ADAMI_DATABASE").expect("Set ADAMI_DATABASE");
        let snapshot = storage::load(
            Path::new(&database),
            storage::EXPECTED_COUNT,
            storage::EXPECTED_IDS_SHA256,
        )
        .unwrap();
        let mut model = LocalEmbeddings::new(Path::new(&cache)).unwrap();
        let documents = [
            "The gardener waters plants and grows vegetables.",
            "A mechanic repairs a car engine in the workshop.",
            "The judge excluded an out-of-court witness statement as hearsay.",
        ]
        .map(str::to_owned);
        let questions = [
            "How can I irrigate my vegetable garden?",
            "Fixing a broken motor vehicle.",
            "A trial ruling on inadmissible hearsay testimony.",
        ]
        .map(str::to_owned);
        let document_vectors = model.embed(&documents).unwrap();
        let query_inputs = questions.map(|q| format!("{QUERY_PREFIX}{q}"));
        let query_vectors = model.embed(&query_inputs).unwrap();
        for (expected, query) in query_vectors.iter().enumerate() {
            let scores: Vec<_> = document_vectors
                .iter()
                .map(|v| cosine(query, v).unwrap())
                .collect();
            let best = scores
                .iter()
                .enumerate()
                .max_by(|a, b| a.1.total_cmp(b.1))
                .unwrap()
                .0;
            eprintln!("simple topic {expected}: best={best} scores={scores:?}");
            assert_eq!(best, expected);
        }
        let samples: Vec<_> = [0, snapshot.passages.len() / 2, snapshot.passages.len() - 1]
            .into_iter()
            .map(|i| {
                (
                    snapshot.passages[i].case_id.clone(),
                    snapshot.passages[i].passage.text.clone(),
                )
            })
            .collect();
        let mut engine = Engine {
            snapshot,
            embedder: Box::new(model),
        };
        for (expected, text) in samples {
            let response = engine.search(None, Some(&text)).unwrap();
            eprintln!(
                "self-match expected={expected} actual={:?}",
                response
                    .results
                    .iter()
                    .map(|r| (&r.metadata.case_id, r.score))
                    .collect::<Vec<_>>()
            );
            assert_eq!(response.results[0].metadata.case_id, expected);
            assert!(response.results[0].score > 0.999);
        }
    }
}
