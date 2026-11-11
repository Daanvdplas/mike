use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CaseMetadata {
    pub case_id: String,
    pub title: String,
    pub court: String,
    pub decision_date: String,
    pub citation: String,
    pub text_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Passage {
    pub passage_id: String,
    pub text: String,
    pub start_utf16: usize,
    pub end_utf16: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SearchResult {
    #[serde(flatten)]
    pub metadata: CaseMetadata,
    pub score: f64,
    pub passage: Passage,
    pub case_url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SearchResponse {
    pub mode: String,
    pub corpus_version: String,
    pub ranking_version: String,
    pub results: Vec<SearchResult>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CaseDetail {
    #[serde(flatten)]
    pub metadata: CaseMetadata,
    pub corpus_version: String,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HealthResponse {
    pub status: String,
    pub corpus_version: String,
    pub indexed_case_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImportReport {
    pub corpus_version: String,
    pub case_count: usize,
    pub passage_count: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    InvalidInput,
    IndexUnavailable,
    Internal,
    CaseNotFound,
}

#[derive(Debug, Clone)]
pub struct EngineError {
    pub kind: ErrorKind,
    pub message: String,
}

impl EngineError {
    pub(crate) fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
        }
    }
}

impl std::fmt::Display for EngineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for EngineError {}
