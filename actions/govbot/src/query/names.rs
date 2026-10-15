//! Matching a caller-supplied legislator name against the names that appear in the
//! data, and being honest about how sure we are.
//!
//! govbot has no legislator roster. Sponsors and voters are name strings, and
//! `person_id` is pseudo-JSON derived from the name itself (`~{"name": "Filer"}`),
//! so it carries no identity the name doesn't already carry. Everything here works
//! from the names in the corpus alone.
//!
//! Formats vary by jurisdiction, and all of these are real:
//!
//! | jurisdiction | what a vote row says |
//! |---|---|
//! | usa    | `Kelly (PA)`, `Kelly (D-AZ)`, `Arrington`, with the member id in `note` |
//! | co, oh | `Max Brooks`, `Roy Klopfenstein` |
//! | il, sc | `Cunningham, Bill`, `Adams, Brian` |
//! | ga     | `ADESANYA`, with the district in `note` |
//! | wy     | `Brown` — bare surname, and see [`is_suspect_fragment`] |
//!
//! The rule that matters: **a refusal is a success.** Attributing a vote to the
//! wrong legislator is far worse than saying we can't tell. So surname collisions
//! resolve to [`MatchMethod::Ambiguous`] with the candidates listed, never to a
//! guess, and edit distance is never used to assign a person — `Hanson`/`Hansen`
//! and `Reed`/`Reid` are one edit apart and are different people.

use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// How a name was matched. Ordering is not meaningful; use [`Confidence`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MatchMethod {
    /// A stable external id agreed: the bioguide in a federal vote row's `note`.
    Bioguide,
    /// Full name matched exactly after normalization.
    ExactName,
    /// `Adams, Brian` matched `Brian Adams`.
    ReversedName,
    /// Surname matched exactly one distinct person in scope.
    UniqueSurname,
    /// Surname plus a given-name initial selected exactly one person.
    SurnameInitial,
    /// A bare-surname spelling (`Cunningham`) linked to the one full-named person
    /// (`Cunningham, Bill`) who shares that surname in the same jurisdiction,
    /// chamber and session. See [`NameIndex::surname_links`].
    SurnameOnlySpelling,
    /// Surname matched more than one person and nothing disambiguated them.
    Ambiguous,
    /// The name is a committee or other body, not a person.
    Organization,
    /// No candidate at all.
    Unmatched,
}

/// How much a match should be trusted. `query --min-confidence` gates on this.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Confidence {
    /// Nothing was matched, or the match was ambiguous.
    None,
    /// A surname plus a weak signal.
    Medium,
    /// A full-name agreement.
    High,
    /// A stable external identifier agreed.
    Exact,
}

impl Confidence {
    pub fn parse(input: &str) -> Option<Self> {
        match input.trim().to_lowercase().as_str() {
            "any" | "none" => Some(Confidence::None),
            "medium" => Some(Confidence::Medium),
            "high" => Some(Confidence::High),
            "exact" => Some(Confidence::Exact),
            _ => None,
        }
    }
}

impl MatchMethod {
    pub fn confidence(&self) -> Confidence {
        match self {
            MatchMethod::Bioguide => Confidence::Exact,
            MatchMethod::ExactName | MatchMethod::ReversedName => Confidence::High,
            MatchMethod::UniqueSurname
            | MatchMethod::SurnameInitial
            | MatchMethod::SurnameOnlySpelling => Confidence::Medium,
            MatchMethod::Ambiguous | MatchMethod::Organization | MatchMethod::Unmatched => {
                Confidence::None
            }
        }
    }
}

/// The outcome of resolving one caller-supplied name against the corpus.
#[derive(Debug, Clone, Serialize)]
pub struct NameMatch {
    pub method: MatchMethod,
    pub confidence: Confidence,
    /// The raw corpus names this resolved to. Exactly one unless `method` is
    /// [`MatchMethod::Ambiguous`], in which case it lists what the caller must
    /// choose between.
    pub candidates: Vec<String>,
    /// Other spellings of the same person, linked only by surname, and so trusted
    /// at [`MatchMethod::SurnameOnlySpelling`]'s confidence rather than this
    /// match's. Illinois floor votes say `Cunningham` where its committee votes
    /// say `Cunningham, Bill`; without this, a full-name query silently loses the
    /// floor record. Use [`Self::confidence_for`] to gate a row on these.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub surname_only_spellings: Vec<String>,
    /// For each of `surname_only_spellings`, the scopes the link holds in. The
    /// same bare `Peters` is Robert Peters in the Illinois Senate and someone
    /// else in Congress, so a row only counts when its own scope is listed here.
    #[serde(skip)]
    pub surname_only_scopes: BTreeMap<String, BTreeSet<String>>,
    /// Bare spellings of this person's surname that appear alongside them (same
    /// scope) but could not be linked there — two full-named people with that
    /// surname, or a source hint. Their rows are left out; callers should say so.
    #[serde(skip)]
    pub unlinked_surname_only_spellings: Vec<String>,
    /// The member ids (see [`member_id`]) of the person matched. A row that
    /// carries a member id belongs to them only if it is one of these, whatever
    /// its name says: `Grijalva` is two members of Congress. Empty outside
    /// Congress, and for an ambiguous match.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub member_ids: Vec<String>,
}

impl NameMatch {
    fn unmatched() -> Self {
        Self {
            method: MatchMethod::Unmatched,
            confidence: Confidence::None,
            candidates: Vec::new(),
            surname_only_spellings: Vec::new(),
            surname_only_scopes: BTreeMap::new(),
            unlinked_surname_only_spellings: Vec::new(),
            member_ids: Vec::new(),
        }
    }

    #[cfg(test)]
    fn resolved(method: MatchMethod, name: String) -> Self {
        Self::resolved_many(method, vec![name])
    }

    fn resolved_person(method: MatchMethod, person: Person) -> Self {
        let mut matched = Self::resolved_many(method, person.spellings);
        matched.member_ids = person.member_ids;
        matched
    }

    /// One person, spelled several ways in the data. Every spelling is carried so a
    /// caller filtering on `candidates` catches all of that person's rows.
    fn resolved_many(method: MatchMethod, spellings: Vec<String>) -> Self {
        Self {
            method,
            confidence: method.confidence(),
            candidates: spellings,
            surname_only_spellings: Vec::new(),
            surname_only_scopes: BTreeMap::new(),
            unlinked_surname_only_spellings: Vec::new(),
            member_ids: Vec::new(),
        }
    }

    fn ambiguous(candidates: Vec<String>) -> Self {
        Self {
            method: MatchMethod::Ambiguous,
            confidence: Confidence::None,
            candidates,
            surname_only_spellings: Vec::new(),
            surname_only_scopes: BTreeMap::new(),
            unlinked_surname_only_spellings: Vec::new(),
            member_ids: Vec::new(),
        }
    }

    /// Whether this match may be used to attribute a bill or vote to a person.
    pub fn is_attributable(&self, minimum: Confidence) -> bool {
        self.confidence >= minimum && self.confidence > Confidence::None
    }

    /// How far a row naming `raw`, cast in `scope`, may be attributed to this
    /// person: the match's own confidence for one of its candidates, Medium for a
    /// surname-only spelling linked in that scope, `None` for anything else —
    /// including a surname-only spelling from a row whose scope is unknown.
    pub fn confidence_for(&self, raw: &str, scope: Option<&str>) -> Option<Confidence> {
        if self.candidates.iter().any(|c| c == raw) {
            return Some(self.confidence);
        }
        let linked_here = scope.is_some_and(|scope| {
            self.surname_only_scopes
                .get(raw)
                .is_some_and(|scopes| scopes.contains(scope))
        });
        linked_here.then(|| MatchMethod::SurnameOnlySpelling.confidence())
    }

    /// [`Self::confidence_for`] for a whole vote row. A row carrying a member id
    /// counts only if the id is this person's, so a Congress row is never given
    /// to someone else because the name happens to agree.
    pub fn confidence_for_row(&self, row: &RawVoteRow, scope: Option<&str>) -> Option<Confidence> {
        if let Some(id) = member_id(&row.note) {
            if !self.member_ids.contains(&id) {
                return None;
            }
        }
        self.confidence_for(&row.voter_name, scope)
    }

    /// The match as it applies to one row naming `raw`, so a row reached through
    /// a surname-only spelling reports that, at medium confidence, instead of
    /// inheriting the full-name match's.
    pub fn for_spelling(&self, raw: &str) -> NameMatch {
        let mut row_match = self.clone();
        if !self.candidates.iter().any(|c| c == raw)
            && self.surname_only_spellings.iter().any(|c| c == raw)
        {
            row_match.method = MatchMethod::SurnameOnlySpelling;
            row_match.confidence = MatchMethod::SurnameOnlySpelling.confidence();
        }
        row_match
    }
}

/// One result of [`NameIndex::surname_links`]: within one scope, one person known
/// by a full name, and the bare-surname spellings that may be read as them there.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SurnameLink {
    /// The scope the link holds in, e.g. `il|upper|104th`.
    pub scope: String,
    /// The full-named person's normalized key, e.g. `bill cunningham`.
    pub person_key: String,
    /// The full-named person's raw spellings seen in this scope.
    pub person_spellings: Vec<String>,
    /// The bare-surname raw spellings seen in this scope, e.g. `Cunningham`.
    pub bare_spellings: Vec<String>,
}

/// Fold the accented Latin characters that actually occur in US legislator names
/// down to ASCII, so `Ortíz` and `Ortiz` compare equal.
///
/// This is a table rather than full Unicode NFKD because the input domain is
/// names in US legislative data — Latin-1 and Latin Extended-A cover it, and a
/// table keeps this dependency-free and obvious. Characters outside the table
/// pass through unchanged, so a name we don't fold simply fails to match rather
/// than matching something wrong.
fn fold_accents(input: &str) -> String {
    input
        .chars()
        .map(|c| match c {
            'á' | 'à' | 'â' | 'ä' | 'ã' | 'å' | 'ā' | 'ă' | 'ą' => 'a',
            'é' | 'è' | 'ê' | 'ë' | 'ē' | 'ĕ' | 'ė' | 'ę' | 'ě' => 'e',
            'í' | 'ì' | 'î' | 'ï' | 'ī' | 'ĭ' | 'į' | 'ı' => 'i',
            'ó' | 'ò' | 'ô' | 'ö' | 'õ' | 'ø' | 'ō' | 'ŏ' | 'ő' => 'o',
            'ú' | 'ù' | 'û' | 'ü' | 'ū' | 'ŭ' | 'ů' | 'ű' | 'ų' => 'u',
            'ñ' | 'ń' | 'ņ' | 'ň' => 'n',
            'ç' | 'ć' | 'ĉ' | 'ċ' | 'č' => 'c',
            'ý' | 'ÿ' => 'y',
            'š' | 'ś' | 'ş' => 's',
            'ž' | 'ź' | 'ż' => 'z',
            'ł' => 'l',
            'ř' | 'ŕ' => 'r',
            'ť' | 'ţ' => 't',
            'ď' => 'd',
            'ğ' => 'g',
            other => other,
        })
        .collect()
}

/// Titles that appear in front of names in some sources and carry no identity.
const HONORIFICS: &[&str] = &[
    "sen", "senator", "rep", "representative", "del", "delegate", "assemblymember",
    "assemblyman", "assemblywoman", "mr", "mrs", "ms", "dr", "hon", "speaker",
    "president", "chairman", "chairwoman", "chair",
];

/// Generational suffixes, which vary between sources for the same person.
const SUFFIXES: &[&str] = &["jr", "sr", "ii", "iii", "iv", "v"];

/// A name reduced to comparable parts.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NormalizedName {
    /// All meaningful tokens, in given-name-first order.
    pub tokens: Vec<String>,
    /// A parenthetical or trailing hint, e.g. the `NV` in `Amodei (NV)`.
    pub hint: Option<String>,
}

impl NormalizedName {
    /// The full name as a single comparable key.
    pub fn key(&self) -> String {
        self.tokens.join(" ")
    }

    /// The last token, which for US legislative data is the family name.
    pub fn surname(&self) -> Option<&str> {
        self.tokens.last().map(|s| s.as_str())
    }

    /// The first letter of the first given name, when there is one.
    pub fn given_initial(&self) -> Option<char> {
        if self.tokens.len() < 2 {
            return None;
        }
        self.tokens[0].chars().next()
    }

    pub fn is_empty(&self) -> bool {
        self.tokens.is_empty()
    }
}

/// The member id in a vote row's `note`, if the note is one.
///
/// Congress's roll calls carry a stable per-member id there: a bioguide id for
/// the House (`K000376`) and a Senate LIS id for the Senate (`S406`). Other
/// sources use `note` for other things (Georgia puts the district there), so
/// only those two shapes count as identity.
pub fn member_id(note: &str) -> Option<String> {
    let id = note.trim().to_uppercase();
    let bytes = id.as_bytes();
    let digits = |from: usize| bytes[from..].iter().all(u8::is_ascii_digit);
    let is_bioguide = bytes.len() == 7 && bytes[0].is_ascii_uppercase() && digits(1);
    let is_senate_lis = bytes.len() == 4 && bytes[0] == b'S' && digits(1);
    (is_bioguide || is_senate_lis).then_some(id)
}

/// The key that tells one person from another, for a spelling seen with
/// `member_id` (or without one).
///
/// - With a member id, the id decides: `Grijalva` seen with G000551 (Raúl) and
///   with G000606 (Adelita, who succeeded him) is two people, and one member
///   printed two ways would be one.
/// - Otherwise a source hint is part of identity. Congress prints `Kelly (IL)`,
///   `Kelly (PA)` and `Kelly (D-AZ)` for three different members; dropping the
///   hint would make them one person.
/// - Otherwise the normalized name, as before: `Smith, S` and `SMITH, S` are one.
///
/// Only a plain key ever contains a space for a full name, so the surname-link
/// code (which looks for full names) never links a hinted or id'd spelling.
pub fn identity_key(raw: &str, member_id: Option<&str>) -> String {
    let normalized = normalize(raw);
    match (member_id, &normalized.hint) {
        (Some(id), _) => format!("{}[{}]", normalized.key(), id),
        (None, Some(hint)) => format!("{}({})", normalized.key(), hint),
        (None, None) => normalized.key(),
    }
}

/// Take a member id out of a query, so `Grijalva [G000606]` (the form an
/// ambiguous match lists) or `Mike Kelly K000376` resolves by the id.
fn split_member_id(query: &str) -> (String, Option<String>) {
    let mut id = None;
    let rest: Vec<&str> = query
        .split_whitespace()
        .filter(|token| {
            let bare = token.trim_matches(|c: char| "[](),".contains(c));
            match member_id(bare) {
                Some(found) if id.is_none() => {
                    id = Some(found);
                    false
                }
                _ => true,
            }
        })
        .collect();
    (rest.join(" "), id)
}

/// Whether a person's source hint is compatible with the hint a caller wrote.
/// `pa` matches `pa`, and also `r-pa`, since a caller gives a state, not a party.
fn hint_matches(person_hint: &str, query_hint: &str) -> bool {
    person_hint == query_hint
        || (!query_hint.contains('-')
            && person_hint.rsplit_once('-').is_some_and(|(_, state)| state == query_hint))
}

/// One person found in the data: every spelling they appear under, and the
/// member ids their rows carry (Congress only).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Person {
    pub spellings: Vec<String>,
    pub member_ids: Vec<String>,
}

/// Reduce a raw name to comparable tokens.
///
/// Handles the `Family, Given` form by reordering, captures and removes
/// parenthetical disambiguators, and drops honorifics and generational suffixes.
pub fn normalize(raw: &str) -> NormalizedName {
    let folded = fold_accents(&raw.to_lowercase());

    // Capture a parenthetical hint: `Amodei (NV)` -> hint `nv`.
    let (body, hint) = match (folded.find('('), folded.find(')')) {
        (Some(open), Some(close)) if close > open + 1 => {
            let hint = folded[open + 1..close].trim().to_string();
            let mut body = String::with_capacity(folded.len());
            body.push_str(&folded[..open]);
            body.push_str(&folded[close + 1..]);
            (body, Some(hint))
        }
        _ => (folded, None),
    };

    // `Family, Given Middle` -> `Given Middle Family`. Only the first comma is
    // structural; anything after it (`Smith, John, Jr.`) is handled by suffix
    // stripping below.
    let reordered = match body.split_once(',') {
        Some((family, rest)) if !rest.trim().is_empty() => {
            format!("{} {}", rest.trim(), family.trim())
        }
        _ => body,
    };

    let tokens: Vec<String> = reordered
        .split(|c: char| !c.is_alphanumeric() && c != '\'' && c != '-')
        .map(|t| t.trim_matches(|c: char| c == '\'' || c == '-'))
        .filter(|t| !t.is_empty())
        .filter(|t| !HONORIFICS.contains(t))
        .filter(|t| !SUFFIXES.contains(t))
        .map(|t| t.to_string())
        .collect();

    NormalizedName { tokens, hint }
}

/// Whether a raw voter name looks like debris from an upstream parsing bug rather
/// than a person.
///
/// Wyoming's vote rows are the known case: `"Brown, L."` was split on the comma
/// into two separate voters, so `"L"` appears as a voter 768 times, alongside
/// `"G"`, `"K"`, `"E"`, and `"JT"`. Counting those as legislators invents people
/// and double-counts real ones. See [`repair_split_rows`] for the recovery.
pub fn is_suspect_fragment(raw: &str) -> bool {
    let trimmed = raw.trim().trim_end_matches('.');
    !trimmed.is_empty() && trimmed.len() <= 2 && trimmed.chars().all(|c| c.is_alphabetic())
}

/// One row of a roll call, as it appears in the data.
#[derive(Debug, Clone)]
pub struct RawVoteRow {
    pub voter_name: String,
    pub option: String,
    pub note: String,
}

/// Rejoin vote rows that an upstream parser split on a comma.
///
/// In Wyoming's data the severed initial always follows its surname and carries
/// the same vote option:
///
/// ```text
/// [0] 'Brown'    -> yes      [37] 'Brown'    -> no
/// [1] 'L'        -> yes      [38] 'G'        -> no
/// [2] 'Campbell' -> yes      [39] 'Campbell' -> no
/// [3] 'E'        -> yes      [40] 'K'        -> no
/// ```
///
/// Rejoining them turns `Brown` + `L` back into `Brown, L.`, which is what
/// separates Landon Brown from Gary Brown — the only thing that makes Wyoming's
/// two colliding surnames attributable at all.
///
/// The repair is deliberately conservative: it fires only when the *preceding*
/// row is a plausible surname and the options agree, because at least one stray
/// `L` appears in the data with no `Brown` before it.
pub fn repair_split_rows(rows: Vec<RawVoteRow>) -> (Vec<RawVoteRow>, usize) {
    let mut repaired: Vec<RawVoteRow> = Vec::with_capacity(rows.len());
    let mut repairs = 0usize;
    let mut index = 0usize;

    while index < rows.len() {
        let current = &rows[index];
        let next = rows.get(index + 1);

        let is_rejoinable = match next {
            Some(next) => {
                is_suspect_fragment(&next.voter_name)
                    && !is_suspect_fragment(&current.voter_name)
                    && next.option == current.option
            }
            None => false,
        };

        if is_rejoinable {
            let next = next.expect("checked above");
            repaired.push(RawVoteRow {
                voter_name: format!(
                    "{}, {}",
                    current.voter_name.trim(),
                    next.voter_name.trim().trim_end_matches('.')
                ),
                option: current.option.clone(),
                note: current.note.clone(),
            });
            repairs += 1;
            index += 2;
        } else {
            repaired.push(current.clone());
            index += 1;
        }
    }

    (repaired, repairs)
}

/// The distinct names present in some scope, and the lookups needed to resolve a
/// caller's name against them.
///
/// "Scope" is the caller's business — build one per jurisdiction, or per
/// jurisdiction and chamber. Narrower scope means fewer surname collisions.
#[derive(Debug, Default)]
pub struct NameIndex {
    by_full_key: HashMap<String, BTreeSet<String>>,
    by_surname: HashMap<String, BTreeSet<String>>,
    by_bioguide: HashMap<String, BTreeSet<String>>,
    /// The member ids each spelling's vote rows carried (see [`member_id`]).
    member_ids: HashMap<String, BTreeSet<String>>,
    /// Spellings seen at least once without a member id. Congress's `Peters`
    /// (Scott Peters, P000608) and the Illinois Senate's `Peters` are the same
    /// string, and only the Congress rows carry an id.
    unidentified: BTreeSet<String>,
    /// Where each raw spelling appears, as opaque caller-chosen scope keys (the
    /// query layer uses `jurisdiction|chamber|session`). Only names recorded with
    /// [`Self::insert_in_scope`] have any; [`Self::surname_link`] needs them.
    scopes: HashMap<String, BTreeSet<String>>,
    suspect_fragments: BTreeSet<String>,
    all: BTreeSet<String>,
}

impl NameIndex {
    pub fn new() -> Self {
        Self::default()
    }

    /// Record a name that appears in the data, with no member id.
    pub fn insert(&mut self, raw: &str) {
        if self.record(raw) {
            self.unidentified.insert(raw.trim().to_string());
        }
    }

    /// Record one vote row's name, where it was cast (if known), and its `note`,
    /// which for Congress is the member id that decides who the row belongs to.
    pub fn insert_vote(&mut self, raw: &str, scope: Option<&str>, note: &str) {
        let trimmed = raw.trim();
        if !self.record(trimmed) {
            return;
        }
        match member_id(note) {
            Some(id) => {
                self.member_ids
                    .entry(trimmed.to_string())
                    .or_default()
                    .insert(id.clone());
                self.by_bioguide
                    .entry(id)
                    .or_default()
                    .insert(trimmed.to_string());
            }
            None => {
                self.unidentified.insert(trimmed.to_string());
            }
        }
        if let Some(scope) = scope {
            self.scopes
                .entry(trimmed.to_string())
                .or_default()
                .insert(scope.to_string());
        }
    }

    /// The lookups behind [`Self::insert`]. False when the name was skipped
    /// (empty, or a suspect fragment).
    fn record(&mut self, raw: &str) -> bool {
        let raw = raw.trim();
        if raw.is_empty() {
            return false;
        }
        if is_suspect_fragment(raw) {
            self.suspect_fragments.insert(raw.to_string());
            return false;
        }

        let normalized = normalize(raw);
        if normalized.is_empty() {
            return false;
        }

        self.all.insert(raw.to_string());
        self.by_full_key
            .entry(normalized.key())
            .or_default()
            .insert(raw.to_string());
        if let Some(surname) = normalized.surname() {
            self.by_surname
                .entry(surname.to_string())
                .or_default()
                .insert(raw.to_string());
        }
        true
    }

    /// Record a name together with where it appears, with no member id. The
    /// scope is opaque here; two spellings share a scope when the caller passes
    /// equal strings.
    pub fn insert_in_scope(&mut self, raw: &str, scope: &str) {
        self.insert_vote(raw, Some(scope), "");
    }

    /// Where the bare-surname spellings of `surname` can be read as the one
    /// person who appears with that surname and a full name, decided scope by
    /// scope.
    ///
    /// Illinois is the case this exists for: floor roll calls print `Cunningham`,
    /// committee roll calls print `Cunningham, Bill`, and they are the same
    /// senator. But a bare surname is exactly where two people collide, so for
    /// each scope (the query layer uses `jurisdiction|chamber|session`) a bare
    /// spelling appears in, the link is made there only when, counting only the
    /// spellings recorded in that same scope:
    ///
    /// - exactly one full-named person (two or more tokens) has this surname.
    ///   Two — Wyoming's `Brown, G` and `Brown, L` in one chamber — and nothing
    ///   is linked there. None — a bare `Cunningham` in a chamber, session or
    ///   state where no full-named Cunningham appears — and nothing is linked;
    /// - no bare spelling carries a parenthetical hint. `Peters (D-MI)` has been
    ///   disambiguated by its source in a way this rule can't check.
    ///
    /// Deciding per scope is what keeps one jurisdiction from breaking another's
    /// links: Congress's `Peters` and `Peters (D-MI)` say nothing about whether
    /// the Illinois Senate's `Peters` is `Peters, Robert`. Names recorded without
    /// a scope (sponsors, or votes whose chamber is unknown) never take part.
    ///
    /// The residual risk, accepted because Illinois floor votes are otherwise
    /// lost: a legislator who only ever appears as a bare surname in a scope
    /// where one other, full-named legislator shares it would be linked to them.
    pub fn surname_links(&self, surname: &str) -> Vec<SurnameLink> {
        let Some(spellings) = self.by_surname.get(surname) else {
            return Vec::new();
        };
        let is_bare = |raw: &String| normalize(raw).tokens.len() == 1;
        let bare_scopes: BTreeSet<&String> = spellings
            .iter()
            .filter(|raw| is_bare(raw))
            .filter_map(|raw| self.scopes.get(raw))
            .flatten()
            .collect();

        let mut links = Vec::new();
        for scope in bare_scopes {
            let in_scope = |raw: &&String| {
                self.scopes
                    .get(*raw)
                    .is_some_and(|scopes| scopes.contains(scope))
            };
            let bare: Vec<String> = spellings
                .iter()
                .filter(in_scope)
                .filter(|raw| is_bare(raw))
                .cloned()
                .collect();
            if bare.iter().any(|raw| normalize(raw).hint.is_some()) {
                continue;
            }
            let full: BTreeSet<String> = spellings
                .iter()
                .filter(in_scope)
                .filter(|raw| !is_bare(raw))
                .cloned()
                .collect();
            let mut people = self.group_by_person(&full);
            if people.len() != 1 {
                continue;
            }
            let (person_key, person) = people.pop_first().expect("checked above");
            links.push(SurnameLink {
                scope: scope.clone(),
                person_key,
                person_spellings: person.spellings,
                bare_spellings: bare,
            });
        }
        links
    }

    /// Add the other side of the [`SurnameLink`]s for the person `key` names: the
    /// bare spellings for a full-named person, or the full-named person for a
    /// bare-surname query. Each is recorded with the scopes it holds in.
    ///
    /// A bare query is only extended when every scope links it to the same
    /// person; Illinois's bare `Johnson` is Gregg in the House and Adriane in the
    /// Senate, and adding both to a query for "Johnson" would mix two people.
    fn with_surname_link(&self, mut matched: NameMatch, key: &str) -> NameMatch {
        let Some(surname) = key.split(' ').next_back() else {
            return matched;
        };
        let links = self.surname_links(surname);

        let mut linked: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
        if key.contains(' ') {
            for link in links.iter().filter(|link| link.person_key == key) {
                for raw in &link.bare_spellings {
                    linked.entry(raw.clone()).or_default().insert(link.scope.clone());
                }
            }
            matched.unlinked_surname_only_spellings =
                self.unlinked_bare_spellings(surname, &matched.candidates, &linked);
        } else {
            let people: BTreeSet<&String> = links.iter().map(|link| &link.person_key).collect();
            if people.len() == 1 {
                for link in &links {
                    for raw in &link.person_spellings {
                        linked.entry(raw.clone()).or_default().insert(link.scope.clone());
                    }
                }
            }
        }

        matched.surname_only_spellings = linked.keys().cloned().collect();
        matched.surname_only_scopes = linked;
        matched
    }

    /// Bare spellings of `surname` recorded in a scope where one of `person`'s
    /// spellings also appears, but which `linked` does not cover there.
    fn unlinked_bare_spellings(
        &self,
        surname: &str,
        person: &[String],
        linked: &BTreeMap<String, BTreeSet<String>>,
    ) -> Vec<String> {
        let person_scopes: BTreeSet<&String> = person
            .iter()
            .filter_map(|raw| self.scopes.get(raw))
            .flatten()
            .collect();
        let Some(spellings) = self.by_surname.get(surname) else {
            return Vec::new();
        };
        spellings
            .iter()
            .filter(|raw| normalize(raw).tokens.len() == 1)
            .filter(|raw| {
                self.scopes.get(*raw).is_some_and(|scopes| {
                    scopes.iter().any(|scope| {
                        person_scopes.contains(scope)
                            && !linked.get(*raw).is_some_and(|l| l.contains(scope))
                    })
                })
            })
            .cloned()
            .collect()
    }

    /// Record a stable external identifier for a name, so a caller who has the id
    /// can look the name up. The sponsor index uses this for bill bioguides. It
    /// does not decide who is who; vote rows do that through [`Self::insert_vote`].
    pub fn insert_identifier(&mut self, identifier: &str, raw_name: &str) {
        let identifier = identifier.trim();
        if identifier.is_empty() {
            return;
        }
        // Replaces rather than adds, as it always has: the sponsor index calls this
        // for every bioguide on a bill, and only vote rows decide identity (see
        // [`Self::insert_vote`]).
        self.by_bioguide.insert(
            identifier.to_uppercase(),
            BTreeSet::from([raw_name.trim().to_string()]),
        );
    }

    /// Distinct people, counted after normalization.
    ///
    /// Prefer this over [`Self::distinct_raw_spellings`] for anything a reader will
    /// interpret as a headcount. Wyoming's data spells the same legislator both
    /// `Smith, S` and `SMITH, S`, so counting raw strings reports 184 voters for a
    /// 93-member legislature. Congress's `Kelly (IL)` and `Kelly (PA)` count as two,
    /// and so do the two members recorded as `Grijalva` (see [`identity_key`]).
    pub fn distinct_people(&self) -> usize {
        let people: BTreeSet<String> = self
            .all
            .iter()
            .flat_map(|raw| self.identity_keys(raw))
            .collect();
        people.len()
    }

    /// The identity key of each person `raw` is a spelling of: one per member id
    /// its rows carried, plus a plain key if it was also seen without one.
    fn identity_keys(&self, raw: &str) -> Vec<String> {
        let mut keys: Vec<String> = self
            .member_ids
            .get(raw)
            .into_iter()
            .flatten()
            .map(|id| identity_key(raw, Some(id)))
            .collect();
        if self.unidentified.contains(raw) || keys.is_empty() {
            keys.push(identity_key(raw, None));
        }
        keys
    }

    /// Group raw spellings by the person they belong to.
    ///
    /// This is what separates "one legislator written two ways" from "two
    /// legislators who share a surname"; the first is resolvable, the second
    /// must not be. A spelling seen under two member ids lands in both people.
    pub fn group_by_person(&self, names: &BTreeSet<String>) -> BTreeMap<String, Person> {
        let mut grouped: BTreeMap<String, Person> = BTreeMap::new();
        for name in names {
            for key in self.identity_keys(name) {
                let person = grouped.entry(key).or_insert_with(|| Person {
                    spellings: Vec::new(),
                    member_ids: Vec::new(),
                });
                if !person.spellings.contains(name) {
                    person.spellings.push(name.clone());
                }
            }
            for id in self.member_ids.get(name).into_iter().flatten() {
                let key = identity_key(name, Some(id));
                let person = grouped.get_mut(&key).expect("inserted above");
                if !person.member_ids.contains(id) {
                    person.member_ids.push(id.clone());
                }
            }
        }
        grouped
    }

    /// Distinct raw strings, before normalization. Useful for describing how noisy a
    /// jurisdiction's spelling is, not as a headcount.
    pub fn distinct_raw_spellings(&self) -> usize {
        self.all.len()
    }

    pub fn suspect_fragment_count(&self) -> usize {
        self.suspect_fragments.len()
    }

    pub fn names(&self) -> impl Iterator<Item = &String> {
        self.all.iter()
    }

    /// Resolve a caller-supplied name against the corpus.
    pub fn resolve(&self, query: &str) -> NameMatch {
        let query = query.trim();
        if query.is_empty() {
            return NameMatch::unmatched();
        }

        // A member id, if the caller has one, beats every heuristic. It may come
        // alone (`K000376`) or with the name an ambiguous match listed it under
        // (`Grijalva [G000606]`).
        let (rest, id) = split_member_id(query);
        if let Some(id) = id {
            let Some(spellings) = self.by_bioguide.get(&id) else {
                return NameMatch::unmatched();
            };
            // A name given with the id must agree with it: `Kelly [S380]` is a
            // mistake (S380 is Peters), not a request for Peters's votes.
            let named = normalize(&rest);
            if let Some(surname) = named.surname() {
                if !spellings.iter().any(|s| normalize(s).surname() == Some(surname)) {
                    return NameMatch::unmatched();
                }
            }
            return NameMatch::resolved_person(
                MatchMethod::Bioguide,
                Person {
                    spellings: to_vec(spellings),
                    member_ids: vec![id],
                },
            );
        }
        let query = rest.as_str();

        let normalized = normalize(query);
        if normalized.is_empty() {
            return NameMatch::unmatched();
        }
        let hint = normalized.hint.as_deref();

        // Full name, exactly as given. Several raw strings may share one normalized
        // key — `Smith, S` and `SMITH, S` are one legislator spelled two ways, not
        // two legislators — so every spelling of the person is returned. But the
        // same key can also be several people: Congress's `Kelly (IL)` and
        // `Kelly (PA)`, or the two members recorded as `Grijalva`. A hint in the
        // query (`Kelly (PA)`) narrows them; otherwise that is ambiguity.
        if let Some(matches) = self.by_full_key.get(&normalized.key()) {
            if let Some(found) = self.pick_person(matches, hint, MatchMethod::ExactName) {
                return found;
            }
        }

        // The caller wrote the name in the other order from the data, or the data
        // wrote it in the other order from the caller. `normalize` already
        // reorders an explicit `Family, Given`, so this covers the rest.
        if normalized.tokens.len() > 1 {
            let mut swapped = normalized.tokens.clone();
            let last = swapped.len() - 1;
            swapped.rotate_left(last);
            if let Some(matches) = self.by_full_key.get(&swapped.join(" ")) {
                if let Some(found) = self.pick_person(matches, hint, MatchMethod::ReversedName) {
                    return found;
                }
            }
        }

        // Surname only. This is where collisions live.
        let Some(surname) = normalized.surname() else {
            return NameMatch::unmatched();
        };
        let Some(surname_matches) = self.by_surname.get(surname) else {
            return NameMatch::unmatched();
        };

        let people = narrow_by_hint(self.group_by_person(surname_matches), hint);
        if people.is_empty() {
            // `Kelly (NY)` when no Kelly from New York is in the data.
            return NameMatch::unmatched();
        }
        if people.len() == 1 {
            let (key, person) = people.into_iter().next().expect("checked above");
            let matched = NameMatch::resolved_person(MatchMethod::UniqueSurname, person);
            return self.with_surname_link(matched, &key);
        }

        // Several distinct people share the surname. A given-name initial from the
        // caller may pick one out; anything less and we refuse. Congress's names
        // carry no given name (`Kelly (PA)`), so "Mike Kelly" never narrows here.
        if let Some(initial) = normalized.given_initial() {
            let narrowed: Vec<(&String, &Person)> = people
                .iter()
                .filter(|(_, person)| {
                    person.spellings.first().is_some_and(|name| {
                        normalize(name)
                            .given_initial()
                            .is_some_and(|c| c == initial)
                    })
                })
                .collect();
            if let [(key, person)] = narrowed.as_slice() {
                let matched =
                    NameMatch::resolved_person(MatchMethod::SurnameInitial, (*person).clone());
                // `Laura Murphy` reaches `Murphy, Laura M` here, not by exact
                // name, and her floor votes print `Murphy` all the same.
                return self.with_surname_link(matched, key);
            }
        }

        NameMatch::ambiguous(candidate_labels(people))
    }

    /// The one person among `matches` (narrowed by the caller's `hint`), linked
    /// to their surname-only spellings; ambiguity if several remain; `None` if
    /// the hint ruled them all out, so the caller can try the next rule.
    fn pick_person(
        &self,
        matches: &BTreeSet<String>,
        hint: Option<&str>,
        method: MatchMethod,
    ) -> Option<NameMatch> {
        let people = narrow_by_hint(self.group_by_person(matches), hint);
        match people.len() {
            0 => None,
            1 => {
                let (key, person) = people.into_iter().next().expect("checked above");
                Some(self.with_surname_link(NameMatch::resolved_person(method, person), &key))
            }
            _ => Some(NameMatch::ambiguous(candidate_labels(people))),
        }
    }
}

/// Keep the people whose source hint agrees with the caller's. People with an
/// exactly equal hint win over ones that only share the state, so `Kelly (IL)`
/// is never ambiguous with a senator printed `Kelly (D-IL)`. A person with no hint
/// can't be confirmed, so is dropped: `Kelly (NY)` must not fall through to some
/// other Kelly printed without one. With no caller hint, everyone is kept.
fn narrow_by_hint(
    people: BTreeMap<String, Person>,
    hint: Option<&str>,
) -> BTreeMap<String, Person> {
    let Some(hint) = hint else {
        return people;
    };
    let person_hint = |person: &Person| {
        person
            .spellings
            .iter()
            .find_map(|raw| normalize(raw).hint)
    };
    let exact: BTreeMap<String, Person> = people
        .iter()
        .filter(|(_, person)| person_hint(person).as_deref() == Some(hint))
        .map(|(key, person)| (key.clone(), person.clone()))
        .collect();
    if !exact.is_empty() {
        return exact;
    }
    people
        .into_iter()
        .filter(|(_, person)| {
            person_hint(person).is_some_and(|theirs| hint_matches(&theirs, hint))
        })
        .collect()
}

/// One label per person, so the caller is choosing between people rather than
/// between spellings, and each label resolves back to that one person. The
/// label is the person's first spelling, plus their member id when the
/// spelling alone wouldn't pick them out: another candidate has the same
/// spelling (`Grijalva [G000551]`, `Grijalva [G000606]`), or it has no hint to
/// narrow by (Congress's `Peters`, beside `Peters (D-MI)`).
fn candidate_labels(people: BTreeMap<String, Person>) -> Vec<String> {
    let firsts: Vec<(String, Option<String>)> = people
        .into_values()
        .filter_map(|person| {
            let first = person.spellings.into_iter().next()?;
            Some((first, person.member_ids.into_iter().next()))
        })
        .collect();
    let mut labels: Vec<String> = firsts
        .iter()
        .map(|(name, id)| {
            let shared = firsts.iter().filter(|(other, _)| other == name).count() > 1;
            let unhinted = normalize(name).hint.is_none();
            match id {
                Some(id) if shared || unhinted => format!("{name} [{id}]"),
                _ => name.clone(),
            }
        })
        .collect();
    labels.sort();
    labels
}

fn to_vec(set: &BTreeSet<String>) -> Vec<String> {
    set.iter().cloned().collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn index_of(names: &[&str]) -> NameIndex {
        let mut index = NameIndex::new();
        for name in names {
            index.insert(name);
        }
        index
    }

    #[test]
    fn folds_accents_so_ortiz_matches_ortiz() {
        assert_eq!(normalize("Ortíz, Aarón").key(), "aaron ortiz");
        assert_eq!(normalize("Aaron Ortiz").key(), "aaron ortiz");
        assert_eq!(normalize("González, Edgar").key(), "edgar gonzalez");
        assert_eq!(normalize("Guzmán, Graciela").key(), "graciela guzman");
    }

    #[test]
    fn reorders_family_given_form() {
        // Illinois and South Carolina publish names this way.
        assert_eq!(normalize("Cunningham, Bill").key(), "bill cunningham");
        assert_eq!(normalize("Adams, Brian").key(), "brian adams");
        assert_eq!(normalize("Alexander, Thomas C.").key(), "thomas c alexander");
    }

    #[test]
    fn captures_parenthetical_hints() {
        let n = normalize("Amodei (NV)");
        assert_eq!(n.key(), "amodei");
        assert_eq!(n.hint.as_deref(), Some("nv"));
    }

    #[test]
    fn strips_honorifics_and_suffixes() {
        assert_eq!(normalize("Sen. Bill Cunningham").key(), "bill cunningham");
        assert_eq!(normalize("Joseph A. Miller, III").key(), "joseph a miller");
    }

    #[test]
    fn matches_full_names_and_reversals() {
        let index = index_of(&["Cunningham, Bill", "Max Brooks"]);

        let m = index.resolve("Bill Cunningham");
        assert_eq!(m.method, MatchMethod::ExactName);
        assert_eq!(m.confidence, Confidence::High);
        assert_eq!(m.candidates, vec!["Cunningham, Bill"]);

        let m = index.resolve("Brooks, Max");
        assert_eq!(m.method, MatchMethod::ExactName);
    }

    #[test]
    fn unique_surname_resolves_but_collision_refuses() {
        // Wyoming publishes bare surnames, so the caller's surname matches the
        // data's full name outright.
        let index = index_of(&["Filer", "Geringer", "Love"]);
        let m = index.resolve("Filer");
        assert_eq!(m.method, MatchMethod::ExactName);

        // Where the data carries full names, a surname-only query falls to the
        // surname lookup and is only attributable because it is unique.
        let index = index_of(&["Bill Cunningham", "Robert Peters"]);
        let m = index.resolve("Cunningham");
        assert_eq!(m.method, MatchMethod::UniqueSurname);
        assert_eq!(m.confidence, Confidence::Medium);
        assert_eq!(m.candidates, vec!["Bill Cunningham"]);

        // Wyoming really does have two Browns and two Campbells.
        let index = index_of(&["Brown, G", "Brown, L", "Campbell, E", "Campbell, K"]);
        let m = index.resolve("Brown");
        assert_eq!(m.method, MatchMethod::Ambiguous);
        assert_eq!(m.confidence, Confidence::None);
        assert_eq!(m.candidates, vec!["Brown, G", "Brown, L"]);
        assert!(!m.is_attributable(Confidence::None));
    }

    #[test]
    fn given_initial_breaks_a_surname_collision() {
        let index = index_of(&["Brown, G", "Brown, L"]);
        let m = index.resolve("Brown, L");
        // An exact hit on the full key, since the data uses the same form.
        assert_eq!(m.method, MatchMethod::ExactName);

        let index = index_of(&["Gary Brown", "Landon Brown"]);
        let m = index.resolve("L Brown");
        assert_eq!(m.method, MatchMethod::SurnameInitial);
        assert_eq!(m.candidates, vec!["Landon Brown"]);
    }

    #[test]
    fn never_matches_a_near_miss() {
        // One edit apart, different people. This must not resolve.
        let index = index_of(&["Hanson", "Reed"]);
        assert_eq!(index.resolve("Hansen").method, MatchMethod::Unmatched);
        assert_eq!(index.resolve("Reid").method, MatchMethod::Unmatched);
    }

    #[test]
    fn bioguide_beats_everything() {
        let mut index = index_of(&["Arrington"]);
        index.insert_identifier("A000375", "Arrington");
        let m = index.resolve("a000375");
        assert_eq!(m.method, MatchMethod::Bioguide);
        assert_eq!(m.confidence, Confidence::Exact);
    }

    #[test]
    fn identifies_wyoming_split_fragments() {
        assert!(is_suspect_fragment("L"));
        assert!(is_suspect_fragment("JT"));
        assert!(is_suspect_fragment("E."));
        assert!(!is_suspect_fragment("Brown"));
        assert!(!is_suspect_fragment(""));
    }

    #[test]
    fn case_variants_are_one_person_not_two() {
        // Wyoming publishes both spellings for the same legislator.
        let index = index_of(&["Smith, S", "SMITH, S", "Brown, G", "BROWN, G"]);
        assert_eq!(index.distinct_people(), 2);
        assert_eq!(index.distinct_raw_spellings(), 4);

        // A query resolves to every spelling, so no votes are missed.
        let m = index.resolve("S Smith");
        assert_eq!(m.method, MatchMethod::ExactName);
        assert_eq!(m.candidates, vec!["SMITH, S", "Smith, S"]);
    }

    #[test]
    fn suspect_fragments_never_become_legislators() {
        let index = index_of(&["Brown", "L", "Campbell", "E"]);
        assert_eq!(index.distinct_people(), 2);
        assert_eq!(index.suspect_fragment_count(), 2);
        assert_eq!(index.resolve("L").method, MatchMethod::Unmatched);
    }

    #[test]
    fn rejoins_wyoming_split_vote_rows() {
        let rows = vec![
            row("Brown", "yes"),
            row("L", "yes"),
            row("Campbell", "yes"),
            row("E", "yes"),
            row("Chestek", "yes"),
        ];
        let (repaired, repairs) = repair_split_rows(rows);
        assert_eq!(repairs, 2);
        let names: Vec<&str> = repaired.iter().map(|r| r.voter_name.as_str()).collect();
        assert_eq!(names, vec!["Brown, L", "Campbell, E", "Chestek"]);
    }

    #[test]
    fn leaves_a_stray_fragment_alone() {
        // A fragment with no surname before it is not evidence of a split.
        let rows = vec![row("Chestek", "yes"), row("L", "no")];
        let (repaired, repairs) = repair_split_rows(rows);
        assert_eq!(repairs, 0);
        assert_eq!(repaired.len(), 2);
    }

    #[test]
    fn does_not_rejoin_across_differing_options() {
        let rows = vec![row("Brown", "yes"), row("L", "no")];
        let (repaired, repairs) = repair_split_rows(rows);
        assert_eq!(repairs, 0);
        assert_eq!(repaired.len(), 2);
    }

    #[test]
    fn confidence_ordering_gates_attribution() {
        assert!(Confidence::Exact > Confidence::High);
        assert!(Confidence::High > Confidence::Medium);
        assert!(Confidence::Medium > Confidence::None);

        let m = NameMatch::resolved(MatchMethod::UniqueSurname, "Filer".into());
        assert!(m.is_attributable(Confidence::Medium));
        assert!(!m.is_attributable(Confidence::High));
    }

    fn scoped_index_of(names: &[(&str, &str)]) -> NameIndex {
        let mut index = NameIndex::new();
        for (name, scope) in names {
            index.insert_in_scope(name, scope);
        }
        index
    }

    const IL_SENATE: &str = "il|upper|104th";
    const IL_HOUSE: &str = "il|lower|104th";

    #[test]
    fn full_name_query_includes_the_surname_only_floor_spelling() {
        // Illinois: committee roll calls say `Cunningham, Bill`, floor roll calls
        // say `Cunningham`. One senator.
        let index = scoped_index_of(&[
            ("Cunningham, Bill", IL_SENATE),
            ("Cunningham", IL_SENATE),
            ("Peters, Robert", IL_SENATE),
            ("Peters", IL_SENATE),
        ]);

        let m = index.resolve("Bill Cunningham");
        assert_eq!(m.method, MatchMethod::ExactName);
        assert_eq!(m.confidence, Confidence::High);
        assert_eq!(m.candidates, vec!["Cunningham, Bill"]);
        assert_eq!(m.surname_only_spellings, vec!["Cunningham"]);
        let senate = Some(IL_SENATE);
        assert_eq!(m.confidence_for("Cunningham, Bill", senate), Some(Confidence::High));
        assert_eq!(m.confidence_for("Cunningham", senate), Some(Confidence::Medium));
        assert_eq!(m.confidence_for("Peters", senate), None);
        // A row whose scope is unknown (no chamber) is never reached by the link.
        assert_eq!(m.confidence_for("Cunningham", None), None);

        let row = m.for_spelling("Cunningham");
        assert_eq!(row.method, MatchMethod::SurnameOnlySpelling);
        assert_eq!(row.confidence, Confidence::Medium);
        assert_eq!(m.for_spelling("Cunningham, Bill").method, MatchMethod::ExactName);

        // And the other way round: the bare surname pulls in the full name.
        let m = index.resolve("Cunningham");
        assert_eq!(m.method, MatchMethod::ExactName);
        assert_eq!(m.candidates, vec!["Cunningham"]);
        assert_eq!(m.surname_only_spellings, vec!["Cunningham, Bill"]);
        assert_eq!(m.confidence_for("Cunningham, Bill", senate), Some(Confidence::Medium));
    }

    #[test]
    fn two_full_named_people_keep_a_bare_surname_unlinked() {
        // Wyoming's two Browns: a bare `Brown` must not be given to either.
        let index = scoped_index_of(&[
            ("Brown", "wy|lower|2025"),
            ("Brown, G", "wy|lower|2025"),
            ("Brown, L", "wy|lower|2025"),
        ]);
        assert!(index.surname_links("brown").is_empty());
        let m = index.resolve("Brown, L");
        assert!(m.surname_only_spellings.is_empty());
        // ...and the caller is told those bare rows were left out.
        assert_eq!(m.unlinked_surname_only_spellings, vec!["Brown"]);
        assert!(index.resolve("Brown").surname_only_spellings.is_empty());
    }

    #[test]
    fn each_chamber_links_its_own_bare_surname() {
        // Illinois's floor votes print `Johnson` for both Gregg Johnson (House) and
        // Adriane Johnson (Senate). Each chamber has one full-named Johnson, so the
        // House `Johnson` is Gregg and the Senate `Johnson` is Adriane — never the
        // other way round.
        let index = scoped_index_of(&[
            ("Johnson", IL_HOUSE),
            ("Johnson", IL_SENATE),
            ("Johnson, Gregg", IL_HOUSE),
            ("Johnson, Adriane", IL_SENATE),
        ]);
        let m = index.resolve("Gregg Johnson");
        assert_eq!(m.candidates, vec!["Johnson, Gregg"]);
        assert_eq!(m.surname_only_spellings, vec!["Johnson"]);
        assert_eq!(m.confidence_for("Johnson", Some(IL_HOUSE)), Some(Confidence::Medium));
        assert_eq!(m.confidence_for("Johnson", Some(IL_SENATE)), None);
        assert!(m.unlinked_surname_only_spellings.is_empty());

        // A bare query is two people across the chambers, so it pulls in neither.
        assert!(index.resolve("Johnson").surname_only_spellings.is_empty());
    }

    #[test]
    fn a_bare_surname_outside_the_full_names_scope_is_not_linked() {
        // A House `Cunningham` is not assumed to be Senator Bill Cunningham.
        let index = scoped_index_of(&[("Cunningham, Bill", IL_SENATE), ("Cunningham", IL_HOUSE)]);
        assert!(index.surname_links("cunningham").is_empty());

        // Nor is one from a session he doesn't appear in, or another state — but
        // that doesn't undo the link in the scope he does share.
        for elsewhere in ["il|upper|103rd", "oh|upper|136"] {
            let index = scoped_index_of(&[
                ("Cunningham, Bill", IL_SENATE),
                ("Cunningham", IL_SENATE),
                ("Cunningham", elsewhere),
            ]);
            let m = index.resolve("Bill Cunningham");
            assert_eq!(m.confidence_for("Cunningham", Some(IL_SENATE)), Some(Confidence::Medium));
            assert_eq!(m.confidence_for("Cunningham", Some(elsewhere)), None);
        }
    }

    #[test]
    fn another_jurisdiction_does_not_break_a_link() {
        // Default scope is il + usa. Congress's bare `Peters` and hinted
        // `Peters (D-MI)` must neither block Illinois's link nor be swept into it.
        let index = scoped_index_of(&[
            ("Peters, Robert", IL_SENATE),
            ("Peters", IL_SENATE),
            ("Peters", "usa|lower|119"),
            ("Peters (D-MI)", "usa|upper|119"),
        ]);
        let m = index.resolve("Robert Peters");
        assert_eq!(m.surname_only_spellings, vec!["Peters"]);
        assert_eq!(m.confidence_for("Peters", Some(IL_SENATE)), Some(Confidence::Medium));
        assert_eq!(m.confidence_for("Peters", Some("usa|lower|119")), None);
        // Congress's Peters never shares a scope with him, so no caveat either.
        assert!(m.unlinked_surname_only_spellings.is_empty());
    }

    #[test]
    fn a_name_matched_by_surname_and_initial_still_gets_floor_votes() {
        // 36 of Illinois's linked legislators are stored with a middle initial,
        // nickname or suffix, so "Laura Murphy" is not an exact name.
        let index = scoped_index_of(&[("Murphy, Laura M", IL_SENATE), ("Murphy", IL_SENATE)]);
        let m = index.resolve("Laura Murphy");
        assert_eq!(m.method, MatchMethod::SurnameInitial);
        assert_eq!(m.confidence, Confidence::Medium);
        assert_eq!(m.surname_only_spellings, vec!["Murphy"], "method was {:?}", m.method);
        assert_eq!(m.confidence_for("Murphy", Some(IL_SENATE)), Some(Confidence::Medium));

        // A suffix normalizes away, so `Sims Jr., Elgie R` is reached the same way.
        let index = scoped_index_of(&[("Sims Jr., Elgie R", IL_SENATE), ("Sims", IL_SENATE)]);
        assert_eq!(index.resolve("Elgie Sims").surname_only_spellings, vec!["Sims"]);
    }

    #[test]
    fn names_without_scope_or_with_a_source_hint_never_link() {
        let index = index_of(&["Cunningham, Bill", "Cunningham"]);
        assert!(index.resolve("Bill Cunningham").surname_only_spellings.is_empty());

        let index = scoped_index_of(&[("Smith, Adrian", "usa|lower|119"), ("Smith (NJ)", "usa|lower|119")]);
        assert!(index.surname_links("smith").is_empty());
    }

    // ---- Congress: surname + state, with a member id in `note` ----------------

    const HOUSE_119: &str = "usa|lower|119";
    const SENATE_119: &str = "usa|upper|119";

    /// The 119th Congress's Kellys and Johnsons, as its roll calls print them.
    fn congress() -> NameIndex {
        let mut index = NameIndex::new();
        for (name, scope, id) in [
            ("Kelly (IL)", HOUSE_119, "K000385"),
            ("Kelly (MS)", HOUSE_119, "K000388"),
            ("Kelly (PA)", HOUSE_119, "K000376"),
            ("Kelly (D-AZ)", SENATE_119, "S406"),
            ("Johnson (GA)", HOUSE_119, "J000288"),
            ("Johnson (LA)", HOUSE_119, "J000299"),
            ("Johnson (SD)", HOUSE_119, "J000301"),
            ("Johnson (TX)", HOUSE_119, "J000310"),
            ("Johnson (R-WI)", SENATE_119, "S345"),
            ("Davis (IL)", HOUSE_119, "D000096"),
            ("Davis (NC)", HOUSE_119, "D000230"),
            ("Peters", HOUSE_119, "P000608"),
            ("Peters (D-MI)", SENATE_119, "S380"),
            // Raúl Grijalva, then Adelita Grijalva, who succeeded him.
            ("Grijalva", HOUSE_119, "G000551"),
            ("Grijalva", HOUSE_119, "G000606"),
        ] {
            index.insert_vote(name, Some(scope), id);
        }
        index
    }

    fn vote(name: &str, note: &str) -> RawVoteRow {
        RawVoteRow {
            voter_name: name.to_string(),
            option: "yes".to_string(),
            note: note.to_string(),
        }
    }

    #[test]
    fn only_congress_member_id_shapes_count() {
        assert_eq!(member_id("K000376").as_deref(), Some("K000376"));
        assert_eq!(member_id(" s406 ").as_deref(), Some("S406"));
        // Georgia puts the district in `note`; that is not who someone is.
        for note in ["", "12", "District 12", "HD012", "S40", "K00037"] {
            assert_eq!(member_id(note), None, "{note:?}");
        }
    }

    #[test]
    fn kelly_by_state_is_four_people() {
        let index = congress();
        let m = index.resolve("Kelly");
        assert_eq!(m.method, MatchMethod::Ambiguous);
        assert_eq!(
            m.candidates,
            vec!["Kelly (D-AZ)", "Kelly (IL)", "Kelly (MS)", "Kelly (PA)"]
        );

        // Congress prints no given names, so "Mike Kelly" can't pick one either.
        let m = index.resolve("Mike Kelly");
        assert_eq!(m.method, MatchMethod::Ambiguous);
        assert_eq!(m.candidates.len(), 4);
        assert!(!m.is_attributable(Confidence::None));
    }

    #[test]
    fn exact_hinted_name_resolves_one() {
        let index = congress();
        let m = index.resolve("Kelly (PA)");
        assert_eq!(m.method, MatchMethod::ExactName);
        assert_eq!(m.candidates, vec!["Kelly (PA)"]);
        assert_eq!(m.member_ids, vec!["K000376"]);

        // A state picks the senator out of a party-and-state hint.
        assert_eq!(index.resolve("Kelly (AZ)").candidates, vec!["Kelly (D-AZ)"]);
        // A full name plus a state narrows by the state, as a name match.
        let m = index.resolve("Mike Kelly (PA)");
        assert_eq!(m.method, MatchMethod::UniqueSurname);
        assert_eq!(m.candidates, vec!["Kelly (PA)"]);
        // A state with no such member is no match, never some other Kelly.
        assert_eq!(index.resolve("Kelly (NY)").method, MatchMethod::Unmatched);
    }

    #[test]
    fn the_speaker_never_gets_another_johnsons_votes() {
        let index = congress();
        let m = index.resolve("Mike Johnson");
        assert_eq!(m.method, MatchMethod::Ambiguous);
        assert!(m.candidates.contains(&"Johnson (LA)".to_string()));
        assert_eq!(m.candidates.len(), 5);

        let m = index.resolve("Johnson (LA)");
        assert_eq!(m.member_ids, vec!["J000299"]);
        let scope = Some(HOUSE_119);
        assert_eq!(
            m.confidence_for_row(&vote("Johnson (LA)", "J000299"), scope),
            Some(Confidence::High)
        );
        assert_eq!(m.confidence_for_row(&vote("Johnson (GA)", "J000288"), scope), None);
        assert_eq!(
            m.confidence_for_row(&vote("Johnson (R-WI)", "S345"), Some(SENATE_119)),
            None
        );

        let m = index.resolve("Don Davis");
        assert_eq!(m.method, MatchMethod::Ambiguous);
        assert_eq!(m.candidates, vec!["Davis (IL)", "Davis (NC)"]);
    }

    #[test]
    fn a_member_id_decides_identity_over_the_name() {
        let index = congress();
        // Two members printed `Grijalva`: ambiguous, and each label resolves back.
        let m = index.resolve("Grijalva");
        assert_eq!(m.method, MatchMethod::Ambiguous);
        assert_eq!(m.candidates, vec!["Grijalva [G000551]", "Grijalva [G000606]"]);

        let m = index.resolve("Grijalva [G000606]");
        assert_eq!(m.method, MatchMethod::Bioguide);
        assert_eq!(m.member_ids, vec!["G000606"]);
        assert!(m.confidence_for_row(&vote("Grijalva", "G000606"), None).is_some());
        // Same name, same scope, other member: never theirs.
        assert_eq!(m.confidence_for_row(&vote("Grijalva", "G000551"), Some(HOUSE_119)), None);

        // A name that disagrees with the id is a mistake, not a request.
        assert_eq!(index.resolve("Kelly [S380]").method, MatchMethod::Unmatched);

        // One member printed two ways is one person.
        let mut index = NameIndex::new();
        index.insert_vote("Kelly (IL)", Some(HOUSE_119), "K000385");
        index.insert_vote("Kelly (D-IL)", Some(HOUSE_119), "K000385");
        assert_eq!(index.distinct_people(), 1);
        let m = index.resolve("Kelly");
        assert_eq!(m.method, MatchMethod::ExactName);
        assert_eq!(m.candidates, vec!["Kelly (D-IL)", "Kelly (IL)"]);
    }

    #[test]
    fn an_unhinted_member_is_listed_with_an_id_that_resolves() {
        // `Peters` (Scott Peters, House) beside `Peters (D-MI)` (Gary Peters,
        // Senate): "Peters" is ambiguous, so the bare one needs its id to be named.
        let index = congress();
        let m = index.resolve("Peters");
        assert_eq!(m.method, MatchMethod::Ambiguous);
        assert_eq!(m.candidates, vec!["Peters (D-MI)", "Peters [P000608]"]);
        assert_eq!(index.resolve("Peters [P000608]").candidates, vec!["Peters"]);
    }

    #[test]
    fn congress_counts_members_not_surnames() {
        // Kellys 4, Johnsons 5, Davises 2, Peterses 2, Grijalvas 2.
        assert_eq!(congress().distinct_people(), 15);
    }

    #[test]
    fn a_row_with_a_member_id_never_reaches_an_illinois_match() {
        // Congress's `Peters` (P000608) and the Illinois Senate's `Peters` are the
        // same string. Robert Peters's link is the Illinois one only.
        let mut index = congress();
        index.insert_in_scope("Peters, Robert", IL_SENATE);
        index.insert_in_scope("Peters", IL_SENATE);
        let m = index.resolve("Robert Peters");
        assert_eq!(m.surname_only_spellings, vec!["Peters"]);
        assert!(m.member_ids.is_empty());
        let senate = Some(IL_SENATE);
        assert_eq!(m.confidence_for_row(&vote("Peters", ""), senate), Some(Confidence::Medium));
        assert_eq!(m.confidence_for_row(&vote("Peters", "P000608"), senate), None);

        // And a bare "Peters" is now three people, not one.
        let m = index.resolve("Peters");
        assert_eq!(m.method, MatchMethod::Ambiguous);
        assert_eq!(m.candidates, vec!["Peters", "Peters (D-MI)", "Peters [P000608]"]);
    }

    fn row(name: &str, option: &str) -> RawVoteRow {
        RawVoteRow {
            voter_name: name.to_string(),
            option: option.to_string(),
            note: String::new(),
        }
    }
}
