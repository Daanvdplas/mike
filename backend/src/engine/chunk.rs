use super::{EngineError, ErrorKind, Passage};

pub(super) const TOKEN_BUDGET: usize = 480;

#[derive(Debug, Clone)]
pub(super) struct TextChunk {
    pub passage: Passage,
    pub start_byte: usize,
    pub end_byte: usize,
}

pub(super) fn chunk_text(
    text: &str,
    prefix: &str,
    token_count: impl Fn(&str) -> Result<usize, EngineError>,
) -> Result<Vec<TextChunk>, EngineError> {
    if text.trim().is_empty() {
        return Err(EngineError::new(
            ErrorKind::InvalidInput,
            "The text is empty.",
        ));
    }
    let mut utf16 = 0;
    let mut boundaries = Vec::new();
    for (byte, character) in text.char_indices() {
        boundaries.push((byte, utf16));
        utf16 += character.len_utf16();
    }
    boundaries.push((text.len(), utf16));
    let length = boundaries.len() - 1;
    let mut start = 0;
    let mut result = Vec::new();
    while start < length {
        let mut end = (start + 1600).min(length);
        while token_count(&text[boundaries[start].0..boundaries[end].0])? > TOKEN_BUDGET {
            if end == start + 1 {
                return Err(EngineError::new(
                    ErrorKind::InvalidInput,
                    "A text character exceeds the model token budget.",
                ));
            }
            end = start + ((end - start) * 3 / 4).max(1);
        }
        result.push(TextChunk {
            passage: Passage {
                source_section: None,
                text_version: None,
                passage_id: format!("{prefix}:p{:08}", result.len()),
                text: text[boundaries[start].0..boundaries[end].0].into(),
                start_utf16: boundaries[start].1,
                end_utf16: boundaries[end].1,
            },
            start_byte: boundaries[start].0,
            end_byte: boundaries[end].0,
        });
        if end == length {
            break;
        }
        let overlap = 160.min(end - start - 1);
        start = end - overlap;
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unicode_chunks_cover_all_text_with_exact_utf16_spans_and_no_truncation() {
        let text = "Witness 😀 described e\u{301}vidence.\n".repeat(180);
        let chunks = chunk_text(&text, "case", |s| Ok(s.chars().count() + 2)).unwrap();
        assert!(chunks.len() > 2);
        assert_eq!(chunks[0].start_byte, 0);
        assert_eq!(chunks.last().unwrap().end_byte, text.len());
        let units: Vec<_> = text.encode_utf16().collect();
        for chunk in &chunks {
            let p = &chunk.passage;
            assert_eq!(&text[chunk.start_byte..chunk.end_byte], p.text);
            assert_eq!(
                String::from_utf16(&units[p.start_utf16..p.end_utf16]).unwrap(),
                p.text
            );
            assert!(p.text.chars().count() + 2 <= TOKEN_BUDGET);
        }
        for pair in chunks.windows(2) {
            assert!(pair[1].start_byte > pair[0].start_byte);
            assert!(pair[1].start_byte < pair[0].end_byte);
        }
        assert!(chunk_text(" \n ", "case", |s| Ok(s.len())).is_err());
    }
}
