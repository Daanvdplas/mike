use crate::api_error::ApiError;

pub const MAX_DOCUMENT_BYTES: usize = 10 * 1024 * 1024;

pub fn extract_document(filename: &str, bytes: &[u8]) -> Result<String, ApiError> {
    if bytes.len() > MAX_DOCUMENT_BYTES {
        return Err(ApiError::new(
            axum::http::StatusCode::PAYLOAD_TOO_LARGE,
            "document_too_large",
            "The document must not exceed 10 MiB.",
        ));
    }
    let extension = std::path::Path::new(filename)
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    let text = match extension.as_str() {
        "txt" => {
            if bytes.contains(&0) || bytes.starts_with(b"%PDF-") {
                return Err(unreadable());
            }
            std::str::from_utf8(bytes)
                .map_err(|_| unreadable())?
                .to_owned()
        }
        "pdf" => {
            if !bytes.starts_with(b"%PDF-") {
                return Err(unreadable());
            }
            pdf_extract::extract_text_from_mem(bytes).map_err(|_| unreadable())?
        }
        _ => {
            return Err(ApiError::new(
                axum::http::StatusCode::UNSUPPORTED_MEDIA_TYPE,
                "unsupported_document",
                "Upload a PDF or TXT document.",
            ));
        }
    };
    if text.trim().is_empty() {
        return Err(unreadable());
    }
    Ok(text)
}

fn unreadable() -> ApiError {
    ApiError::new(
        axum::http::StatusCode::UNPROCESSABLE_ENTITY,
        "unreadable_document",
        "The document contains no readable text. Scans require OCR, which is not supported.",
    )
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    #[test]
    fn txt_preserves_the_complete_unicode_document() {
        let text = "Witness 🧪 testimony\n\nAn exact second paragraph.\n";
        assert_eq!(extract_document("case.TXT", text.as_bytes()).unwrap(), text);
    }

    #[test]
    fn unsupported_extension_is_not_treated_as_plain_text() {
        let error = extract_document("case.docx", b"plain but unsupported").unwrap_err();
        assert_eq!(error.status, axum::http::StatusCode::UNSUPPORTED_MEDIA_TYPE);
        assert_eq!(error.code, "unsupported_document");
    }

    #[test]
    fn empty_and_binary_txt_are_unreadable() {
        for bytes in [b"  \n\t".as_slice(), b"binary\0file", &[0xff, 0xfe]] {
            assert_eq!(
                extract_document("case.txt", bytes).unwrap_err().code,
                "unreadable_document"
            );
        }
    }

    #[test]
    fn file_limit_is_exactly_ten_mib() {
        let bytes = vec![b'a'; MAX_DOCUMENT_BYTES];
        assert_eq!(
            extract_document("case.txt", &bytes).unwrap().len(),
            MAX_DOCUMENT_BYTES
        );
        let oversized = vec![b'a'; MAX_DOCUMENT_BYTES + 1];
        assert_eq!(
            extract_document("case.txt", &oversized)
                .err()
                .unwrap()
                .status,
            axum::http::StatusCode::PAYLOAD_TOO_LARGE
        );
    }

    #[test]
    fn text_pdf_is_extracted_instead_of_embedded_as_binary() {
        let pdf = text_pdf(Some("Witness testimony concerns evidence."));
        let text = extract_document("case.pdf", &pdf).unwrap();
        assert!(text.contains("Witness testimony concerns evidence."));
        assert!(!text.contains("%PDF"));
    }

    #[test]
    fn corrupt_and_textless_pdfs_require_readable_text() {
        for bytes in [b"%PDF-1.4 broken".to_vec(), text_pdf(None)] {
            assert_eq!(
                extract_document("case.pdf", &bytes).unwrap_err().code,
                "unreadable_document"
            );
        }
    }

    pub(crate) fn text_pdf(text: Option<&str>) -> Vec<u8> {
        let content = text
            .map(|s| format!("BT /F1 12 Tf 72 720 Td ({s}) Tj ET"))
            .unwrap_or_default();
        let objects = [
            "<< /Type /Catalog /Pages 2 0 R >>".to_owned(),
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>".to_owned(),
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>".to_owned(),
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>".to_owned(),
            format!("<< /Length {} >>\nstream\n{content}\nendstream", content.len()),
        ];
        let mut pdf = b"%PDF-1.4\n".to_vec();
        let mut offsets = vec![];
        for (index, object) in objects.iter().enumerate() {
            offsets.push(pdf.len());
            pdf.extend_from_slice(format!("{} 0 obj\n{object}\nendobj\n", index + 1).as_bytes());
        }
        let xref = pdf.len();
        pdf.extend_from_slice(b"xref\n0 6\n0000000000 65535 f \n");
        for offset in offsets {
            pdf.extend_from_slice(format!("{offset:010} 00000 n \n").as_bytes());
        }
        pdf.extend_from_slice(
            format!("trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").as_bytes(),
        );
        pdf
    }
}
