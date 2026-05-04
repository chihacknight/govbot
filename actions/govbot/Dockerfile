# syntax=docker/dockerfile:1

# ── Stage 1: Build ────────────────────────────────────────────────
FROM docker.io/library/rust:1-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    libgit2-dev \
    libonnx-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/govbot

# Copy dependency manifests first (layer caching)
COPY Cargo.toml Cargo.lock ./

# Fetch dependencies (populates Cargo cache)
RUN cargo fetch

# Copy full source
COPY . .

# Build release binary
RUN cargo build --release --bin govbot

# ── Stage 2: Runtime ─────────────────────────────────────────────
# Use trixie-slim to match the glibc version in rust:1-slim (builder)
FROM docker.io/library/debian:trixie-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/govbot

COPY --from=builder \
    /home/govbot/target/release/govbot \
    /usr/local/bin/govbot

ENTRYPOINT ["govbot"]