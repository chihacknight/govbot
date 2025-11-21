//! A type-safe, functional reactive library for processing pipeline log files.
//!
//! This library provides a reactive stream-based API for discovering, filtering,
//! sorting, and processing JSON log files from pipeline repositories.

pub mod config;
pub mod error;
pub mod processor;
pub mod types;

pub use config::{Config, ConfigBuilder, JoinOption, SortOrder};
pub use error::{Error, Result};
pub use processor::PipelineProcessor;
pub use types::{LogContent, LogEntry, Metadata, VoteEventResult};

/// Re-export commonly used types for convenience
pub mod prelude {
    pub use crate::config::{Config, ConfigBuilder, JoinOption, SortOrder};
    pub use crate::error::{Error, Result};
    pub use crate::processor::PipelineProcessor;
    pub use crate::types::{LogContent, LogEntry, Metadata, VoteEventResult};
    pub use futures::StreamExt;
}
