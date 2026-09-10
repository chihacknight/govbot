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
//! | usa    | `Arrington`, with the bioguide id in `note` |
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
            MatchMethod::UniqueSurname | MatchMethod::SurnameInitial => Confidence::Medium,
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
}

impl NameMatch {
    fn unmatched() -> Self {
        Self {
            method: MatchMethod::Unmatched,
            confidence: Confidence::None,
            candidates: Vec::new(),
        }
    }

    fn resolved(method: MatchMethod, name: String) -> Self {
        Self::resolved_many(method, vec![name])
    }

    /// One person, spelled several ways in the data. Every spelling is carried so a
    /// caller filtering on `candidates` catches all of that person's rows.
    fn resolved_many(method: MatchMethod, spellings: Vec<String>) -> Self {
        Self {
            method,
            confidence: method.confidence(),
            candidates: spellings,
        }
    }

    fn ambiguous(candidates: Vec<String>) -> Self {
        Self {
            method: MatchMethod::Ambiguous,
            confidence: Confidence::None,
            candidates,
        }
    }

    /// Whether this match may be used to attribute a bill or vote to a person.
    pub fn is_attributable(&self, minimum: Confidence) -> bool {
        self.confidence >= minimum && self.confidence > Confidence::None
    }
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
    by_bioguide: HashMap<String, String>,
    suspect_fragments: BTreeSet<String>,
    all: BTreeSet<String>,
}

impl NameIndex {
    pub fn new() -> Self {
        Self::default()
    }

    /// Record a name that appears in the data.
    pub fn insert(&mut self, raw: &str) {
        let raw = raw.trim();
        if raw.is_empty() {
            return;
        }
        if is_suspect_fragment(raw) {
            self.suspect_fragments.insert(raw.to_string());
            return;
        }

        let normalized = normalize(raw);
        if normalized.is_empty() {
            return;
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
    }

    /// Record a stable external identifier for a name — the bioguide id carried in
    /// the `note` field of federal vote rows.
    pub fn insert_identifier(&mut self, identifier: &str, raw_name: &str) {
        let identifier = identifier.trim();
        if identifier.is_empty() {
            return;
        }
        self.by_bioguide
            .insert(identifier.to_uppercase(), raw_name.trim().to_string());
    }

    /// Distinct people, counted after normalization.
    ///
    /// Prefer this over [`Self::distinct_raw_spellings`] for anything a reader will
    /// interpret as a headcount. Wyoming's data spells the same legislator both
    /// `Smith, S` and `SMITH, S`, so counting raw strings reports 184 voters for a
    /// 93-member legislature.
    pub fn distinct_people(&self) -> usize {
        self.by_full_key.len()
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

        // A bioguide id, if the caller happens to have one, beats every heuristic.
        if let Some(name) = self.by_bioguide.get(&query.to_uppercase()) {
            return NameMatch::resolved(MatchMethod::Bioguide, name.clone());
        }

        let normalized = normalize(query);
        if normalized.is_empty() {
            return NameMatch::unmatched();
        }

        // Full name, exactly as given. Several raw strings may share one normalized
        // key — `Smith, S` and `SMITH, S` are one legislator spelled two ways, not
        // two legislators — so every spelling is returned and none is ambiguity.
        if let Some(matches) = self.by_full_key.get(&normalized.key()) {
            return NameMatch::resolved_many(MatchMethod::ExactName, to_vec(matches));
        }

        // The caller wrote the name in the other order from the data, or the data
        // wrote it in the other order from the caller. `normalize` already
        // reorders an explicit `Family, Given`, so this covers the rest.
        if normalized.tokens.len() > 1 {
            let mut swapped = normalized.tokens.clone();
            let last = swapped.len() - 1;
            swapped.rotate_left(last);
            if let Some(matches) = self.by_full_key.get(&swapped.join(" ")) {
                return NameMatch::resolved_many(MatchMethod::ReversedName, to_vec(matches));
            }
        }

        // Surname only. This is where collisions live.
        let Some(surname) = normalized.surname() else {
            return NameMatch::unmatched();
        };
        let Some(surname_matches) = self.by_surname.get(surname) else {
            return NameMatch::unmatched();
        };

        let people = group_by_person(surname_matches);
        if people.len() == 1 {
            let spellings = people.into_values().next().expect("checked above");
            return NameMatch::resolved_many(MatchMethod::UniqueSurname, spellings);
        }

        // Several distinct people share the surname. A given-name initial from the
        // caller may pick one out; anything less and we refuse.
        if let Some(initial) = normalized.given_initial() {
            let narrowed: Vec<Vec<String>> = people
                .values()
                .filter(|spellings| {
                    spellings.first().is_some_and(|name| {
                        normalize(name)
                            .given_initial()
                            .is_some_and(|c| c == initial)
                    })
                })
                .cloned()
                .collect();
            if narrowed.len() == 1 {
                return NameMatch::resolved_many(
                    MatchMethod::SurnameInitial,
                    narrowed.into_iter().next().expect("checked above"),
                );
            }
        }

        // Report one representative spelling per person, so the caller is choosing
        // between people rather than between spellings.
        NameMatch::ambiguous(
            people
                .into_values()
                .filter_map(|spellings| spellings.into_iter().next())
                .collect(),
        )
    }
}

/// Group raw spellings by the person they normalize to.
///
/// This is what separates "one legislator written two ways" from "two legislators
/// who share a surname" — the first is resolvable, the second must not be.
fn group_by_person(names: &BTreeSet<String>) -> BTreeMap<String, Vec<String>> {
    let mut grouped: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for name in names {
        grouped
            .entry(normalize(name).key())
            .or_default()
            .push(name.clone());
    }
    grouped
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

    fn row(name: &str, option: &str) -> RawVoteRow {
        RawVoteRow {
            voter_name: name.to_string(),
            option: option.to_string(),
            note: String::new(),
        }
    }
}
