use crate::{
    api::Backend,
    engine::{CaseDetail, Engine, EngineError, HealthResponse, SearchResponse},
};
use axum::http::HeaderValue;

impl Backend for Engine {
    fn search(
        &mut self,
        query: Option<&str>,
        document: Option<&str>,
    ) -> Result<SearchResponse, EngineError> {
        Engine::search(self, query, document)
    }
    fn get_case(&self, case_id: &str) -> Result<CaseDetail, EngineError> {
        Engine::get_case(self, case_id)
    }
    fn health(&self) -> HealthResponse {
        Engine::health(self)
    }
}
use std::{net::SocketAddr, path::PathBuf};

#[derive(Debug, PartialEq)]
pub enum Command {
    Serve,
    Import(PathBuf),
    Search(String),
    Evaluate(EvalOptions),
    Score {
        run: PathBuf,
        labels: PathBuf,
        scenarios: PathBuf,
        corpus: PathBuf,
        output: PathBuf,
    },
}

#[derive(Debug, PartialEq)]
pub struct EvalOptions {
    pub scenarios: PathBuf,
    pub corpus: PathBuf,
    pub output: PathBuf,
    pub scenario_ids: Vec<String>,
    pub labels: Option<PathBuf>,
}

impl Command {
    pub fn parse(args: &[String]) -> Result<Self, String> {
        match args {
            [] => Ok(Self::Serve),
            [command] if command == "serve" => Ok(Self::Serve),
            [command, path] if command == "import" && !path.is_empty() => {
                Ok(Self::Import(PathBuf::from(path)))
            }
            [command, scenarios, corpus, output, options @ ..] if command == "eval" => {
                let mut parsed = EvalOptions {scenarios: scenarios.into(), corpus: corpus.into(), output: output.into(), scenario_ids:Vec::new(), labels:None};
                let mut options = options.iter();
                while let Some(option) = options.next() {
                    let value = options.next().filter(|value| !value.trim().is_empty()).ok_or("Eval options require a value.")?;
                    match option.as_str() {
                        "--scenario-id" => parsed.scenario_ids.push(value.clone()),
                        "--labels" if parsed.labels.is_none() => parsed.labels = Some(value.into()),
                        _ => return Err("Unknown or duplicate eval option.".into()),
                    }
                }
                Ok(Self::Evaluate(parsed))
            }
            [command, run, labels, scenarios, corpus, output] if command == "score" => Ok(Self::Score {run:run.into(), labels:labels.into(), scenarios:scenarios.into(), corpus:corpus.into(), output:output.into()}),
            [command, words @ ..] if command == "search" => {
                let query = words.join(" ").trim().to_owned();
                if query.is_empty() {
                    Err("Search needs a question.".into())
                } else {
                    Ok(Self::Search(query))
                }
            }
            _ => {
                Err("Usage: texas-case-finder [serve | import CORPUS_DIR | search QUESTION | eval SCENARIOS CORPUS_DIR OUTPUT_DIR [--scenario-id ID] [--labels FILE] | score RUN_JSON LABELS_JSON SCENARIOS CORPUS_DIR OUTPUT_DIR]".into())
            }
        }
    }
}

#[derive(Debug)]
pub struct Settings {
    pub database: PathBuf,
    pub cache: PathBuf,
    pub bind: SocketAddr,
    pub cors_origins: Vec<HeaderValue>,
}

impl Settings {
    pub fn from_env() -> Result<Self, String> {
        Self::from_lookup(|name| std::env::var(name).ok())
    }
    fn from_lookup(lookup: impl Fn(&str) -> Option<String>) -> Result<Self, String> {
        let database =
            PathBuf::from(lookup("ADAMI_DB_PATH").unwrap_or_else(|| "data/cases.sqlite3".into()));
        let cache =
            PathBuf::from(lookup("ADAMI_CACHE_DIR").unwrap_or_else(|| ".fastembed_cache".into()));
        let bind = lookup("ADAMI_BIND_ADDR")
            .unwrap_or_else(|| "127.0.0.1:8000".into())
            .parse()
            .map_err(|_| "ADAMI_BIND_ADDR must be an IP address and port.".to_owned())?;
        let origins = lookup("ADAMI_CORS_ORIGINS")
            .unwrap_or_else(|| "http://localhost:5173,http://127.0.0.1:5173".into());
        let cors_origins = origins
            .split(',')
            .map(|origin| {
                let uri: axum::http::Uri = origin
                    .trim()
                    .parse()
                    .map_err(|_| "Invalid CORS origin.".to_owned())?;
                let scheme = uri
                    .scheme_str()
                    .ok_or("CORS origin needs http:// or https://.")?;
                let authority = uri.authority().ok_or("CORS origin needs a host.")?;
                if !matches!(scheme, "http" | "https")
                    || uri.path() != "/"
                    || uri.query().is_some()
                    || authority.as_str().contains('@')
                {
                    return Err("CORS values must be complete HTTP origins without a path.".into());
                }
                format!("{scheme}://{authority}")
                    .parse::<HeaderValue>()
                    .map_err(|_| "Invalid CORS origin.".to_owned())
            })
            .collect::<Result<Vec<_>, String>>()?;
        Ok(Self {
            database,
            cache,
            bind,
            cors_origins,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn cli_has_explicit_import_serve_and_query_search_commands() {
        assert_eq!(Command::parse(&[]).unwrap(), Command::Serve);
        assert_eq!(Command::parse(&args(&["serve"])).unwrap(), Command::Serve);
        assert_eq!(
            Command::parse(&args(&["import", "/tmp/corpus"])).unwrap(),
            Command::Import(PathBuf::from("/tmp/corpus"))
        );
        assert_eq!(
            Command::parse(&args(&["search", "witness", "evidence"])).unwrap(),
            Command::Search("witness evidence".into())
        );
        for values in [
            &["import"][..],
            &["serve", "unexpected"],
            &["search"],
            &["search", "  "],
            &["unknown"],
        ] {
            assert!(Command::parse(&args(values)).is_err());
        }
    }

    #[test]
    fn evaluation_cli_requires_paths_and_validates_repeatable_selection_options() {
        assert_eq!(
            Command::parse(&args(&[
                "eval",
                "scenarios.json",
                "corpus",
                "out",
                "--scenario-id",
                "E01",
                "--labels",
                "labels.json"
            ]))
            .unwrap(),
            Command::Evaluate(EvalOptions {
                scenarios: "scenarios.json".into(),
                corpus: "corpus".into(),
                output: "out".into(),
                scenario_ids: vec!["E01".into()],
                labels: Some("labels.json".into())
            })
        );
        for values in [
            &["eval"][..],
            &["eval", "a", "b", "c", "--unknown", "x"],
            &["eval", "a", "b", "c", "--scenario-id"],
            &["eval", "a", "b", "c", "--labels", "x", "--labels", "y"],
        ] {
            assert!(Command::parse(&args(values)).is_err());
        }
    }

    #[test]
    fn default_settings_are_local_and_do_not_require_secrets() {
        let settings = Settings::from_lookup(|_| None).unwrap();
        assert_eq!(
            settings.bind,
            "127.0.0.1:8000".parse::<SocketAddr>().unwrap()
        );
        assert_eq!(settings.database, PathBuf::from("data/cases.sqlite3"));
        assert_eq!(settings.cache, PathBuf::from(".fastembed_cache"));
        assert_eq!(
            settings.cors_origins,
            vec![
                HeaderValue::from_static("http://localhost:5173"),
                HeaderValue::from_static("http://127.0.0.1:5173")
            ]
        );
    }

    #[test]
    fn settings_accept_explicit_paths_address_and_cors_allowlist() {
        let settings = Settings::from_lookup(|key| {
            Some(
                match key {
                    "ADAMI_DB_PATH" => "/tmp/cases.sqlite3",
                    "ADAMI_CACHE_DIR" => "/tmp/model-cache",
                    "ADAMI_BIND_ADDR" => "127.0.0.1:9000",
                    "ADAMI_CORS_ORIGINS" => "http://localhost:3000, http://127.0.0.1:3000",
                    _ => return None,
                }
                .into(),
            )
        })
        .unwrap();
        assert_eq!(settings.database, PathBuf::from("/tmp/cases.sqlite3"));
        assert_eq!(settings.bind.port(), 9000);
        assert_eq!(settings.cors_origins.len(), 2);
        assert_eq!(settings.cors_origins[1], "http://127.0.0.1:3000");
    }

    #[test]
    fn invalid_binding_and_non_origin_cors_values_are_configuration_errors() {
        for (name, value) in [
            ("ADAMI_BIND_ADDR", "not an address"),
            ("ADAMI_CORS_ORIGINS", "*"),
            ("ADAMI_CORS_ORIGINS", "http://localhost:3000/path"),
            ("ADAMI_CORS_ORIGINS", "not an origin"),
        ] {
            assert!(Settings::from_lookup(|key| (key == name).then(|| value.into())).is_err());
        }
    }
}
