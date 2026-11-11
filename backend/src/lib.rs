//! Rust backend for the Texas Legal Document Similarity Finder.
//!
//! The foundation supplies the dependency graph and build checks. Corpus,
//! ranking, extraction and HTTP modules are implemented in follow-up issues.
pub mod api;
pub mod api_error;
pub mod engine;
pub mod extraction;
