//! Open Civic Data identifier vocabulary.
//!
//! `govbot query` speaks OCD, because the data already does: every `metadata.json`
//! carries `jurisdiction: {id, name, classification, division_id}` with values like
//! `ocd-jurisdiction/country:us/state:il/government`.
//!
//! There is one wrinkle worth knowing before reading this module. The *path* layout
//! and the *OCD* vocabulary disagree about the federal government. On disk, federal
//! bills live under `country:us/state:usa/` so that downstream tooling needs no
//! special-casing. But the OCD jurisdiction id inside those same files is
//! `ocd-jurisdiction/country:us/government` — no `state:` segment at all, because
//! Congress is not a state. This module is the only place that discrepancy lives.

use std::fmt;

/// A jurisdiction, resolved from whatever the caller typed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Jurisdiction {
    /// govbot's locale code: `il`, `wy`, `usa`.
    pub locale: String,
}

impl Jurisdiction {
    pub fn new(locale: impl Into<String>) -> Self {
        Self {
            locale: locale.into().to_lowercase(),
        }
    }

    /// The `state:` path segment for this jurisdiction. Federal is `usa`.
    pub fn path_segment(&self) -> &str {
        &self.locale
    }

    /// The canonical OCD jurisdiction id.
    pub fn ocd_jurisdiction_id(&self) -> String {
        if self.is_federal() {
            "ocd-jurisdiction/country:us/government".to_string()
        } else {
            format!(
                "ocd-jurisdiction/country:us/state:{}/government",
                self.locale
            )
        }
    }

    /// The canonical OCD division id.
    pub fn ocd_division_id(&self) -> String {
        if self.is_federal() {
            "ocd-division/country:us".to_string()
        } else {
            format!("ocd-division/country:us/state:{}", self.locale)
        }
    }

    pub fn is_federal(&self) -> bool {
        self.locale == "usa"
    }

    /// The git repository name this jurisdiction is cloned into.
    pub fn repo_name(&self) -> String {
        format!("{}-legislation", self.locale)
    }
}

impl fmt::Display for Jurisdiction {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.locale)
    }
}

/// A legislative district, expressed as an OCD division.
///
/// `ocd-division/country:us/state:il/sldl:4`  — Illinois House district 4
/// `ocd-division/country:us/state:il/sldu:2`  — Illinois Senate district 2
/// `ocd-division/country:us/state:il/cd:7`    — US House, Illinois 7th
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct District {
    pub jurisdiction: Jurisdiction,
    /// `sldl`, `sldu`, or `cd`.
    pub kind: DistrictKind,
    pub number: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DistrictKind {
    /// State legislative district, lower chamber.
    StateLower,
    /// State legislative district, upper chamber.
    StateUpper,
    /// Congressional district.
    Congressional,
}

impl DistrictKind {
    pub fn as_ocd_prefix(&self) -> &'static str {
        match self {
            DistrictKind::StateLower => "sldl",
            DistrictKind::StateUpper => "sldu",
            DistrictKind::Congressional => "cd",
        }
    }

    /// The chamber classification used in vote events and `from_organization`.
    pub fn chamber(&self) -> &'static str {
        match self {
            DistrictKind::StateLower | DistrictKind::Congressional => "lower",
            DistrictKind::StateUpper => "upper",
        }
    }

    fn from_ocd_prefix(prefix: &str) -> Option<Self> {
        match prefix {
            "sldl" => Some(DistrictKind::StateLower),
            "sldu" => Some(DistrictKind::StateUpper),
            "cd" => Some(DistrictKind::Congressional),
            _ => None,
        }
    }
}

impl District {
    pub fn ocd_division_id(&self) -> String {
        format!(
            "{}/{}:{}",
            self.jurisdiction.ocd_division_id(),
            self.kind.as_ocd_prefix(),
            self.number
        )
    }
}

/// Parse a jurisdiction from any of the forms a caller might reasonably use:
/// a bare locale (`il`), an OCD jurisdiction id, or an OCD division id.
///
/// Returns `None` for input that names no jurisdiction we can act on.
pub fn parse_jurisdiction(input: &str) -> Option<Jurisdiction> {
    let raw = input.trim();
    if raw.is_empty() {
        return None;
    }
    let lowered = raw.to_lowercase();

    if let Some(rest) = lowered.strip_prefix("ocd-jurisdiction/") {
        return jurisdiction_from_division_path(rest.trim_end_matches("/government"));
    }
    if let Some(rest) = lowered.strip_prefix("ocd-division/") {
        return jurisdiction_from_division_path(rest);
    }

    // A bare locale code.
    if lowered.chars().all(|c| c.is_ascii_alphabetic()) && lowered.len() <= 3 {
        return Some(Jurisdiction::new(lowered));
    }
    None
}

/// Shared tail of both OCD id forms: `country:us[/state:xx][/sldl:4]`.
fn jurisdiction_from_division_path(path: &str) -> Option<Jurisdiction> {
    if !path.starts_with("country:us") {
        return None;
    }
    for segment in path.split('/') {
        if let Some(state) = segment.strip_prefix("state:") {
            if state.is_empty() {
                return None;
            }
            return Some(Jurisdiction::new(state));
        }
    }
    // `country:us` with no `state:` segment is the federal government, which on
    // disk lives under `state:usa`.
    Some(Jurisdiction::new("usa"))
}

/// Parse a district from an OCD division id.
///
/// A division id without a district segment is a jurisdiction, not a district, and
/// yields `None` — callers that accept either should try [`parse_jurisdiction`] too.
pub fn parse_district(input: &str) -> Option<District> {
    let lowered = input.trim().to_lowercase();
    let rest = lowered.strip_prefix("ocd-division/")?;
    let jurisdiction = jurisdiction_from_division_path(rest)?;

    let last = rest.rsplit('/').next()?;
    let (prefix, number) = last.split_once(':')?;
    let kind = DistrictKind::from_ocd_prefix(prefix)?;
    if number.is_empty() {
        return None;
    }

    Some(District {
        jurisdiction,
        kind,
        number: number.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_bare_locale() {
        assert_eq!(parse_jurisdiction("il").unwrap().locale, "il");
        assert_eq!(parse_jurisdiction("IL").unwrap().locale, "il");
        assert_eq!(parse_jurisdiction("usa").unwrap().locale, "usa");
    }

    #[test]
    fn parses_state_jurisdiction_id() {
        let j = parse_jurisdiction("ocd-jurisdiction/country:us/state:il/government").unwrap();
        assert_eq!(j.locale, "il");
        assert_eq!(
            j.ocd_jurisdiction_id(),
            "ocd-jurisdiction/country:us/state:il/government"
        );
    }

    /// The federal special case, in both directions. On disk it is `state:usa`;
    /// in OCD it has no `state:` segment at all.
    #[test]
    fn federal_round_trips_between_path_and_ocd() {
        let j = parse_jurisdiction("ocd-jurisdiction/country:us/government").unwrap();
        assert_eq!(j.locale, "usa");
        assert!(j.is_federal());
        assert_eq!(j.path_segment(), "usa");
        assert_eq!(j.ocd_jurisdiction_id(), "ocd-jurisdiction/country:us/government");
        assert_eq!(j.ocd_division_id(), "ocd-division/country:us");

        // And the bare locale reaches the same place.
        assert_eq!(parse_jurisdiction("usa").unwrap(), j);
    }

    #[test]
    fn parses_division_ids() {
        assert_eq!(
            parse_jurisdiction("ocd-division/country:us/state:wy")
                .unwrap()
                .locale,
            "wy"
        );
        assert_eq!(
            parse_jurisdiction("ocd-division/country:us/state:il/sldl:4")
                .unwrap()
                .locale,
            "il"
        );
    }

    #[test]
    fn parses_districts() {
        let d = parse_district("ocd-division/country:us/state:il/sldl:4").unwrap();
        assert_eq!(d.jurisdiction.locale, "il");
        assert_eq!(d.kind, DistrictKind::StateLower);
        assert_eq!(d.kind.chamber(), "lower");
        assert_eq!(d.number, "4");
        assert_eq!(d.ocd_division_id(), "ocd-division/country:us/state:il/sldl:4");

        let s = parse_district("ocd-division/country:us/state:il/sldu:2").unwrap();
        assert_eq!(s.kind, DistrictKind::StateUpper);
        assert_eq!(s.kind.chamber(), "upper");

        let c = parse_district("ocd-division/country:us/state:il/cd:7").unwrap();
        assert_eq!(c.kind, DistrictKind::Congressional);
        assert_eq!(c.jurisdiction.locale, "il");
    }

    #[test]
    fn rejects_non_districts_and_junk() {
        assert!(parse_district("ocd-division/country:us/state:il").is_none());
        assert!(parse_jurisdiction("").is_none());
        assert!(parse_jurisdiction("ocd-division/country:ca/province:on").is_none());
        assert!(parse_jurisdiction("some arbitrary sentence").is_none());
    }
}
