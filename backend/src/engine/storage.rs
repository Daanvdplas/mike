use super::{
    EngineError, ErrorKind, IndexedPassage,
    corpus::{CaseRecord, hash, parse_case},
    embedding::EmbeddingConfig,
    ranking::cosine,
};
use rusqlite::{Connection, OpenFlags, params};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

pub(super) const PIPELINE: &str =
    "majority-lf-trim-v1|chars1600-overlap160-token480-v1|cosine-max-v1";
pub(super) const EXPECTED_COUNT: usize = 135;
pub(super) const EXPECTED_IDS_SHA256: &str =
    "efa425142ba80a8f54cc42e329a1f38c4a5fc5aa0aa853f8c9550fc96640be88";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(super) struct Manifest {
    pub format_version: u32,
    pub pipeline: String,
    pub embedding: EmbeddingConfig,
    pub corpus_version: String,
}

#[derive(Debug, Clone)]
pub(super) struct Snapshot {
    pub cases: BTreeMap<String, CaseRecord>,
    pub passages: Vec<IndexedPassage>,
    pub manifest: Manifest,
}

fn unavailable() -> EngineError {
    EngineError::new(
        ErrorKind::IndexUnavailable,
        "The complete index is missing, incompatible or corrupt; import the corpus again.",
    )
}

pub(super) fn persist(path: &Path, snapshot: &Snapshot) -> Result<(), EngineError> {
    if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
        std::fs::create_dir_all(parent).map_err(|_| unavailable())?;
    }
    let mut connection = Connection::open(path).map_err(|_| unavailable())?;
    let transaction = connection.transaction().map_err(|_| unavailable())?;
    transaction.execute_batch("CREATE TABLE IF NOT EXISTS cases (case_id TEXT PRIMARY KEY, record TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS passages (passage_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, record TEXT NOT NULL, vector BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id = 1), manifest TEXT NOT NULL);
        DELETE FROM passages; DELETE FROM cases; DELETE FROM metadata;").map_err(|_| unavailable())?;
    for (id, case) in &snapshot.cases {
        transaction
            .execute(
                "INSERT INTO cases VALUES (?1, ?2)",
                params![id, serde_json::to_string(case).map_err(|_| unavailable())?],
            )
            .map_err(|_| unavailable())?;
    }
    for passage in &snapshot.passages {
        let bytes: Vec<_> = passage
            .vector
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect();
        transaction
            .execute(
                "INSERT INTO passages VALUES (?1, ?2, ?3, ?4)",
                params![
                    passage.passage.passage_id,
                    passage.case_id,
                    serde_json::to_string(passage).map_err(|_| unavailable())?,
                    bytes
                ],
            )
            .map_err(|_| unavailable())?;
    }
    transaction
        .execute(
            "INSERT INTO metadata VALUES (1, ?1)",
            params![serde_json::to_string(&snapshot.manifest).map_err(|_| unavailable())?],
        )
        .map_err(|_| unavailable())?;
    transaction.commit().map_err(|_| unavailable())
}

pub(super) fn load(path: &Path, count: usize, ids_sha256: &str) -> Result<Snapshot, EngineError> {
    let connection = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|_| unavailable())?;
    let manifest_json: String = connection
        .query_row("SELECT manifest FROM metadata WHERE id = 1", [], |r| {
            r.get(0)
        })
        .map_err(|_| unavailable())?;
    let manifest: Manifest = serde_json::from_str(&manifest_json).map_err(|_| unavailable())?;
    let mut cases = BTreeMap::new();
    let mut statement = connection
        .prepare("SELECT case_id, record FROM cases ORDER BY case_id")
        .map_err(|_| unavailable())?;
    let records = statement
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(|_| unavailable())?;
    for record in records {
        let (id, record) = record.map_err(|_| unavailable())?;
        let case: CaseRecord = serde_json::from_str(&record).map_err(|_| unavailable())?;
        if id != case.metadata.case_id {
            return Err(unavailable());
        }
        cases.insert(id, case);
    }
    let mut passages = Vec::new();
    let mut statement = connection
        .prepare("SELECT passage_id, case_id, record, vector FROM passages ORDER BY passage_id")
        .map_err(|_| unavailable())?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, Vec<u8>>(3)?,
            ))
        })
        .map_err(|_| unavailable())?;
    for row in rows {
        let (id, case, record, bytes) = row.map_err(|_| unavailable())?;
        let mut passage: IndexedPassage =
            serde_json::from_str(&record).map_err(|_| unavailable())?;
        if id != passage.passage.passage_id
            || case != passage.case_id
            || bytes.len()
                != manifest
                    .embedding
                    .dimensions
                    .checked_mul(4)
                    .ok_or_else(unavailable)?
        {
            return Err(unavailable());
        }
        passage.vector = bytes
            .chunks_exact(4)
            .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
            .collect();
        passages.push(passage);
    }
    let snapshot = Snapshot {
        cases,
        passages,
        manifest,
    };
    validate(&snapshot, count, ids_sha256)?;
    Ok(snapshot)
}

pub(super) fn fingerprint(snapshot: &Snapshot) -> Result<String, EngineError> {
    use sha2::{Digest, Sha256};
    let record = serde_json::to_vec(&(
        snapshot.manifest.format_version,
        &snapshot.manifest.pipeline,
        &snapshot.manifest.embedding,
        &snapshot.cases,
        &snapshot.passages,
    ))
    .map_err(|_| unavailable())?;
    let mut digest = Sha256::new();
    digest.update((record.len() as u64).to_le_bytes());
    digest.update(record);
    for passage in &snapshot.passages {
        for value in &passage.vector {
            digest.update(value.to_le_bytes());
        }
    }
    Ok(format!("sha256:{:x}", digest.finalize()))
}

pub(super) fn validate(
    snapshot: &Snapshot,
    count: usize,
    ids_sha256: &str,
) -> Result<(), EngineError> {
    if snapshot.manifest.format_version != 1
        || snapshot.manifest.pipeline != PIPELINE
        || snapshot.manifest.embedding.dimensions == 0
        || snapshot.cases.len() != count
        || count < 3
        || hash(
            snapshot
                .cases
                .keys()
                .cloned()
                .collect::<Vec<_>>()
                .join("\n")
                .as_bytes(),
        ) != ids_sha256
    {
        return Err(unavailable());
    }
    let mut by_case: BTreeMap<&str, Vec<&IndexedPassage>> = BTreeMap::new();
    let mut ids = BTreeSet::new();
    for item in &snapshot.passages {
        let case = snapshot.cases.get(&item.case_id).ok_or_else(unavailable)?;
        let p = &item.passage;
        if !ids.insert(&p.passage_id)
            || p.text.is_empty()
            || item.start_byte >= item.end_byte
            || case.text.get(item.start_byte..item.end_byte) != Some(p.text.as_str())
            || case.text[..item.start_byte].encode_utf16().count() != p.start_utf16
            || p.start_utf16.checked_add(p.text.encode_utf16().count()) != Some(p.end_utf16)
            || item.vector.len() != snapshot.manifest.embedding.dimensions
        {
            return Err(unavailable());
        }
        cosine(&item.vector, &item.vector).map_err(|_| unavailable())?;
        by_case.entry(&item.case_id).or_default().push(item);
    }
    for (id, case) in &snapshot.cases {
        let original =
            parse_case(serde_json::from_str(&case.source_json).map_err(|_| unavailable())?)?;
        if original.metadata != case.metadata || original.text != case.text {
            return Err(unavailable());
        }
        let chunks = by_case.get_mut(id.as_str()).ok_or_else(unavailable)?;
        chunks.sort_by_key(|p| p.start_byte);
        let mut covered = 0;
        for chunk in chunks {
            if chunk.start_byte > covered {
                return Err(unavailable());
            }
            covered = covered.max(chunk.end_byte);
        }
        if covered != case.text.len() {
            return Err(unavailable());
        }
    }
    if fingerprint(snapshot)? != snapshot.manifest.corpus_version {
        return Err(unavailable());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::{
        Passage,
        corpus::{hash, parse_case},
    };
    use serde_json::json;

    fn snapshot() -> Snapshot {
        let mut cases = BTreeMap::new();
        let mut passages = Vec::new();
        for id in 1..=4 {
            let case = parse_case(json!({
                "id": id, "name": "Example", "decision_date": "1892-01-01",
                "court": {"name": "Texas Court of Criminal Appeals"},
                "citations": [{"type": "official", "cite": "Example cite"}],
                "casebody": {"opinions": [{"type":"majority", "text":"Evidence 😀"}]}
            }))
            .unwrap();
            cases.insert(id.to_string(), case);
            passages.push(IndexedPassage {
                case_id: id.to_string(),
                start_byte: 0,
                end_byte: "Evidence 😀".len(),
                passage: Passage {
                    passage_id: format!("{id}:p00000000"),
                    text: "Evidence 😀".into(),
                    start_utf16: 0,
                    end_utf16: 11,
                },
                vector: vec![1., 0.],
            });
        }
        let mut snapshot = Snapshot {
            cases,
            passages,
            manifest: Manifest {
                format_version: 1,
                pipeline: PIPELINE.into(),
                embedding: EmbeddingConfig {
                    model: "test".into(),
                    dimensions: 2,
                    max_tokens: 512,
                    sdk: "test".into(),
                    artifacts_sha256: "test".into(),
                },
                corpus_version: String::new(),
            },
        };
        snapshot.manifest.corpus_version = fingerprint(&snapshot).unwrap();
        snapshot
    }

    fn ids() -> String {
        hash(b"1\n2\n3\n4")
    }

    #[test]
    fn roundtrip_and_reimport_keep_versions_vectors_and_original_majority() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cases.sqlite");
        let expected = snapshot();
        persist(&path, &expected).unwrap();
        persist(&path, &expected).unwrap();
        let loaded = load(&path, 4, &ids()).unwrap();
        assert_eq!(loaded.cases.len(), 4);
        assert_eq!(loaded.passages.len(), 4);
        assert_eq!(
            loaded.manifest.corpus_version,
            expected.manifest.corpus_version
        );
        assert_eq!(loaded.passages[0].vector, vec![1., 0.]);
        assert_eq!(loaded.cases["1"].text, "Evidence 😀");
        assert!(load(&path, EXPECTED_COUNT, EXPECTED_IDS_SHA256).is_err());
    }

    #[test]
    fn incomplete_index_never_becomes_ready_even_with_three_remaining_cases() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cases.sqlite");
        persist(&path, &snapshot()).unwrap();
        rusqlite::Connection::open(&path)
            .unwrap()
            .execute("DELETE FROM cases WHERE case_id = '4'", [])
            .unwrap();
        assert!(load(&path, 4, &ids()).is_err());
    }

    #[test]
    fn corrupted_vector_or_version_is_rejected_on_restart() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cases.sqlite");
        persist(&path, &snapshot()).unwrap();
        rusqlite::Connection::open(&path)
            .unwrap()
            .execute(
                "UPDATE passages SET vector = X'0000' WHERE passage_id = '1:p00000000'",
                [],
            )
            .unwrap();
        assert!(load(&path, 4, &ids()).is_err());
        persist(&path, &snapshot()).unwrap();
        rusqlite::Connection::open(&path)
            .unwrap()
            .execute("UPDATE metadata SET manifest = '{}'", [])
            .unwrap();
        assert!(load(&path, 4, &ids()).is_err());
    }
}
