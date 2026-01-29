/// Default selector for OCDFiles-style JSON structures.
/// Extracts human-readable text content from a JSON value, focusing on bill and log content.
pub fn ocd_files_select_default(value: &serde_json::Value) -> String {
    match value {
        serde_json::Value::String(s) => s.clone(),
        serde_json::Value::Object(map) => {
            let mut texts = Vec::new();

            // Extract from bill object (if present)
            if let Some(bill) = map.get("bill") {
                if let Some(title) = bill.get("title").and_then(|v| v.as_str()) {
                    texts.push(title.to_string());
                }
                if let Some(subjects) = bill.get("subject") {
                    texts.push(ocd_files_select_default(subjects));
                }
                if let Some(abstracts) = bill.get("abstracts") {
                    texts.push(ocd_files_select_default(abstracts));
                }
                if let Some(session) = bill.get("legislative_session").and_then(|v| v.as_str()) {
                    texts.push(session.to_string());
                }
                if let Some(org) = bill.get("from_organization").and_then(|v| v.as_str()) {
                    texts.push(org.to_string());
                }
            }

            // Extract from log object (if present)
            if let Some(log) = map.get("log") {
                if let Some(action) = log.get("action") {
                    // Extract description from action object
                    if let Some(desc) = action.get("description").and_then(|v| v.as_str()) {
                        texts.push(desc.to_string());
                    }
                    // Or if action is directly a string
                    if let Some(desc_str) = action.as_str() {
                        texts.push(desc_str.to_string());
                    }
                }
                // Also check for bill_id in log
                if let Some(bill_id) = log
                    .get("bill_id")
                    .or_else(|| log.get("bill_identifier"))
                    .and_then(|v| v.as_str())
                {
                    texts.push(bill_id.to_string());
                }
            }

            // Extract from action object directly (if present at top level, e.g., when processing log object)
            if let Some(action) = map.get("action") {
                // Extract description from action object
                if let Some(desc) = action.get("description").and_then(|v| v.as_str()) {
                    texts.push(desc.to_string());
                }
                // Or if action is directly a string
                if let Some(desc_str) = action.as_str() {
                    texts.push(desc_str.to_string());
                }
            }

            // Fallback: extract from all other text fields (excluding metadata)
            for (key, val) in map {
                if !key.starts_with("_")
                    && key != "id"
                    && key != "sources"
                    && key != "timestamp"
                    && key != "bill"
                    && key != "log"
                    && key != "title"
                    && key != "action"
                    && key != "subjects"
                    && key != "abstracts"
                    && key != "legislative_session"
                    && key != "from_organization"
                {
                    if let Some(text) = val.as_str() {
                        texts.push(text.to_string());
                    } else if val.is_object() || val.is_array() {
                        texts.push(ocd_files_select_default(val));
                    }
                }
            }

            texts.join(" ")
        }
        serde_json::Value::Array(arr) => arr
            .iter()
            .map(ocd_files_select_default)
            .collect::<Vec<_>>()
            .join(" "),
        _ => String::new(),
    }
}
