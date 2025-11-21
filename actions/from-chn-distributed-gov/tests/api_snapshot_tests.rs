use from_chn_distributed_gov::prelude::*;
use futures::StreamExt;

use insta;

/// Snapshot test for the pipeline processor
/// 
/// This test processes log files and compares the output against stored snapshots.
/// To update snapshots after making changes, run:
///   cargo insta review
#[tokio::test]
async fn test_pipeline_processor_snapshot() {
    // Use the same test data directory as the example
    let git_dir = "tmp/git/windy-civi-pipelines";
    
    // Build configuration matching the render-snapshots.sh script
    let config = ConfigBuilder::new(git_dir)
        .sort_order_str("DESC")
        .unwrap()
        .limit(100)
        .join_options_str("minimal_metadata")
        .unwrap()
        .build();
    
    // Skip test if git_dir doesn't exist (e.g., in CI without test data)
    let config = match config {
        Ok(c) => c,
        Err(_) => {
            eprintln!("Skipping snapshot test: test data directory not found");
            return;
        }
    };

    // Create processor
    let processor = PipelineProcessor::new(config);

    // Collect all entries from the stream
    let mut stream = processor.process();
    let mut entries = Vec::new();
    
    while let Some(result) = stream.next().await {
        match result {
            Ok(entry) => entries.push(entry),
            Err(e) => {
                eprintln!("Error processing entry: {}", e);
                // Continue processing other entries
            }
        }
    }

    // Serialize to JSON for snapshot comparison
    let json_output = serde_json::to_string_pretty(&entries)
        .expect("Failed to serialize entries to JSON");

    // Use insta's assert_snapshot! macro for string comparison
    // The snapshot will be stored in tests/snapshots/api_snapshot_tests__test_pipeline_processor_snapshot.snap
    insta::assert_snapshot!("pipeline_output", json_output);
}

/// Snapshot test for a single log entry structure
#[tokio::test]
async fn test_log_entry_structure() {
    use from_chn_distributed_gov::types::{LogContent, LogEntry, VoteEventResult};
    use from_chn_distributed_gov::types::MinimalMetadata;

    // Create a sample log entry
    let entry = LogEntry {
        log: LogContent::VoteEvent {
            result: VoteEventResult::Pass,
        },
        filename: "test/path/to/logs/20240101T120000Z_vote_event.pass.json".to_string(),
        minimal_metadata: Some(MinimalMetadata {
            title: Some("Test Bill Title".to_string()),
            description: Some("A test bill description".to_string()),
            sources: None,
        }),
        sponsors: None,
    };

    // Use assert_json_snapshot! for structured data
    insta::assert_json_snapshot!("log_entry_structure", &entry);
}

/// Snapshot test for vote event processing
#[tokio::test]
async fn test_vote_event_processing() {
    use from_chn_distributed_gov::types::VoteEventResult;

    let results = vec![
        VoteEventResult::Pass,
        VoteEventResult::Fail,
        VoteEventResult::Unknown,
    ];

    // Test vote event result serialization
    insta::assert_json_snapshot!("vote_event_results", &results);
}

