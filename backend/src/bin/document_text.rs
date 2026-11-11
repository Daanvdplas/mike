//! Minimal stdin/stdout bridge to the same upload extractor used by the HTTP API.
use serde_json::{Value, json};
use std::io::{Read, Write};
use texas_case_finder::extraction::MAX_DOCUMENT_BYTES;

fn extract(filename: &str, bytes: &[u8]) -> Value {
    match texas_case_finder::extraction::extract_document(filename, bytes) {
        Ok(text) => json!({"status": 200, "text": text}),
        Err(error) => {
            json!({"status": error.status.as_u16(), "error": {"code": error.code, "message": error.message}})
        }
    }
}

fn main() {
    let filename = std::env::args().nth(1).unwrap_or_default();
    let mut bytes = Vec::new();
    let result = match std::io::stdin()
        .take(MAX_DOCUMENT_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
    {
        Ok(_) => extract(&filename, &bytes),
        Err(_) => {
            json!({"status":400,"error":{"code":"invalid_input","message":"Cannot read document input."}})
        }
    };
    if let Ok(data) = serde_json::to_vec(&result) {
        let _ = std::io::stdout().write_all(&data);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preserves_canonical_unicode_text_exactly() {
        let text = "Confession 🧪 evidence\r\n\r\nAn entire second paragraph.\n";
        let response = extract("case.TXT", text.as_bytes());
        assert_eq!(response["status"], 200);
        assert_eq!(response["text"], text);
    }
    #[test]
    fn preserves_existing_type_and_readability_errors() {
        assert_eq!(extract("case.docx", b"text")["status"], 415);
        assert_eq!(extract("case.pdf", b"%PDF-broken")["status"], 422);
        assert_eq!(extract("case.txt", &[0xff, 0xfe])["status"], 422);
        assert_eq!(extract("case.txt", b" \n")["status"], 422);
    }
    #[test]
    fn preserves_ten_mib_upload_limit() {
        let large = vec![b'x'; MAX_DOCUMENT_BYTES + 1];
        assert_eq!(extract("case.txt", &large)["status"], 413);
    }
}
