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
    rank_cases_excluding(passages, query, document, &[])
}

pub(super) fn rank_cases_excluding(
    passages: &[IndexedPassage],
    query: Option<&[f32]>,
    document: Option<&[f32]>,
    excluded_case_ids: &[String],
) -> Result<Vec<(usize, f64)>, EngineError> {
    if query.is_none() && document.is_none() {
        return Err(EngineError::new(
            ErrorKind::InvalidInput,
            "Supply a document or query.",
        ));
    }
    let mut cases: BTreeMap<&str, (usize, f64)> = BTreeMap::new();
    for (index, item) in passages.iter().enumerate() {
        if excluded_case_ids.contains(&item.case_id) {
            continue;
        }
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
        if a.1 == b.1 {
            passages[a.0].case_id.cmp(&passages[b.0].case_id)
        } else {
            b.1.total_cmp(&a.1)
        }
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

    #[test]
    fn numerically_equal_signed_zero_scores_use_case_id_tie_break() {
        let passages = vec![
            candidate("A", "A:p1", &[-1e-20, 0., 1e10]),
            candidate("B", "B:p1", &[0., 0., 1.]),
            candidate("C", "C:p1", &[-1., 0., 0.]),
            candidate("D", "D:p1", &[0., -1., 0.]),
        ];
        let ranked = rank_cases(&passages, Some(&[1e-20, 1., 0.]), None).unwrap();
        assert_eq!(ranked[0].1, 0.);
        assert_eq!(ranked[1].1, 0.);
        assert_eq!(passages[ranked[0].0].case_id, "A");
    }
}

#[cfg(test)]
mod independent_reference_tests {
    use super::*;
    use crate::engine::Passage;

    fn passage(case_id: &str, passage_id: &str, vector: &[f32]) -> IndexedPassage {
        IndexedPassage {
            case_id: case_id.into(),
            passage: Passage {
                passage_id: passage_id.into(),
                text: "reference evidence".into(),
                start_utf16: 0,
                end_utf16: 18,
            },
            start_byte: 0,
            end_byte: 18,
            vector: vector.to_vec(),
        }
    }

    // Independent arithmetic: f64 dot/norms, without production cosine or grouping.
    fn reference_cosine(left: &[f32], right: &[f32]) -> f64 {
        let left: Vec<_> = left.iter().map(|v| f64::from(*v)).collect();
        let right: Vec<_> = right.iter().map(|v| f64::from(*v)).collect();
        let numerator = left.iter().zip(&right).map(|(a, b)| a * b).sum::<f64>();
        let left_length = left.iter().map(|v| v * v).sum::<f64>().sqrt();
        let right_length = right.iter().map(|v| v * v).sum::<f64>().sqrt();
        numerator / (left_length * right_length)
    }

    fn reference_all_cases(
        passages: &[IndexedPassage],
        query: Option<&[f32]>,
        document: Option<&[f32]>,
    ) -> Vec<(String, String, f64)> {
        let mut identities: Vec<_> = passages.iter().map(|p| p.case_id.clone()).collect();
        identities.sort();
        identities.dedup();
        let mut cases = Vec::new();
        for case in identities {
            let mut candidates: Vec<_> = passages
                .iter()
                .filter(|p| p.case_id == case)
                .map(|p| {
                    let score = match (query, document) {
                        (Some(q), Some(d)) => {
                            0.7 * reference_cosine(q, &p.vector)
                                + 0.3 * reference_cosine(d, &p.vector)
                        }
                        (Some(q), None) => reference_cosine(q, &p.vector),
                        (None, Some(d)) => reference_cosine(d, &p.vector),
                        _ => panic!("The reference requires an input"),
                    };
                    (p.passage.passage_id.clone(), score)
                })
                .collect();
            candidates.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap().then(a.0.cmp(&b.0)));
            cases.push((case, candidates[0].0.clone(), candidates[0].1));
        }
        cases.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap().then(a.0.cmp(&b.0)));
        cases
    }

    #[test]
    fn top_three_matches_independent_full_f64_ranking_in_every_mode_and_order() {
        let mut passages = vec![
            passage("A", "A:2", &[3., 4., 0.]),
            passage("A", "A:1", &[3., 4., 0.]),
            passage("B", "B:1", &[0., 1., 0.]),
            passage("B", "B:2", &[0., 2., 1.]),
            passage("C", "C:1", &[0., 0., 1.]),
            passage("D", "D:1", &[1., 0., 0.]),
            passage("E", "E:1", &[-1., -1., -1.]),
            passage("F", "F:2", &[4., 3., 2.]),
            passage("F", "F:1", &[4., 3., 2.]),
            passage("G", "G:1", &[1., 0., 0.]),
            passage("H", "H:1", &[0., 1., 0.]),
            // The combined winner occurs last, so no candidate prefix may be used.
            passage("Z", "Z:1", &[2., 1., 0.]),
        ];
        let query = [1., 0., 0.];
        let document = [0., 1., 0.];
        for reverse in [false, true] {
            if reverse {
                passages.reverse();
            }
            for (query, document) in [
                (Some(query.as_slice()), None),
                (None, Some(document.as_slice())),
                (Some(query.as_slice()), Some(document.as_slice())),
            ] {
                let reference = reference_all_cases(&passages, query, document);
                let actual = rank_cases(&passages, query, document).unwrap();
                assert_eq!(actual.len(), 3);
                for ((index, score), expected) in actual.iter().zip(&reference[..3]) {
                    assert_eq!(passages[*index].case_id, expected.0);
                    assert_eq!(passages[*index].passage.passage_id, expected.1);
                    assert!((score - expected.2).abs() < 1e-6);
                }
                let last_returned_score = actual[2].1;
                for omitted in &reference[3..] {
                    assert!(omitted.2 <= last_returned_score + 1e-6);
                }
            }
        }
    }

    #[test]
    fn ranking_rejects_invalid_inputs_and_incomplete_case_sets() {
        let passages = vec![
            passage("A", "A:1", &[1., 0.]),
            passage("B", "B:1", &[0., 1.]),
            passage("C", "C:1", &[-1., 0.]),
        ];
        for query in [
            vec![],
            vec![0., 0.],
            vec![1.],
            vec![f32::NAN, 0.],
            vec![f32::INFINITY, 0.],
        ] {
            assert!(rank_cases(&passages, Some(&query), None).is_err());
        }
        assert!(rank_cases(&passages, None, None).is_err());
        assert_eq!(
            rank_cases(&passages[..2], Some(&[1., 0.]), None)
                .unwrap_err()
                .kind,
            ErrorKind::IndexUnavailable
        );
        let mean = normalized_mean(&[vec![3., 0.], vec![0., 4.]]).unwrap();
        assert!((f64::from(mean[0]) - 0.6).abs() < 1e-6);
        assert!((f64::from(mean[1]) - 0.8).abs() < 1e-6);
    }
}
