//! Source identity, date validation and hash helpers follow tested COA code:
//! https://github.com/Daanvdplas/meedoenbalie-rag-learning/blob/cada34fbb4d22bde46d31c3cdbcda495e6d93e9b/src/source.rs
//! https://github.com/Daanvdplas/meedoenbalie-rag-learning/blob/cada34fbb4d22bde46d31c3cdbcda495e6d93e9b/src/manifest.rs
use super::{CaseMetadata, EngineError, ErrorKind, SourceSection};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(super) struct CaseRecord {
    pub metadata: CaseMetadata,
    pub text: String,
    pub head_matter: String,
    pub head_matter_text_version: String,
    pub source_json: String,
}

impl CaseRecord {
    pub(super) fn section(&self, section: SourceSection) -> (&str, &str) {
        match section {
            SourceSection::Majority => (&self.text, &self.metadata.text_version),
            SourceSection::HeadMatter => (&self.head_matter, &self.head_matter_text_version),
        }
    }
}

pub(super) fn read_cases(
    directory: &std::path::Path,
) -> Result<std::collections::BTreeMap<String, CaseRecord>, EngineError> {
    let invalid = || {
        EngineError::new(
            ErrorKind::IndexUnavailable,
            "Cannot read a complete, unique Texas JSON corpus.",
        )
    };
    let directory = if directory.join("json").is_dir() {
        directory.join("json")
    } else {
        directory.to_owned()
    };
    let mut files = std::fs::read_dir(directory)
        .map_err(|_| invalid())?
        .map(|entry| entry.map(|e| e.path()).map_err(|_| invalid()))
        .collect::<Result<Vec<_>, _>>()?;
    files.sort();
    let mut result = std::collections::BTreeMap::new();
    for file in files
        .into_iter()
        .filter(|p| p.extension().is_some_and(|e| e == "json"))
    {
        let raw = std::fs::read_to_string(file).map_err(|_| invalid())?;
        let mut case = parse_case(serde_json::from_str(&raw).map_err(|_| invalid())?)?;
        case.source_json = raw;
        if result.insert(case.metadata.case_id.clone(), case).is_some() {
            return Err(invalid());
        }
    }
    Ok(result)
}

pub(super) fn hash(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(bytes))
}

pub(super) fn canonicalize(text: &str) -> String {
    text.replace("\r\n", "\n")
        .replace('\r', "\n")
        .trim()
        .to_owned()
}

pub(super) fn parse_case(value: Value) -> Result<CaseRecord, EngineError> {
    let invalid = || {
        EngineError::new(
            ErrorKind::IndexUnavailable,
            "Invalid corpus metadata or majority opinion.",
        )
    };
    let string = |value: &Value| {
        value
            .as_str()
            .filter(|s| !s.trim().is_empty())
            .map(str::to_owned)
            .ok_or_else(invalid)
    };
    let id = value["id"].as_u64().ok_or_else(invalid)?.to_string();
    let date = string(&value["decision_date"])?;
    validate_date(&date).map_err(|_| invalid())?;
    let opinions = value["casebody"]["opinions"]
        .as_array()
        .ok_or_else(invalid)?;
    let majority: Vec<_> = opinions
        .iter()
        .filter(|o| o["type"] == "majority")
        .collect();
    if majority.len() != 1 {
        return Err(invalid());
    }
    let text = canonicalize(&string(&majority[0]["text"])?);
    let head_matter = value["casebody"]["head_matter"]
        .as_str()
        .map(canonicalize)
        .unwrap_or_default();
    if text.is_empty() {
        return Err(invalid());
    }
    let citations = value["citations"].as_array().ok_or_else(invalid)?;
    let citation = citations
        .iter()
        .find(|c| c["type"] == "official")
        .or(citations.first())
        .ok_or_else(invalid)?;
    Ok(CaseRecord {
        metadata: CaseMetadata {
            case_id: id,
            title: string(&value["name"])?,
            court: string(&value["court"]["name"])?,
            decision_date: date,
            citation: string(&citation["cite"])?,
            text_version: format!("sha256:{}", hash(text.as_bytes())),
        },
        text,
        head_matter_text_version: format!("sha256:{}", hash(head_matter.as_bytes())),
        head_matter,
        source_json: serde_json::to_string(&value).map_err(|_| invalid())?,
    })
}

fn validate_date(date: &str) -> Result<(), String> {
    let bytes = date.as_bytes();
    if bytes.len() != 10
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || !bytes
            .iter()
            .enumerate()
            .all(|(i, c)| i == 4 || i == 7 || c.is_ascii_digit())
    {
        return Err("Expected date YYYY-MM-DD".into());
    }
    let year: u32 = date[..4].parse().map_err(|_| "Invalid year")?;
    let month: usize = date[5..7].parse().map_err(|_| "Invalid month")?;
    let day: u32 = date[8..].parse().map_err(|_| "Invalid day")?;
    let leap = year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400));
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    if year == 0 || !(1..=12).contains(&month) || day == 0 || day > days[month - 1] {
        return Err("Invalid calendar date".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    pub(super) fn source(id: u64, text: &str) -> Value {
        json!({
            "id": id, "name": "Example v. State", "decision_date": "1892-02-29",
            "court": {"name": "Texas Court of Criminal Appeals"},
            "citations": [{"type": "official", "cite": "31 Tex. Crim. 1"}],
            "volume": {"year": 1992},
            "casebody": {"opinions": [
                {"type": "majority", "text": text, "author": "Judge"},
                {"type": "dissent", "text": "Dissent must stay separate."}
            ], "head_matter": "Editorial headnote about the dispute."}
        })
    }

    #[test]
    fn preserves_head_matter_as_a_separate_canonical_source_with_its_own_version() {
        let mut raw = source(42, "The court's majority reasoning.");
        raw["casebody"]["head_matter"] = json!("\r\nEditorial headnote 😀\r\nSecond line.\r\n");
        let case = parse_case(raw.clone()).unwrap();
        let stored = serde_json::to_value(&case).unwrap();
        assert_eq!(stored["head_matter"], "Editorial headnote 😀\nSecond line.");
        assert_eq!(
            stored["head_matter_text_version"],
            format!(
                "sha256:{}",
                hash("Editorial headnote 😀\nSecond line.".as_bytes())
            )
        );
        assert_eq!(case.text, "The court's majority reasoning.");
        assert_eq!(
            serde_json::from_str::<Value>(&case.source_json).unwrap(),
            raw
        );
    }

    #[test]
    fn preserves_metadata_original_opinions_and_canonical_majority_only() {
        let raw = source(42, "\r\nEvidence 😀\r\nSecond paragraph.\r\n");
        let case = parse_case(raw.clone()).unwrap();
        assert_eq!(case.metadata.case_id, "42");
        assert_eq!(case.metadata.decision_date, "1892-02-29");
        assert_eq!(case.text, "Evidence 😀\nSecond paragraph.");
        assert!(!case.text.contains("Dissent"));
        assert_eq!(
            serde_json::from_str::<Value>(&case.source_json).unwrap(),
            raw
        );
        assert_eq!(case.metadata.text_version.len(), 71);
        let mut invalid = source(42, "Text");
        invalid["decision_date"] = json!("1893-02-29");
        assert!(parse_case(invalid).is_err());
        let mut invalid = source(42, "Text");
        invalid["casebody"]["opinions"][0]["type"] = json!("dissent");
        assert!(parse_case(invalid).is_err());
    }

    #[test]
    fn corpus_archive_preserves_exact_utf8_json_bytes_including_floats_and_whitespace() {
        let directory = tempfile::tempdir().unwrap();
        let mut value = source(1, "Majority reasoning");
        value["analysis"] = json!({"pagerank":{"raw": 0.00000025961689552170427}});
        let raw = format!(" \n{}\n ", serde_json::to_string_pretty(&value).unwrap());
        std::fs::write(directory.path().join("case.json"), &raw).unwrap();
        let cases = read_cases(directory.path()).unwrap();
        assert_eq!(cases["1"].source_json.as_bytes(), raw.as_bytes());
    }

    #[test]
    fn corpus_loader_rejects_duplicate_case_ids_before_indexing() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("a.json"), source(1, "Majority").to_string()).unwrap();
        std::fs::write(
            dir.path().join("b.json"),
            source(1, "Other majority").to_string(),
        )
        .unwrap();
        assert!(read_cases(dir.path()).is_err());
        std::fs::write(
            dir.path().join("b.json"),
            source(2, "Other majority").to_string(),
        )
        .unwrap();
        assert_eq!(read_cases(dir.path()).unwrap().len(), 2);
    }
}
