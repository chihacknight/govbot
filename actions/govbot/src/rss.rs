use chrono::{DateTime, TimeZone, Utc};
use rss::{ChannelBuilder, ItemBuilder};
use serde_json::Value;
use std::collections::HashSet;

/// Parse timestamp string in format YYYYMMDDTHHMMSSZ to DateTime
pub fn parse_timestamp(timestamp_str: &str) -> Option<DateTime<Utc>> {
    // Format: 20250428T040000Z (Z indicates UTC)
    if timestamp_str.len() != 16 || !timestamp_str.ends_with('Z') {
        return None;
    }

    let date_part = &timestamp_str[0..8]; // YYYYMMDD
    let time_part = &timestamp_str[9..15]; // HHMMSS

    let year: i32 = date_part[0..4].parse().ok()?;
    let month: u32 = date_part[4..6].parse().ok()?;
    let day: u32 = date_part[6..8].parse().ok()?;

    let hour: u32 = time_part[0..2].parse().ok()?;
    let minute: u32 = time_part[2..4].parse().ok()?;
    let second: u32 = time_part[4..6].parse().ok()?;

    Utc.with_ymd_and_hms(year, month, day, hour, minute, second)
        .single()
}

/// Extract repository name from sources path
/// Example: "de-legislation/country:us/state:de/..." -> "de-legislation"
fn extract_repo_name(entry: &Value) -> String {
    if let Some(sources) = entry.get("sources").and_then(|s| s.as_object()) {
        // Try log source first
        if let Some(log_source) = sources.get("log").and_then(|s| s.as_str()) {
            if let Some(first_slash) = log_source.find('/') {
                return log_source[..first_slash].to_string();
            }
            return log_source.to_string();
        }
        // Fall back to bill source
        if let Some(bill_source) = sources.get("bill").and_then(|s| s.as_str()) {
            if let Some(first_slash) = bill_source.find('/') {
                return bill_source[..first_slash].to_string();
            }
            return bill_source.to_string();
        }
    }
    "unknown".to_string()
}

/// Extract tag name(s) from entry
/// Returns the first tag, or comma-separated list if multiple
fn extract_tag_name(entry: &Value) -> String {
    if let Some(tags) = entry.get("tags").and_then(|t| t.as_object()) {
        let tag_names: Vec<String> = tags.keys().cloned().collect();
        if !tag_names.is_empty() {
            return tag_names.join(", ");
        }
    }
    "untagged".to_string()
}

/// Extract title from log entry
/// Format: {tag} - {repo} - {title}
pub fn extract_title(entry: &Value) -> String {
    let tag = extract_tag_name(entry);
    let repo = extract_repo_name(entry);

    // Try bill title first
    let title = if let Some(bill) = entry.get("bill").and_then(|b| b.as_object()) {
        if let Some(bill_title) = bill.get("title").and_then(|t| t.as_str()) {
            let trimmed = bill_title.trim();
            if !trimmed.is_empty() {
                trimmed.to_string()
            } else {
                // Fall back to bill identifier
                entry
                    .get("id")
                    .or_else(|| entry.get("log").and_then(|l| l.get("bill_id")))
                    .and_then(|id| id.as_str())
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| "Legislative Update".to_string())
            }
        } else {
            // Fall back to bill identifier
            entry
                .get("id")
                .or_else(|| entry.get("log").and_then(|l| l.get("bill_id")))
                .and_then(|id| id.as_str())
                .map(|s| s.to_string())
                .unwrap_or_else(|| "Legislative Update".to_string())
        }
    } else {
        // Fall back to bill identifier
        entry
            .get("id")
            .or_else(|| entry.get("log").and_then(|l| l.get("bill_id")))
            .and_then(|id| id.as_str())
            .map(|s| s.to_string())
            .unwrap_or_else(|| "Legislative Update".to_string())
    };

    format!("{} - {} - {}", tag, repo, title)
}

/// Format a JSON value as a readable string (for simple types)
fn format_json_value(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Null => "null".to_string(),
        Value::Array(arr) => arr
            .iter()
            .map(|v| format_json_value(v))
            .collect::<Vec<_>>()
            .join(", "),
        Value::Object(_) => "[object]".to_string(),
    }
}

/// Extract description from log entry
/// Formats the JSON structure similar to the terminal output, with log.action as primary
pub fn extract_description(entry: &Value) -> String {
    let mut parts = Vec::new();

    // Primary: log.action (most prominent)
    if let Some(log) = entry.get("log") {
        let mut log_parts = Vec::new();

        if let Some(action) = log.get("action") {
            let mut action_parts = Vec::new();

            // Action description (required, most prominent)
            if let Some(desc) = action.get("description").and_then(|d| d.as_str()) {
                action_parts.push(format!("description: {}", desc));
            }

            // Action date
            if let Some(date) = action.get("date").and_then(|d| d.as_str()) {
                action_parts.push(format!("date: {}", date));
            }

            // Action classification (if array)
            if let Some(classification) = action.get("classification") {
                if let Some(class_arr) = classification.as_array() {
                    if !class_arr.is_empty() {
                        let classes: Vec<String> = class_arr
                            .iter()
                            .filter_map(|v| v.as_str())
                            .map(|s| s.to_string())
                            .collect();
                        if !classes.is_empty() {
                            action_parts.push(format!(
                                "classification:\n      - {}",
                                classes.join("\n      - ")
                            ));
                        }
                    }
                }
            }

            // Organization ID
            if let Some(org_id) = action.get("organization_id").and_then(|o| o.as_str()) {
                action_parts.push(format!("organization_id: {}", org_id));
            }

            if !action_parts.is_empty() {
                log_parts.push(format!("  action:\n    {}", action_parts.join("\n    ")));
            }
        }

        // bill_id from log (at same level as action)
        if let Some(bill_id) = log.get("bill_id").and_then(|b| b.as_str()) {
            log_parts.push(format!("  bill_id: {}", bill_id));
        }

        if !log_parts.is_empty() {
            parts.push(format!("log:\n{}", log_parts.join("\n")));
        }
    }

    // Bill information
    if let Some(bill) = entry.get("bill") {
        let mut bill_parts = Vec::new();

        if let Some(identifier) = bill.get("identifier").and_then(|i| i.as_str()) {
            bill_parts.push(format!("identifier: {}", identifier));
        }

        if let Some(title) = bill.get("title").and_then(|t| t.as_str()) {
            bill_parts.push(format!("title: {}", title));
        }

        if let Some(session) = bill.get("legislative_session") {
            let session_str = format_json_value(session);
            bill_parts.push(format!("legislative_session: {}", session_str));
        }

        if let Some(subject) = bill.get("subject") {
            if let Some(subj_arr) = subject.as_array() {
                if !subj_arr.is_empty() {
                    let subjects: Vec<String> = subj_arr
                        .iter()
                        .filter_map(|v| v.as_str())
                        .map(|s| s.to_string())
                        .collect();
                    if !subjects.is_empty() {
                        bill_parts.push(format!("subject:\n    - {}", subjects.join("\n    - ")));
                    }
                }
            }
        }

        if let Some(abstracts) = bill.get("abstracts") {
            if let Some(abs_arr) = abstracts.as_array() {
                for abs in abs_arr {
                    if let Some(abs_obj) = abs.as_object() {
                        if let Some(abstract_text) =
                            abs_obj.get("abstract").and_then(|a| a.as_str())
                        {
                            let note = abs_obj.get("note").and_then(|n| n.as_str()).unwrap_or("");
                            if !note.is_empty() {
                                bill_parts.push(format!("abstract ({}): {}", note, abstract_text));
                            } else {
                                bill_parts.push(format!("abstract: {}", abstract_text));
                            }
                        }
                    }
                }
            }
        }

        if !bill_parts.is_empty() {
            parts.push(format!("bill:\n  {}", bill_parts.join("\n  ")));
        }
    }

    // Bill ID (top level)
    if let Some(bill_id) = entry.get("id").and_then(|i| i.as_str()) {
        parts.insert(0, format!("id: {}", bill_id));
    }

    if parts.is_empty() {
        "Legislative update".to_string()
    } else {
        parts.join("\n\n")
    }
}

/// Extract or construct link from log entry
pub fn extract_link(entry: &Value, base_url: Option<&str>) -> Option<String> {
    // Try to get source URL from bill metadata
    if let Some(sources) = entry.get("sources").and_then(|s| s.as_object()) {
        if let Some(bill_source) = sources.get("bill").and_then(|s| s.as_str()) {
            if let Some(base) = base_url {
                let base_trimmed = base.trim_end_matches('/');
                return Some(format!("{}/{}", base_trimmed, bill_source));
            }
        }
    }

    // Try to get URL from bill sources
    if let Some(bill_sources) = entry
        .get("bill")
        .and_then(|b| b.get("sources"))
        .and_then(|s| s.as_array())
    {
        if let Some(first_source) = bill_sources.first().and_then(|s| s.as_object()) {
            if let Some(url) = first_source.get("url").and_then(|u| u.as_str()) {
                return Some(url.to_string());
            }
        }
    }

    None
}

/// Extract or generate a unique GUID for the entry
pub fn extract_guid(entry: &Value) -> String {
    // Use source log path as GUID if available
    if let Some(sources) = entry.get("sources").and_then(|s| s.as_object()) {
        if let Some(log_source) = sources.get("log").and_then(|s| s.as_str()) {
            return log_source.to_string();
        }
    }

    // Fall back to timestamp + bill_id
    let timestamp = entry
        .get("timestamp")
        .and_then(|t| t.as_str())
        .unwrap_or("");
    let bill_id = entry
        .get("id")
        .or_else(|| entry.get("log").and_then(|l| l.get("bill_id")))
        .and_then(|id| id.as_str())
        .unwrap_or("");

    format!("{}_{}", timestamp, bill_id)
}

/// Convert JSON Lines entries to RSS feed
pub fn json_to_rss(
    entries: Vec<Value>,
    title: &str,
    description: &str,
    link: &str,
    base_url: Option<&str>,
    language: &str,
) -> String {
    let base_url = base_url.unwrap_or(link);

    let mut items = Vec::new();
    let mut seen_guids = HashSet::new();

    for entry in entries {
        let guid = extract_guid(&entry);

        // Deduplicate by GUID
        if seen_guids.contains(&guid) {
            continue;
        }
        seen_guids.insert(guid.clone());

        let mut item_builder = ItemBuilder::default();

        // Set title
        item_builder.title(extract_title(&entry));

        // Set description
        item_builder.description(extract_description(&entry));

        // Set link
        if let Some(item_link) = extract_link(&entry, Some(base_url)) {
            item_builder.link(item_link);
        }

        // Set publication date
        if let Some(timestamp) = entry.get("timestamp").and_then(|t| t.as_str()) {
            if let Some(pub_date) = parse_timestamp(timestamp) {
                item_builder.pub_date(pub_date.to_rfc2822());
            }
        }

        // Set GUID
        item_builder.guid(rss::Guid {
            value: guid,
            permalink: false,
        });

        // Only add categories from entry tags (not all feed tags)
        // Each entry should only show tags that are actually on that entry
        if let Some(tags) = entry.get("tags").and_then(|t| t.as_object()) {
            for tag_name in tags.keys() {
                item_builder.category(rss::Category {
                    name: tag_name.clone(),
                    domain: None,
                });
            }
        }

        items.push(item_builder.build());
    }

    // Build channel
    let channel = ChannelBuilder::default()
        .title(title)
        .link(link)
        .description(description)
        .language(Some(language.to_string()))
        .last_build_date(Some(Utc::now().to_rfc2822()))
        .items(items)
        .build();

    channel.to_string()
}

/// Format date and time for HTML display
fn format_datetime_html(dt: &DateTime<Utc>) -> String {
    dt.format("%B %d, %Y at %I:%M %p UTC").to_string()
}

/// Escape HTML special characters
fn escape_html(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

/// Convert description text to HTML with formatted JSON-like structure
/// Keys are bold, values are normal, with proper indentation
fn description_to_html(desc: &str) -> String {
    let mut html = String::new();
    let lines: Vec<&str> = desc.lines().collect();
    let mut in_list = false;
    let mut prev_indent = 0;

    for (i, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            // Close list if we hit an empty line
            if in_list {
                html.push_str("</ul>");
                in_list = false;
            }
            continue;
        }

        // Determine indentation level (count leading spaces)
        let indent_level = line.chars().take_while(|c| *c == ' ').count();
        let indent_em = (indent_level as f32) / 2.0; // 2 spaces = 1em

        // Close list if indentation decreased significantly
        if in_list && indent_level < prev_indent {
            html.push_str("</ul>");
            in_list = false;
        }
        prev_indent = indent_level;

        // Check if this is a list item (starts with "- ")
        if trimmed.starts_with("- ") {
            if !in_list {
                html.push_str(&format!(
                    "<ul class=\"json-list\" style=\"margin-left: {}em; margin-top: 0.25em;\">",
                    indent_em
                ));
                in_list = true;
            }
            let list_value = &trimmed[2..];
            html.push_str(&format!(
                "<li style=\"margin-bottom: 0.25em;\">{}</li>",
                escape_html(list_value)
            ));
            continue;
        }

        // Check if this is a key-value pair (key: value)
        if let Some(colon_pos) = trimmed.find(':') {
            let key = trimmed[..colon_pos].trim();
            let value = trimmed[colon_pos + 1..].trim();

            // Check if this is a section header (key: with no value and next line is indented)
            let is_section = value.is_empty() && i + 1 < lines.len() && {
                let next_line = lines[i + 1];
                let next_indent = next_line.chars().take_while(|c| *c == ' ').count();
                next_indent > indent_level
            };

            if is_section {
                // Section header (like "log:", "bill:")
                html.push_str(&format!(
                    "<div class=\"json-section\" style=\"margin-left: {}em; margin-top: 0.75em;\"><strong class=\"json-key\">{}</strong>:</div>",
                    indent_em, escape_html(key)
                ));
            } else {
                // Regular key-value pair
                html.push_str(&format!(
                    "<div class=\"json-line\" style=\"margin-left: {}em; margin-top: 0.25em;\"><strong class=\"json-key\">{}</strong>: <span class=\"json-value\">{}</span></div>",
                    indent_em, escape_html(key), escape_html(value)
                ));
            }
        } else {
            // No colon, treat as plain text
            html.push_str(&format!(
                "<div class=\"json-line\" style=\"margin-left: {}em; margin-top: 0.25em;\">{}</div>",
                indent_em, escape_html(trimmed)
            ));
        }
    }

    // Close any open list
    if in_list {
        html.push_str("</ul>");
    }

    if html.is_empty() {
        "<p>Legislative update</p>".to_string()
    } else {
        format!("<div class=\"json-content\">{}</div>", html)
    }
}

/// Convert JSON Lines entries to HTML index page
/// title: If None or empty, header will not be shown
pub fn json_to_html(
    entries: Vec<Value>,
    title: Option<&str>,
    link: &str,
    base_url: Option<&str>,
) -> String {
    let base_url = base_url.unwrap_or(link);
    let rss_link = format!("{}/feed.xml", base_url.trim_end_matches('/'));

    // Only show header if title is provided
    let show_header = title.is_some() && !title.unwrap_or("").trim().is_empty();
    let title_str = title.unwrap_or("");

    let mut items_html = String::new();
    let mut seen_guids = HashSet::new();

    for entry in entries {
        let guid = extract_guid(&entry);

        // Deduplicate by GUID
        if seen_guids.contains(&guid) {
            continue;
        }
        seen_guids.insert(guid);

        let entry_title = extract_title(&entry);
        let entry_description = extract_description(&entry);
        let entry_link = extract_link(&entry, Some(base_url));

        // Format date
        let date_html = if let Some(timestamp) = entry.get("timestamp").and_then(|t| t.as_str()) {
            if let Some(pub_date) = parse_timestamp(timestamp) {
                format_datetime_html(&pub_date)
            } else {
                String::new()
            }
        } else {
            String::new()
        };

        // Get tags - only from the entry itself (not all feed tags)
        let mut tags = Vec::new();
        if let Some(entry_tags) = entry.get("tags").and_then(|t| t.as_object()) {
            for tag_name in entry_tags.keys() {
                tags.push(tag_name.clone());
            }
        }

        let tags_html = if tags.is_empty() {
            String::new()
        } else {
            let tag_badges: Vec<String> = tags
                .iter()
                .map(|tag| format!("<span class=\"tag\">{}</span>", escape_html(tag)))
                .collect();
            format!("<div class=\"tags\">{}</div>", tag_badges.join(" "))
        };

        let link_html = if let Some(url) = entry_link {
            format!("<a href=\"{}\" class=\"entry-link\" target=\"_blank\" rel=\"noopener\">Read more →</a>", escape_html(&url))
        } else {
            String::new()
        };

        items_html.push_str(&format!(
            r#"      <article class="entry">
        <header class="entry-header">
          <h2 class="entry-title">{}</h2>
          {}
        </header>
        <div class="entry-content">
          {}
          {}
        </div>
        <footer class="entry-footer">
          <time class="entry-date" datetime="{}">{}</time>
          {}
        </footer>
      </article>
"#,
            escape_html(&entry_title),
            tags_html,
            description_to_html(&entry_description),
            link_html,
            entry
                .get("timestamp")
                .and_then(|t| t.as_str())
                .unwrap_or(""),
            date_html,
            if !date_html.is_empty() { "" } else { "" }
        ));
    }

    format!(
        r#"<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{}</title>
  <link rel="alternate" type="application/rss+xml" title="{}" href="{}">
  <style>
    * {{
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }}
    
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      background: #fafafa;
      padding: 0;
    }}
    
    .container {{
      max-width: 900px;
      margin: 0 auto;
      padding: 2rem 1rem;
    }}
    
    header {{
      background: linear-gradient(rgb(255, 29, 135) 0px, rgb(255, 82, 37) 600px, rgb(238, 145, 126) 1000px, rgba(0, 0, 0, 0.1) 1500px);
      color: white;
      padding: 3rem 0;
      margin-bottom: 2rem;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }}
    
    header .container {{
      padding: 0 1rem;
    }}
    
    h1 {{
      font-size: 2.5rem;
      font-weight: 700;
      margin-bottom: 0.5rem;
      letter-spacing: -0.02em;
    }}
    
    .subtitle {{
      font-size: 1.1rem;
      opacity: 0.95;
      font-weight: 400;
    }}
    
    .rss-link {{
      display: inline-block;
      margin-top: 1rem;
      color: white;
      text-decoration: none;
      padding: 0.5rem 1rem;
      background: rgba(255,255,255,0.2);
      border-radius: 4px;
      font-size: 0.9rem;
      transition: background 0.2s;
    }}
    
    .rss-link:hover {{
      background: rgba(255,255,255,0.3);
    }}
    
    .entries {{
      display: flex;
      flex-direction: column;
      gap: 2rem;
    }}
    
    .entry {{
      border-radius: 8px;
      padding: 2rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      transition: box-shadow 0.2s, transform 0.2s;
    }}
    
    .entry:hover {{
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      transform: translateY(-2px);
    }}
    
    .entry-header {{
      margin-bottom: 1rem;
      padding: 1rem 0;
      box-shadow: none;
      background: none;
    }}
    
    .entry-title {{
      font-size: 1.5rem;
      font-weight: 600;
      color: #1a1a1a;
      margin-bottom: 0.75rem;
      line-height: 1.3;
    }}
    
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 0.5rem;
    }}
    
    .tag {{
      display: inline-block;
      padding: 0.25rem 0.75rem;
      background: #f0f0f0;
      color: #666;
      border-radius: 12px;
      font-size: 0.85rem;
      font-weight: 500;
    }}
    
    .entry-content {{
      margin-bottom: 1rem;
    }}
    
    .entry-content p {{
      margin-bottom: 1rem;
      color: #555;
    }}
    
    .entry-content p:last-child {{
      margin-bottom: 0;
    }}
    
    .json-content {{
      font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'source-code-pro', monospace;
      font-size: 0.9rem;
      line-height: 1.6;
      background: #f8f9fa;
      padding: 1rem;
      border-radius: 4px;
      margin: 1rem 0;
      overflow-x: auto;
    }}
    
    .json-key {{
      font-weight: 600;
      color: #667eea;
    }}
    
    .json-value {{
      color: #333;
    }}
    
    .json-section {{
      font-weight: 600;
      color: #764ba2;
      margin-top: 0.75em;
    }}
    
    .json-line {{
      white-space: pre-wrap;
      word-wrap: break-word;
    }}
    
    .json-list {{
      list-style-type: disc;
      padding-left: 1.5em;
    }}
    
    .json-list li {{
      color: #555;
    }}
    
    .entry-link {{
      display: inline-block;
      color: #667eea;
      text-decoration: none;
      font-weight: 500;
      margin-top: 0.5rem;
      transition: color 0.2s;
    }}
    
    .entry-link:hover {{
      color: #764ba2;
      text-decoration: underline;
    }}
    
    .entry-footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 1rem;
      border-top: 1px solid #eee;
      margin-top: 1rem;
    }}
    
    .entry-date {{
      color: #888;
      font-size: 0.9rem;
    }}
    
    footer {{
      text-align: center;
      padding: 2rem 0;
      color: #888;
      font-size: 0.9rem;
    }}
    
    @media (max-width: 768px) {{
      h1 {{
        font-size: 2rem;
      }}
      
      .container {{
        padding: 1rem;
      }}
      
      .entry {{
        padding: 1.5rem;
      }}
      
      .entry-title {{
        font-size: 1.25rem;
      }}
    }}
  </style>
</head>
<body>
{}
  <main class="container">
    <div class="entries">
{}
    </div>
  </main>
  
  <footer>
    <div class="container">
      <p>Generated by Govbot • Last updated: {}</p>
    </div>
  </footer>
</body>
</html>"#,
        escape_html(title_str), // <title> tag
        escape_html(title_str), // RSS link title
        escape_html(&rss_link), // RSS link href
        if show_header {
            format!(
                r#"  <header>
    <div class="container">
      <h1>{}</h1>
      <a href="{}" class="rss-link">Subscribe via RSS</a>
    </div>
  </header>
  
"#,
                escape_html(title_str),
                escape_html(&rss_link)
            )
        } else {
            String::new()
        },
        items_html,
        Utc::now().format("%B %d, %Y at %I:%M %p UTC")
    )
}
