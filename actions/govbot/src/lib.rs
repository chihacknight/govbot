//! A type-safe, functional reactive library for processing pipeline log files.
//!
//! This library provides a reactive stream-based API for discovering, filtering,
//! sorting, and processing JSON log files from pipeline repositories.

pub mod bluesky;
pub mod cache;
pub mod config;
pub mod embeddings;
pub mod error;
pub mod filter;
pub mod git;
pub mod lock;
pub mod pipeline;
pub mod processor;
pub mod publish;
pub mod registry;
pub mod rss;
pub mod selectors;
pub mod types;
pub mod wizard;

pub use config::{
    Command_, Config, ConfigBuilder, JoinOption, Manifest, Publisher, PublisherKind, SortOrder,
    Transform,
};
pub use embeddings::{
    hash_text, BillTagResult, ScoreBreakdown, TagDefinition, TagFile, TagFileMetadata,
};
pub use error::{Error, Result};
pub use filter::{FilterAlias, FilterManager, FilterResult, LogFilter};
pub use lock::LockFile;
pub use processor::PipelineProcessor;
pub use registry::{DatasetEntry, Registry, ResolvedDataset};
pub use types::{LogContent, LogEntry, Metadata, VoteEventResult};

/// Re-export commonly used types for convenience
pub mod prelude {
    pub use crate::config::{Config, ConfigBuilder, JoinOption, SortOrder};
    pub use crate::error::{Error, Result};
    pub use crate::processor::PipelineProcessor;
    pub use crate::registry::Registry;
    pub use crate::types::{LogContent, LogEntry, Metadata, VoteEventResult};
    pub use futures::StreamExt;
}
