//! Cosine and its original numeric regression test are reused from COA:
//! https://github.com/Daanvdplas/meedoenbalie-rag-learning/blob/cada34fbb4d22bde46d31c3cdbcda495e6d93e9b/src/ranking.rs
use super::{EngineError, ErrorKind, IndexedPassage};
use std::collections::BTreeMap;

pub(super) fn cosine(left: &[f32], right: &[f32]) -> Result<f32, String> {
    if left.is_empty()
        || left.len() != right.len()
        || left.iter().chain(right).any(|v| !v.is_finite())
    {
        return Err("Incompatible or non-finite embedding vectors".into());
    }
    let dot: f32 = left.iter().zip(right).map(|(a, b)| a * b).sum();
    let norm = left.iter().map(|v| v * v).sum::<f32>().sqrt()
        * right.iter().map(|v| v * v).sum::<f32>().sqrt();
    if !norm.is_finite() || norm == 0.0 {
        return Err("Invalid embedding norm".into());
    }
    Ok((dot / norm).clamp(-1.0, 1.0))
}

pub(super) fn rank_cases(
    passages: &[IndexedPassage],
    query: Option<&[f32]>,
    document: Option<&[f32]>,
) -> Result<Vec<(usize, f64)>, EngineError> {
    if query.is_none() && document.is_none() {
        return Err(EngineError::new(
            ErrorKind::InvalidInput,
            "Supply a document or query.",
        ));
    }
    let mut cases: BTreeMap<&str, (usize, f64)> = BTreeMap::new();
    for (index, item) in passages.iter().enumerate() {
        let compare = |vector: &[f32]| {
            cosine(vector, &item.vector)
                .map(f64::from)
                .map_err(|e| EngineError::new(ErrorKind::InvalidInput, e))
        };
        let score = match (query, document) {
            (Some(q), Some(d)) => 0.7 * compare(q)? + 0.3 * compare(d)?,
            (Some(q), None) => compare(q)?,
            (None, Some(d)) => compare(d)?,
            (None, None) => unreachable!(),
        };
        if !score.is_finite() {
            return Err(EngineError::new(
                ErrorKind::Internal,
                "Non-finite ranking score.",
            ));
        }
        let best = cases.entry(&item.case_id).or_insert((index, score));
        if score > best.1
            || (score == best.1 && item.passage.passage_id < passages[best.0].passage.passage_id)
        {
            *best = (index, score);
        }
    }
    if cases.len() < 3 {
        return Err(EngineError::new(
            ErrorKind::IndexUnavailable,
            "Fewer than three cases are available.",
        ));
    }
    // COA's stable score/source ordering, applied after complete case grouping.
    let mut ranked: Vec<_> = cases.into_values().collect();
    ranked.sort_by(|a, b| {
        b.1.total_cmp(&a.1)
            .then(passages[a.0].case_id.cmp(&passages[b.0].case_id))
    });
    ranked.truncate(3);
    Ok(ranked)
}

pub(super) fn normalized_mean(vectors: &[Vec<f32>]) -> Result<Vec<f32>, EngineError> {
    let invalid = |message: &str| EngineError::new(ErrorKind::InvalidInput, message);
    let dimensions = vectors
        .first()
        .ok_or_else(|| invalid("No text embeddings."))?
        .len();
    let mut mean = vec![0.0_f64; dimensions];
    for vector in vectors {
        cosine(vector, vector).map_err(|e| invalid(&e))?;
        if vector.len() != dimensions {
            return Err(invalid("Incompatible embedding dimensions."));
        }
        for (sum, value) in mean.iter_mut().zip(vector) {
            *sum += f64::from(*value) / vectors.len() as f64;
        }
    }
    let norm = mean.iter().map(|v| v * v).sum::<f64>().sqrt();
    if !norm.is_finite() || norm == 0.0 {
        return Err(invalid("The input has no usable mean embedding."));
    }
    let result: Vec<_> = mean.into_iter().map(|v| (v / norm) as f32).collect();
    cosine(&result, &result).map_err(|e| invalid(&e))?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::Passage;

    #[test]
    fn cosine_compares_meaning_vectors_without_hiding_invalid_inputs() {
        assert!((cosine(&[1., 0.], &[1., 0.]).unwrap() - 1.).abs() < 1e-6);
        assert_eq!(cosine(&[1., 0.], &[0., 1.]).unwrap(), 0.);
        assert!(cosine(&[0., 0.], &[1., 0.]).is_err());
        assert!(cosine(&[1.], &[1., 0.]).is_err());
        assert!(cosine(&[f32::NAN], &[1.]).is_err());
    }

    fn candidate(case: &str, id: &str, vector: &[f32]) -> IndexedPassage {
        IndexedPassage {
            case_id: case.into(),
            passage: Passage {
                passage_id: id.into(),
                text: "text".into(),
                start_utf16: 0,
                end_utf16: 4,
            },
            start_byte: 0,
            end_byte: 4,
            vector: vector.to_vec(),
        }
    }

    #[test]
    fn ranks_all_passages_before_grouping_with_case_and_passage_ties() {
        let passages = vec![
            candidate("B", "B:p2", &[1., 0.]),
            candidate("B", "B:p1", &[1., 0.]),
            candidate("B", "B:p3", &[1., 0.]),
            candidate("A", "A:p1", &[1., 0.]),
            candidate("C", "C:p1", &[0., 1.]),
            candidate("D", "D:p1", &[-1., 0.]),
        ];
        let ids = |ranked: Vec<(usize, f64)>| {
            ranked
                .into_iter()
                .map(|(i, _)| {
                    (
                        passages[i].case_id.as_str(),
                        passages[i].passage.passage_id.as_str(),
                    )
                })
                .collect::<Vec<_>>()
        };
        assert_eq!(
            ids(rank_cases(&passages, Some(&[1., 0.]), None).unwrap()),
            [("A", "A:p1"), ("B", "B:p1"), ("C", "C:p1")]
        );
        assert_eq!(
            ids(rank_cases(&passages, None, Some(&[0., 1.])).unwrap()),
            [("C", "C:p1"), ("A", "A:p1"), ("B", "B:p1")]
        );
        let combined = rank_cases(&passages, Some(&[1., 0.]), Some(&[0., 1.])).unwrap();
        assert!((combined[0].1 - 0.7).abs() < 1e-6);
        assert_eq!(ids(combined), [("A", "A:p1"), ("B", "B:p1"), ("C", "C:p1")]);
    }

    #[test]
    fn normalized_mean_rejects_cancellation_and_incompatible_vectors() {
        let mean = normalized_mean(&[vec![1., 0.], vec![0., 1.]]).unwrap();
        assert!((mean[0] - std::f32::consts::FRAC_1_SQRT_2).abs() < 1e-6);
        assert!((cosine(&mean, &mean).unwrap() - 1.).abs() < 1e-6);
        assert!(normalized_mean(&[]).is_err());
        assert!(normalized_mean(&[vec![1., 0.], vec![-1., 0.]]).is_err());
        assert!(normalized_mean(&[vec![1., 0.], vec![1.]]).is_err());
        assert!(normalized_mean(&[vec![f32::INFINITY]]).is_err());
    }
}
