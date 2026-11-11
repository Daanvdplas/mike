use crate::{
    api_error::ApiError,
    engine::{CaseDetail, EngineError, ErrorKind, HealthResponse, SearchResponse},
    extraction::{MAX_DOCUMENT_BYTES, extract_document},
};
use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, Multipart, Path, State, multipart::MultipartRejection},
    http::{HeaderValue, Method, StatusCode, header},
    routing::{get, post},
};
use std::sync::{Arc, Mutex};
use tower_http::cors::{AllowOrigin, CorsLayer};

/// Only the search/index boundary is replaceable; HTTP and extraction stay real.
pub trait Backend: Send {
    fn search(
        &mut self,
        query: Option<&str>,
        document: Option<&str>,
    ) -> Result<SearchResponse, EngineError>;
    fn get_case(&self, case_id: &str) -> Result<CaseDetail, EngineError>;
    fn health(&self) -> HealthResponse;
}

#[derive(Clone)]
pub struct ApiState(Arc<Mutex<Option<Box<dyn Backend>>>>);

impl ApiState {
    pub fn new(backend: Option<Box<dyn Backend>>) -> Self {
        Self(Arc::new(Mutex::new(backend)))
    }
}

pub fn router(state: ApiState, origins: Vec<HeaderValue>) -> Router {
    let contract: serde_json::Value =
        serde_yaml_ng::from_str(include_str!("../../docs/openapi.yaml"))
            .expect("canonical OpenAPI must be valid YAML");
    Router::new()
        .route("/api/search", post(search))
        .route("/api/cases/{case_id}", get(get_case))
        .route("/api/health", get(health))
        .route("/openapi.json", get(move || async move { Json(contract) }))
        // Enforce the file limit on its bytes, not on multipart headers/query.
        .layer(DefaultBodyLimit::disable())
        .layer(
            CorsLayer::new()
                .allow_origin(AllowOrigin::list(origins))
                .allow_methods([Method::GET, Method::POST])
                .allow_headers([header::CONTENT_TYPE]),
        )
        .with_state(state)
}

async fn search(
    State(state): State<ApiState>,
    multipart: Result<Multipart, MultipartRejection>,
) -> Result<Json<SearchResponse>, ApiError> {
    let mut multipart = multipart.map_err(|_| invalid_input())?;
    let mut query = None;
    let mut query_seen = false;
    let mut document = None;
    while let Some(mut field) = multipart.next_field().await.map_err(|_| invalid_input())? {
        match field.name() {
            Some("query") if !query_seen => {
                query_seen = true;
                if field.file_name().is_some() {
                    return Err(invalid_input());
                }
                let bytes = field.bytes().await.map_err(|_| invalid_input())?;
                let text = std::str::from_utf8(&bytes)
                    .map_err(|_| invalid_input())?
                    .trim();
                if !text.is_empty() {
                    query = Some(text.to_owned());
                }
            }
            Some("document") if document.is_none() => {
                let filename = field
                    .file_name()
                    .ok_or_else(|| {
                        ApiError::new(
                            StatusCode::UNSUPPORTED_MEDIA_TYPE,
                            "unsupported_document",
                            "Upload a PDF or TXT document.",
                        )
                    })?
                    .to_owned();
                let mut bytes = Vec::new();
                while let Some(chunk) = field.chunk().await.map_err(|_| invalid_input())? {
                    if chunk.len() > MAX_DOCUMENT_BYTES - bytes.len() {
                        return Err(ApiError::new(
                            StatusCode::PAYLOAD_TOO_LARGE,
                            "document_too_large",
                            "The document must not exceed 10 MiB.",
                        ));
                    }
                    bytes.extend_from_slice(&chunk);
                }
                document = Some((filename, bytes));
            }
            _ => return Err(invalid_input()),
        }
    }
    if query.is_none() && document.is_none() {
        return Err(invalid_input());
    }
    let document = match document {
        Some((filename, bytes)) => Some(
            tokio::task::spawn_blocking(move || extract_document(&filename, &bytes))
                .await
                .map_err(|_| internal_error())??,
        ),
        None => None,
    };
    with_backend(state, move |backend| {
        backend.search(query.as_deref(), document.as_deref())
    })
    .await
    .map(Json)
}

async fn get_case(
    State(state): State<ApiState>,
    Path(case_id): Path<String>,
) -> Result<Json<CaseDetail>, ApiError> {
    with_backend(state, move |backend| backend.get_case(&case_id))
        .await
        .map(Json)
}

async fn health(State(state): State<ApiState>) -> Result<Json<HealthResponse>, ApiError> {
    with_backend(state, |backend| Ok(backend.health()))
        .await
        .map(Json)
}

async fn with_backend<T, F>(state: ApiState, work: F) -> Result<T, ApiError>
where
    T: Send + 'static,
    F: FnOnce(&mut dyn Backend) -> Result<T, EngineError> + Send + 'static,
{
    tokio::task::spawn_blocking(move || {
        let mut locked = state.0.lock().map_err(|_| internal_error())?;
        let backend = locked
            .as_mut()
            .ok_or_else(|| EngineError::new(ErrorKind::IndexUnavailable, "Index unavailable."))?;
        work(backend.as_mut()).map_err(ApiError::from)
    })
    .await
    .map_err(|_| internal_error())?
}

fn invalid_input() -> ApiError {
    ApiError::new(
        StatusCode::BAD_REQUEST,
        "invalid_input",
        "Supply a PDF/TXT document, a query, or both; multipart fields must be valid and unique.",
    )
}
fn index_unavailable() -> ApiError {
    ApiError::new(
        StatusCode::SERVICE_UNAVAILABLE,
        "index_unavailable",
        "The complete search index is not ready. Try again later.",
    )
}
fn internal_error() -> ApiError {
    ApiError::new(
        StatusCode::INTERNAL_SERVER_ERROR,
        "internal_error",
        "The request could not be completed.",
    )
}

impl From<EngineError> for ApiError {
    fn from(error: EngineError) -> Self {
        match error.kind {
            ErrorKind::InvalidInput => ApiError::new(
                StatusCode::BAD_REQUEST,
                "invalid_input",
                "The input could not produce a usable search vector.",
            ),
            ErrorKind::IndexUnavailable => index_unavailable(),
            ErrorKind::Internal => internal_error(),
            ErrorKind::CaseNotFound => {
                ApiError::new(StatusCode::NOT_FOUND, "case_not_found", "Case not found.")
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::ErrorKind;
    use axum::{
        body::{Body, to_bytes},
        http::{Request, StatusCode},
    };
    use serde_json::{Value, json};
    use tower::ServiceExt;

    type Captured = Arc<Mutex<Vec<(Option<String>, Option<String>)>>>;

    struct FixtureBackend {
        captured: Captured,
    }
    impl Backend for FixtureBackend {
        fn search(
            &mut self,
            query: Option<&str>,
            document: Option<&str>,
        ) -> Result<SearchResponse, EngineError> {
            self.captured
                .lock()
                .unwrap()
                .push((query.map(str::to_owned), document.map(str::to_owned)));
            let mut response: SearchResponse =
                serde_json::from_str(include_str!("../../docs/examples/search-response.json"))
                    .unwrap();
            response.mode = match (query, document) {
                (Some(_), Some(_)) => "combined",
                (Some(_), None) => "query",
                _ => "document",
            }
            .into();
            Ok(response)
        }
        fn get_case(&self, id: &str) -> Result<CaseDetail, EngineError> {
            let cases: Vec<CaseDetail> =
                serde_json::from_str(include_str!("../../docs/examples/cases.json")).unwrap();
            cases
                .into_iter()
                .find(|c| c.metadata.case_id == id)
                .ok_or(EngineError {
                    kind: ErrorKind::CaseNotFound,
                    message: "internal lookup context".into(),
                })
        }
        fn health(&self) -> HealthResponse {
            HealthResponse {
                status: "ready".into(),
                corpus_version: "fixture-corpus-v1".into(),
                indexed_case_count: 135,
            }
        }
    }

    fn fixture_app() -> (Router, Captured) {
        let captured = Arc::new(Mutex::new(vec![]));
        let state = ApiState::new(Some(Box::new(FixtureBackend {
            captured: captured.clone(),
        })));
        (
            router(state, vec!["http://localhost:5173".parse().unwrap()]),
            captured,
        )
    }

    fn multipart(parts: &[(&str, Option<&str>, &[u8])]) -> Request<Body> {
        let mut body = Vec::new();
        for (name, filename, bytes) in parts {
            body.extend_from_slice(
                format!("--test-boundary\r\nContent-Disposition: form-data; name=\"{name}\"")
                    .as_bytes(),
            );
            if let Some(filename) = filename {
                body.extend_from_slice(format!("; filename=\"{filename}\"").as_bytes());
            }
            body.extend_from_slice(b"\r\n\r\n");
            body.extend_from_slice(bytes);
            body.extend_from_slice(b"\r\n");
        }
        body.extend_from_slice(b"--test-boundary--\r\n");
        Request::post("/api/search")
            .header(
                "content-type",
                "multipart/form-data; boundary=test-boundary",
            )
            .body(Body::from(body))
            .unwrap()
    }

    async fn response_json(app: Router, request: Request<Body>) -> (StatusCode, Value) {
        let response = app.oneshot(request).await.unwrap();
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 16 * 1024 * 1024)
            .await
            .unwrap();
        let value = serde_json::from_slice(&bytes)
            .unwrap_or_else(|_| json!({"not_json":String::from_utf8_lossy(&bytes)}));
        (status, value)
    }

    #[tokio::test]
    async fn search_accepts_a_trimmed_query_without_a_document_or_coa_length_limit() {
        let (app, captured) = fixture_app();
        let query = format!("  {}  ", "witness ".repeat(200));
        let (status, body) =
            response_json(app, multipart(&[("query", None, query.as_bytes())])).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        assert_eq!(body["results"].as_array().unwrap().len(), 3);
        assert_eq!(
            captured.lock().unwrap()[0],
            (Some(query.trim().into()), None)
        );
    }

    #[tokio::test]
    async fn document_only_accepts_txt_and_blank_query_is_absent() {
        let (app, captured) = fixture_app();
        let text = "Witness 🧪 testimony\nSecond paragraph.";
        let (status, body) = response_json(
            app,
            multipart(&[
                ("document", Some("case.txt"), text.as_bytes()),
                ("query", None, b"  \n "),
            ]),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        assert_eq!(captured.lock().unwrap()[0], (None, Some(text.into())));
    }

    #[tokio::test]
    async fn combined_pdf_upload_extracts_text_before_search() {
        let (app, captured) = fixture_app();
        let pdf = crate::extraction::tests::text_pdf(Some("Evidence about a witness."));
        let (status, body) = response_json(
            app,
            multipart(&[
                ("document", Some("case.pdf"), &pdf),
                ("query", None, b"witness"),
            ]),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let captured = captured.lock().unwrap();
        assert_eq!(captured[0].0.as_deref(), Some("witness"));
        assert!(
            captured[0]
                .1
                .as_ref()
                .unwrap()
                .contains("Evidence about a witness.")
        );
        assert!(!captured[0].1.as_ref().unwrap().contains("%PDF"));
    }

    #[tokio::test]
    async fn invalid_document_is_not_ignored_when_query_is_valid() {
        let (app, captured) = fixture_app();
        let (status, body) = response_json(
            app,
            multipart(&[
                ("query", None, b"witness"),
                ("document", Some("empty.txt"), b" \n"),
            ]),
        )
        .await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(body["error"]["code"], "unreadable_document");
        assert!(captured.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn no_input_unknown_fields_duplicates_and_malformed_multipart_are_errors() {
        let cases = vec![
            multipart(&[]),
            multipart(&[("query", None, b"  ")]),
            multipart(&[("unknown", None, b"x")]),
            multipart(&[("query", None, b"x"), ("query", None, b"y")]),
            Request::post("/api/search")
                .header("content-type", "multipart/form-data")
                .body(Body::from("broken"))
                .unwrap(),
        ];
        for request in cases {
            let (app, _) = fixture_app();
            let (status, body) = response_json(app, request).await;
            assert_eq!(status, StatusCode::BAD_REQUEST, "{body}");
            assert_eq!(body["error"]["code"], "invalid_input");
        }
    }

    #[tokio::test]
    async fn ten_mib_file_is_allowed_despite_multipart_overhead_but_one_more_byte_is_not() {
        let bytes = vec![b'a'; crate::extraction::MAX_DOCUMENT_BYTES];
        let (app, _) = fixture_app();
        let (status, body) =
            response_json(app, multipart(&[("document", Some("limit.txt"), &bytes)])).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let bytes = vec![b'a'; crate::extraction::MAX_DOCUMENT_BYTES + 1];
        let (app, _) = fixture_app();
        let (status, body) =
            response_json(app, multipart(&[("document", Some("large.txt"), &bytes)])).await;
        assert_eq!(status, StatusCode::PAYLOAD_TOO_LARGE);
        assert_eq!(body["error"]["code"], "document_too_large");
    }

    #[tokio::test]
    async fn unloaded_index_returns_503_instead_of_fake_results() {
        for (method, path) in [("GET", "/api/health"), ("GET", "/api/cases/missing")] {
            let app = router(ApiState::new(None), vec![]);
            let (status, body) = response_json(
                app,
                Request::builder()
                    .method(method)
                    .uri(path)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await;
            assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
            assert_eq!(body["error"]["code"], "index_unavailable");
        }
        let (status, body) = response_json(
            router(ApiState::new(None), vec![]),
            multipart(&[("query", None, b"witness")]),
        )
        .await;
        assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(body["error"]["code"], "index_unavailable");
    }

    #[tokio::test]
    async fn detail_and_health_return_contract_fields_and_unknown_case_returns_404() {
        let (app, _) = fixture_app();
        let (status, health) = response_json(
            app.clone(),
            Request::get("/api/health").body(Body::empty()).unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(health["indexed_case_count"], 135);
        let (status, detail) = response_json(
            app.clone(),
            Request::get("/api/cases/fixture-case-001")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert!(detail["text"].as_str().unwrap().contains('🧪'));
        assert!(
            detail["text_version"]
                .as_str()
                .unwrap()
                .starts_with("sha256:")
        );
        let (status, error) = response_json(
            app,
            Request::get("/api/cases/unknown")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::NOT_FOUND);
        assert_eq!(error["error"]["code"], "case_not_found");
        assert!(!error.to_string().contains("internal lookup"));
    }

    #[tokio::test]
    async fn openapi_is_available_without_loading_a_model() {
        let (status, body) = response_json(
            router(ApiState::new(None), vec![]),
            Request::get("/openapi.json").body(Body::empty()).unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["openapi"], "3.0.3");
        assert!(body["paths"]["/api/search"]["post"].is_object());
    }

    #[tokio::test]
    async fn cors_preflight_allows_only_configured_origins() {
        let (app, _) = fixture_app();
        for (origin, allowed) in [
            ("http://localhost:5173", true),
            ("https://unconfigured.example", false),
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method("OPTIONS")
                        .uri("/api/search")
                        .header("origin", origin)
                        .header("access-control-request-method", "POST")
                        .header("access-control-request-headers", "content-type")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(
                response
                    .headers()
                    .get("access-control-allow-origin")
                    .is_some(),
                allowed
            );
        }
    }
}
