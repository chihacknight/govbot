use thiserror::Error;

/// Result type alias for the library
pub type Result<T> = std::result::Result<T, Error>;

/// Error types for the library
#[derive(Error, Debug)]
pub enum Error {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON parsing error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("Regex error: {0}")]
    Regex(#[from] regex::Error),

    #[error("Invalid configuration: {0}")]
    Config(String),

    #[error("File path error: {0}")]
    Path(String),

    #[error("Metadata file not found: {0}")]
    MetadataNotFound(String),

    #[error("Invalid timestamp format: {0}")]
    InvalidTimestamp(String),

    #[error("Git error: {0}")]
    Git(#[from] git2::Error),
}
