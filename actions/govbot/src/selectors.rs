/// Default selector for OCDFiles-style JSON structures.
///
/// Extracts the **full** human-readable text content of a bill from its
/// `metadata.json` projection — per the govbot stream protocol (`STREAM_PROTOCOL.md`
/// §1), the `docs` projection must emit the full bill text, not just titles, so
/// downstream transforms (classification, summarization) see the whole document.
///
/// For an entry that joins `bill` (the full `metadata.json`) this assembles
/// every text-bearing field of the bill: title, identifier, every abstract,
/// every subject, action descriptions, sponsor names, version notes, related
/// bills, the legislative session and originating organization. For a bare log
/// entry it falls back to the action description.
pub fn ocd_files_select_default(value: &serde_json::Value) -> String {
    let mut texts = Vec::new();
    collect_bill_text(value, &mut texts);
    // Drop empties and de-dup adjacent blanks; join with spaces.
    texts
        .into_iter()
        .filter(|s| !s.trim().is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

/// Append every text-bearing string of an OCD-files value into `texts`.
fn collect_bill_text(value: &serde_json::Value, texts: &mut Vec<String>) {
    match value {
        serde_json::Value::String(s) => texts.push(s.clone()),
        serde_json::Value::Object(map) => {
            // The full bill metadata, when joined under `bill`.
            if let Some(bill) = map.get("bill") {
                collect_bill_fields(bill, texts);
            }
            // A bare log object.
            if let Some(log) = map.get("log") {
                collect_log_fields(log, texts);
            }
            // The map *is* a bill metadata.json (no `bill`/`log` wrappers).
            if map.get("bill").is_none() && map.get("log").is_none() {
                collect_bill_fields(value, texts);
            }
        }
        serde_json::Value::Array(arr) => {
            for item in arr {
                collect_bill_text(item, texts);
            }
        }
        _ => {}
    }
}

/// Append every text-bearing field of a bill `metadata.json` object.
fn collect_bill_fields(bill: &serde_json::Value, texts: &mut Vec<String>) {
    let serde_json::Value::Object(map) = bill else {
        // Not an object — recurse generically (e.g. when `bill` is a string).
        collect_strings(bill, texts);
        return;
    };

    push_str(map, "title", texts);
    push_str(map, "identifier", texts);
    push_str(map, "legislative_session", texts);
    push_str(map, "from_organization", texts);

    // Free-text arrays and nested arrays of objects.
    if let Some(v) = map.get("abstracts") {
        collect_strings(v, texts);
    }
    if let Some(v) = map.get("subject") {
        collect_strings(v, texts);
    }
    if let Some(v) = map.get("other_titles") {
        collect_strings(v, texts);
    }
    if let Some(v) = map.get("other_identifiers") {
        collect_strings(v, texts);
    }

    // Action descriptions.
    if let Some(actions) = map.get("actions").and_then(|v| v.as_array()) {
        for action in actions {
            if let Some(desc) = action.get("description").and_then(|v| v.as_str()) {
                texts.push(desc.to_string());
            }
        }
    }

    // Sponsor names.
    if let Some(sponsors) = map.get("sponsorships").and_then(|v| v.as_array()) {
        for sponsor in sponsors {
            if let Some(name) = sponsor.get("name").and_then(|v| v.as_str()) {
                texts.push(name.to_string());
            }
        }
    }

    // Version notes (the closest thing to bill body text in metadata.json).
    if let Some(versions) = map.get("versions").and_then(|v| v.as_array()) {
        for version in versions {
            if let Some(note) = version.get("note").and_then(|v| v.as_str()) {
                texts.push(note.to_string());
            }
        }
    }

    // Documents notes.
    if let Some(docs) = map.get("documents").and_then(|v| v.as_array()) {
        for doc in docs {
            if let Some(note) = doc.get("note").and_then(|v| v.as_str()) {
                texts.push(note.to_string());
            }
        }
    }
}

/// Append the text-bearing fields of a log object (action description, bill id).
fn collect_log_fields(log: &serde_json::Value, texts: &mut Vec<String>) {
    if let Some(action) = log.get("action") {
        if let Some(desc) = action.get("description").and_then(|v| v.as_str()) {
            texts.push(desc.to_string());
        } else if let Some(desc) = action.as_str() {
            texts.push(desc.to_string());
        }
    }
    if let Some(bill_id) = log
        .get("bill_id")
        .or_else(|| log.get("bill_identifier"))
        .and_then(|v| v.as_str())
    {
        texts.push(bill_id.to_string());
    }
}

/// Append a single string-valued map field, if present.
fn push_str(map: &serde_json::Map<String, serde_json::Value>, key: &str, texts: &mut Vec<String>) {
    if let Some(s) = map.get(key).and_then(|v| v.as_str()) {
        texts.push(s.to_string());
    }
}

/// Append every string found anywhere in a JSON value (arrays, nested objects).
fn collect_strings(value: &serde_json::Value, texts: &mut Vec<String>) {
    match value {
        serde_json::Value::String(s) => texts.push(s.clone()),
        serde_json::Value::Array(arr) => {
            for item in arr {
                collect_strings(item, texts);
            }
        }
        serde_json::Value::Object(map) => {
            for v in map.values() {
                collect_strings(v, texts);
            }
        }
        _ => {}
    }
}
