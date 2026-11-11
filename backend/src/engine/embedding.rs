//! Model setup follows COA's tested local fastembed path (same model/options):
//! https://github.com/Daanvdplas/meedoenbalie-rag-learning/blob/cada34fbb4d22bde46d31c3cdbcda495e6d93e9b/src/lib.rs#L100
use super::{EngineError, ErrorKind, chunk::TOKEN_BUDGET, ranking::cosine};
use serde::{Deserialize, Serialize};
use std::{io::Read, path::Path, sync::OnceLock};

static ENVIRONMENT: OnceLock<Result<ort::environment::Environment, String>> = OnceLock::new();

pub(super) const MODEL: &str = "Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(super) struct EmbeddingConfig {
    pub model: String,
    pub dimensions: usize,
    pub max_tokens: usize,
    pub sdk: String,
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
            fastembed::TextInitOptions::new(fastembed::EmbeddingModel::ParaphraseMLMiniLML12V2Q)
                .with_environment(environment)
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
            sdk: "fastembed 7.1.2; mean pooling; unprefixed; intra_threads=2".into(),
            artifacts_sha256: artifacts_fingerprint(cache)?,
        };
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
        let vectors = self
            .model
            .embed(texts, Some(16))
            .map_err(|_| unavailable())?;
        if vectors.len() != texts.len() || vectors.iter().any(|v| v.len() != self.config.dimensions)
        {
            return Err(unavailable());
        }
        for vector in &vectors {
            cosine(vector, vector).map_err(|_| unavailable())?;
        }
        Ok(vectors)
    }
}

fn unavailable() -> EngineError {
    EngineError::new(
        ErrorKind::IndexUnavailable,
        "The local embedding model or its cached files are unavailable.",
    )
}

fn artifacts_fingerprint(cache: &Path) -> Result<String, EngineError> {
    use sha2::{Digest, Sha256};
    let root = cache.join(format!("models--{}", MODEL.replace('/', "--")));
    let revision = std::fs::read_to_string(root.join("refs/main")).map_err(|_| unavailable())?;
    let snapshot = root.join("snapshots").join(revision.trim());
    let mut digest = Sha256::new();
    digest.update(revision.as_bytes());
    for name in [
        "model_optimized.onnx",
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
}
