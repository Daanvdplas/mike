use texas_case_finder::{
    api::{self, ApiState, Backend},
    engine::{self, Engine, evaluation},
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
        Command::Evaluate(options) => {
            if options.output.exists() {
                return Err(
                    "Evaluation output directory already exists; choose a new run directory."
                        .into(),
                );
            }
            let plan = evaluation::EvaluationPlan::load(
                &options.scenarios,
                &options.corpus,
                &options.scenario_ids,
            )?;
            let labels = options
                .labels
                .as_ref()
                .map(
                    |path| -> Result<
                        texas_case_finder::eval_metrics::LabelSet,
                        Box<dyn std::error::Error>,
                    > { Ok(serde_json::from_slice(&std::fs::read(path)?)?) },
                )
                .transpose()?;
            let mut engine = Engine::load(&settings.database, &settings.cache)?;
            let mut artifact = plan.execute(&mut engine)?;
            artifact.executable_sha256 = Some(evaluation::executable_sha256()?);
            let report = evaluation::score_labels(&artifact, labels.as_ref(), &options.corpus)?;
            evaluation::write_outputs(&options.output, &artifact, &report)?;
            println!("{}", options.output.join("report.md").display());
        }
        Command::Score {
            run,
            labels,
            scenarios,
            corpus,
            output,
        } => {
            if output.exists() {
                return Err(
                    "Evaluation output directory already exists; choose a new report directory."
                        .into(),
                );
            }
            let artifact =
                evaluation::read_validated_run(&run, &scenarios, &corpus, &settings.database)?;
            let labels = serde_json::from_slice(&std::fs::read(labels)?)?;
            let report = evaluation::score_labels(&artifact, Some(&labels), &corpus)?;
            evaluation::write_outputs(&output, &artifact, &report)?;
            println!("{}", output.join("report.md").display());
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
