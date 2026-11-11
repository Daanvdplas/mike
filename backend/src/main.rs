use texas_case_finder::{
    api::{self, ApiState, Backend},
    engine::{self, Engine},
    service::{Command, Settings},
};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let command = Command::parse(&std::env::args().skip(1).collect::<Vec<_>>())?;
    let settings = Settings::from_env()?;
    match command {
        Command::Import(corpus) => {
            let report = tokio::task::spawn_blocking(move || {
                engine::import_corpus(&corpus, &settings.database, &settings.cache)
            })
            .await??;
            println!("{}", serde_json::to_string(&report)?);
        }
        Command::Search(query) => {
            let response = tokio::task::spawn_blocking(move || {
                let mut engine = Engine::load(&settings.database, &settings.cache)?;
                engine.search(Some(&query), None)
            })
            .await??;
            println!("{}", serde_json::to_string(&response)?);
        }
        Command::SearchExcluding { query, case_id } => {
            let response = tokio::task::spawn_blocking(move || {
                let mut engine = Engine::load(&settings.database, &settings.cache)?;
                let response =
                    engine.search_excluding(Some(&query), None, std::slice::from_ref(&case_id))?;
                Ok::<_, engine::EngineError>(serde_json::json!({
                    "response": response,
                    "excluded_case_ids": [case_id],
                    "eligible_case_count": engine.health().indexed_case_count - 1,
                }))
            })
            .await??;
            println!("{}", serde_json::to_string(&response)?);
        }
        Command::Serve => {
            let database = settings.database.clone();
            let cache = settings.cache.clone();
            let loaded =
                tokio::task::spawn_blocking(move || Engine::load(&database, &cache)).await?;
            let backend = match loaded {
                Ok(engine) => Some(Box::new(engine) as Box<dyn Backend>),
                Err(error) => {
                    eprintln!(
                        "Search index unavailable ({:?}); import the corpus and restart.",
                        error.kind
                    );
                    None
                }
            };
            let listener = tokio::net::TcpListener::bind(settings.bind).await?;
            eprintln!("Backend listening on http://{}", listener.local_addr()?);
            axum::serve(
                listener,
                api::router(ApiState::new(backend), settings.cors_origins),
            )
            .with_graceful_shutdown(async {
                let _ = tokio::signal::ctrl_c().await;
            })
            .await?;
        }
    }
    Ok(())
}
