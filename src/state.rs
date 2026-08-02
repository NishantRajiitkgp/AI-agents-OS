//! Reading the project state: the repository root, the configuration, tasks, requirements.
//!
//! Everything here reads. Nothing decides. The selector, the transitions and the verification
//! record are in `commands`, and keeping the reader separate from them is what makes it
//! possible to test the selector against a directory of files rather than against a mock.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::yaml::{self, Value};

/// Failure that is not a check failing.
///
/// The distinction is the same one the exit codes carry, and it is the reason this is a
/// separate type rather than a string: a task that cannot be read and a task that is invalid
/// are different facts, and a system that conflates them lets a broken reader look like a
/// clean backlog.
#[derive(Debug)]
pub struct CouldNotRun(pub String);

impl std::fmt::Display for CouldNotRun {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

pub type Reading<T> = Result<T, CouldNotRun>;

/// Find the repository root by walking up for `aios/config.yml`.
///
/// ADR-013 §4 requires this rather than assuming the working directory, and requires refusing
/// rather than guessing when there is no root above. A tool that silently treats the current
/// directory as a project root will one day scaffold a task file into someone's home
/// directory.
pub fn find_root(start: &Path) -> Reading<PathBuf> {
    let mut current = if start.is_absolute() {
        start.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| CouldNotRun(format!("no working directory: {e}")))?
            .join(start)
    };
    loop {
        if current.join("aios").join("config.yml").is_file() {
            return Ok(current);
        }
        if !current.pop() {
            return Err(CouldNotRun(
                "not inside an aios project: no aios/config.yml in this directory or any \
                 above it. Run from inside the repository, or pass --root."
                    .into(),
            ));
        }
    }
}

pub fn read_to_string(path: &Path) -> Reading<String> {
    let bytes =
        fs::read(path).map_err(|e| CouldNotRun(format!("{}: {e}", path.display())))?;
    // A byte-order mark is stripped here rather than tolerated downstream. Frontmatter
    // parsing refuses a `---` that is not on the first byte, on purpose, and a BOM is the
    // most common way for that to happen invisibly.
    let text = String::from_utf8(bytes)
        .map_err(|e| CouldNotRun(format!("{} is not UTF-8: {e}", path.display())))?;
    Ok(text.strip_prefix('\u{feff}').unwrap_or(&text).to_string())
}

pub struct Config {
    pub root: PathBuf,
    pub value: Value,
}

impl Config {
    pub fn load(root: &Path) -> Reading<Config> {
        let path = root.join("aios").join("config.yml");
        let text = read_to_string(&path)?;
        let value = yaml::parse(&text)
            .map_err(|e| CouldNotRun(format!("{}: {e}", path.display())))?;
        Ok(Config { root: root.to_path_buf(), value })
    }

    pub fn tier(&self) -> String {
        self.value
            .get("tier")
            .and_then(|v| v.as_str())
            .unwrap_or("prototype")
            .to_string()
    }

    pub fn budget(&self, name: &str) -> Option<i64> {
        self.value.get("budgets")?.get(name)?.as_int()
    }

    pub fn strings(&self, key: &str) -> Vec<String> {
        self.value.get(key).map(|v| v.strings()).unwrap_or_default()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Status {
    Todo,
    Doing,
    Review,
    Done,
    Waiting,
    Dropped,
}

impl Status {
    pub fn parse(text: &str) -> Option<Status> {
        match text.trim() {
            "todo" => Some(Status::Todo),
            "doing" => Some(Status::Doing),
            "review" => Some(Status::Review),
            "done" => Some(Status::Done),
            "waiting" => Some(Status::Waiting),
            "dropped" => Some(Status::Dropped),
            _ => None,
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            Status::Todo => "todo",
            Status::Doing => "doing",
            Status::Review => "review",
            Status::Done => "done",
            Status::Waiting => "waiting",
            Status::Dropped => "dropped",
        }
    }

    /// Does this status settle a dependency?
    ///
    /// `dropped` counts, which is not an oversight: a task nobody is going to do no longer
    /// blocks anything, and leaving it blocking would make abandoning work impossible without
    /// editing every task that named it.
    pub fn settled(&self) -> bool {
        matches!(self, Status::Done | Status::Dropped)
    }
}

/// Risk, ordered so that `low` sorts first — the selector prefers it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Risk {
    Low,
    Medium,
    High,
}

impl Risk {
    pub fn parse(text: &str) -> Option<Risk> {
        match text.trim() {
            "low" => Some(Risk::Low),
            "medium" => Some(Risk::Medium),
            "high" => Some(Risk::High),
            _ => None,
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            Risk::Low => "low",
            Risk::Medium => "medium",
            Risk::High => "high",
        }
    }
}

#[derive(Debug, Clone)]
pub struct Task {
    pub path: PathBuf,
    pub id: String,
    pub title: String,
    pub status: Status,
    pub risk: Risk,
    pub priority: i64,
    pub satisfies: Vec<String>,
    pub blocked_by: Vec<String>,
    pub touches: Vec<String>,
    pub acceptance: Vec<String>,
    pub verify: Vec<String>,
    pub constraints: Vec<String>,
    pub waiting_on: Option<String>,
    pub reason: Option<String>,
    pub duplicate_check: Vec<String>,
    pub body: String,
    pub frontmatter: Value,
}

fn list_field(header: &Value, key: &str) -> Vec<String> {
    header.get(key).map(|v| v.strings()).unwrap_or_default()
}

fn optional(header: &Value, key: &str) -> Option<String> {
    header
        .get(key)
        .and_then(|v| v.as_str())
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

impl Task {
    pub fn load(path: &Path) -> Reading<Task> {
        let text = read_to_string(path)?;
        let (header, body) = yaml::frontmatter(&text)
            .map_err(|e| CouldNotRun(format!("{}: {e}", path.display())))?;

        let field = |key: &str| -> Reading<String> {
            header
                .get(key)
                .and_then(|v| v.as_str())
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .ok_or_else(|| {
                    CouldNotRun(format!("{}: missing required field {key:?}", path.display()))
                })
        };

        let status_text = field("status")?;
        let status = Status::parse(&status_text).ok_or_else(|| {
            CouldNotRun(format!(
                "{}: status {status_text:?} is not one of todo, doing, review, done, waiting, \
                 dropped",
                path.display()
            ))
        })?;

        let risk_text = field("risk")?;
        let risk = Risk::parse(&risk_text).ok_or_else(|| {
            CouldNotRun(format!(
                "{}: risk {risk_text:?} is not one of low, medium, high",
                path.display()
            ))
        })?;

        let priority = header
            .get("priority")
            .and_then(|v| v.as_int())
            .ok_or_else(|| {
                CouldNotRun(format!("{}: priority must be a whole number", path.display()))
            })?;

        Ok(Task {
            path: path.to_path_buf(),
            id: field("id")?,
            title: field("title")?,
            status,
            risk,
            priority,
            satisfies: list_field(&header, "satisfies"),
            blocked_by: list_field(&header, "blocked_by"),
            touches: list_field(&header, "touches"),
            acceptance: list_field(&header, "acceptance"),
            verify: list_field(&header, "verify"),
            constraints: list_field(&header, "constraints"),
            waiting_on: optional(&header, "waiting_on"),
            reason: optional(&header, "reason"),
            duplicate_check: list_field(&header, "duplicate_check"),
            body,
            frontmatter: header,
        })
    }
}

/// Every task file, and every file that failed to parse.
///
/// Both halves are returned. Dropping the unreadable ones would let a task file with broken
/// frontmatter disappear from `aios list` and from the selector's view of what is blocking —
/// which is indistinguishable from the task not existing, and is how a backlog silently
/// shrinks.
pub fn load_tasks(root: &Path) -> Reading<(Vec<Task>, Vec<CouldNotRun>)> {
    let dir = root.join("aios").join("tasks");
    let entries = fs::read_dir(&dir)
        .map_err(|e| CouldNotRun(format!("{}: {e}", dir.display())))?;

    let mut tasks = Vec::new();
    let mut broken = Vec::new();
    let mut paths: Vec<PathBuf> = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|e| CouldNotRun(format!("{}: {e}", dir.display())))?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) == Some("md") {
            paths.push(path);
        }
    }
    // Sorted before parsing, so that every ordering downstream starts from one that does not
    // depend on the order the filesystem happened to return.
    paths.sort();

    for path in paths {
        match Task::load(&path) {
            Ok(task) => tasks.push(task),
            Err(err) => broken.push(err),
        }
    }
    Ok((tasks, broken))
}

/// Requirement IDs that are currently active, by area file.
pub fn active_requirements(root: &Path) -> Reading<Vec<String>> {
    let dir = root.join("aios").join("requirements");
    let mut ids = Vec::new();
    let entries = match fs::read_dir(&dir) {
        Ok(entries) => entries,
        Err(_) => return Ok(ids), // a project may have none yet; that is not an error
    };
    for entry in entries {
        let entry = entry.map_err(|e| CouldNotRun(format!("{}: {e}", dir.display())))?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("md") {
            continue;
        }
        let text = read_to_string(&path)?;
        for line in text.lines() {
            // `| REQ-1 | ... | active | ...` — the table form the requirement files use. The
            // ID and the status are read positionally from the row rather than by parsing
            // markdown, because the schema validator already refuses a row of the wrong shape.
            let trimmed = line.trim();
            if !trimmed.starts_with('|') {
                continue;
            }
            let cells: Vec<&str> = trimmed.trim_matches('|').split('|').map(str::trim).collect();
            if cells.len() < 2 {
                continue;
            }
            let id = cells[0];
            if id.is_empty() || id.starts_with("---") || id.eq_ignore_ascii_case("id") {
                continue;
            }
            let active = cells.iter().any(|c| *c == "active");
            if active {
                ids.push(id.to_string());
            }
        }
    }
    ids.sort();
    ids.dedup();
    Ok(ids)
}

/// Incidents that declare `blocks_work: true`.
///
/// Read for the refusal in `aios next` (M1-11). An incident that has stopped work is a fact
/// about the repository, and routing an agent around it is the behaviour this refuses.
pub fn blocking_incidents(root: &Path) -> Reading<Vec<(String, String)>> {
    let dir = root.join("aios").join("incidents");
    let mut blocking = Vec::new();
    let entries = match fs::read_dir(&dir) {
        Ok(entries) => entries,
        Err(_) => return Ok(blocking),
    };
    let mut paths: Vec<PathBuf> = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|e| CouldNotRun(format!("{}: {e}", dir.display())))?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) == Some("md") {
            paths.push(path);
        }
    }
    paths.sort();
    for path in paths {
        let text = read_to_string(&path)?;
        let Ok((header, _)) = yaml::frontmatter(&text) else {
            continue; // the incident validator owns this failure; do not report it twice
        };
        if header.get("blocks_work").and_then(|v| v.as_bool()) == Some(true) {
            let title = header
                .get("title")
                .and_then(|v| v.as_str())
                .unwrap_or("(untitled)")
                .to_string();
            let name = path
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("?")
                .to_string();
            blocking.push((name, title));
        }
    }
    Ok(blocking)
}

/// The current commit SHA, for the verification record.
pub fn head_sha(root: &Path) -> Reading<String> {
    let out = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(root)
        .output()
        .map_err(|e| CouldNotRun(format!("could not run git: {e}")))?;
    if !out.status.success() {
        return Err(CouldNotRun(
            "git rev-parse HEAD failed. A verification record names the commit it was taken \
             at; without one the record cannot be re-checked, and a record nobody can \
             re-check is the thing this whole mechanism exists to avoid."
                .into(),
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

/// Today, as `YYYY-MM-DD`, from the system clock.
///
/// Hand-rolled civil-date conversion because there are no dependencies. This is Howard
/// Hinnant's `civil_from_days`, which is exact for the range any repository will see.
pub fn today() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let (y, m, d) = civil_from_days(secs.div_euclid(86_400));
    format!("{y:04}-{m:02}-{d:02}")
}

pub fn civil_from_days(days_since_epoch: i64) -> (i64, u32, u32) {
    let z = days_since_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (if m <= 2 { y + 1 } else { y }, m, d)
}

/// A stable short hash, for allocating task IDs without a dependency.
///
/// FNV-1a. Not a cryptographic hash and not used as one: the requirement is that two titles
/// created a second apart do not collide, and that the value does not depend on the machine.
pub fn short_hash(input: &str, width: usize) -> String {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for byte in input.as_bytes() {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    let full = format!("{hash:016x}");
    full[..width.min(full.len())].to_string()
}

/// Rewrite one scalar field in a file's frontmatter, leaving everything else byte-identical.
///
/// A rewrite rather than a re-serialise. Round-tripping the document through the parser would
/// reformat every comment and every block scalar in it, turning a one-word status change into
/// a diff nobody can review — and an unreviewable diff on state files is how this system stops
/// being auditable.
pub fn set_frontmatter_field(text: &str, key: &str, value: &str) -> Option<String> {
    let mut out = String::new();
    let mut seen_open = false;
    let mut in_header = false;
    let mut replaced = false;
    for line in text.lines() {
        if !seen_open {
            seen_open = true;
            in_header = line.trim_end() == "---";
            out.push_str(line);
            out.push('\n');
            continue;
        }
        if in_header && line.trim_end() == "---" {
            in_header = false;
            out.push_str(line);
            out.push('\n');
            continue;
        }
        if in_header && !replaced {
            let head = line.split(':').next().unwrap_or("");
            if head.trim() == key && line.starts_with(key) {
                out.push_str(&format!("{key}: {value}\n"));
                replaced = true;
                continue;
            }
        }
        out.push_str(line);
        out.push('\n');
    }
    if replaced { Some(out) } else { None }
}

/// Insert a field into the frontmatter immediately before its closing marker.
pub fn add_frontmatter_field(text: &str, block: &str) -> Option<String> {
    let mut out = String::new();
    let mut seen_open = false;
    let mut inserted = false;
    for line in text.lines() {
        if !seen_open {
            seen_open = true;
            out.push_str(line);
            out.push('\n');
            continue;
        }
        if !inserted && line.trim_end() == "---" {
            out.push_str(block);
            if !block.ends_with('\n') {
                out.push('\n');
            }
            inserted = true;
        }
        out.push_str(line);
        out.push('\n');
    }
    if inserted { Some(out) } else { None }
}

/// Write a file with LF endings and no BOM, which is what the hygiene gate requires.
pub fn write(path: &Path, text: &str) -> Reading<()> {
    let normalised = text.replace("\r\n", "\n");
    fs::write(path, normalised.as_bytes())
        .map_err(|e| CouldNotRun(format!("{}: {e}", path.display())))
}

/// Index tasks by ID, reporting any ID claimed twice.
pub fn by_id(tasks: &[Task]) -> (BTreeMap<String, Task>, Vec<String>) {
    let mut map: BTreeMap<String, Task> = BTreeMap::new();
    let mut duplicates = Vec::new();
    for task in tasks {
        if let Some(existing) = map.get(&task.id) {
            duplicates.push(format!(
                "{} is claimed by both {} and {}",
                task.id,
                existing.path.display(),
                task.path.display()
            ));
            continue;
        }
        map.insert(task.id.clone(), task.clone());
    }
    (map, duplicates)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dropped_settles_a_dependency_and_review_does_not() {
        assert!(Status::Dropped.settled());
        assert!(Status::Done.settled());
        assert!(!Status::Review.settled());
        assert!(!Status::Todo.settled());
    }

    #[test]
    fn risk_orders_low_first() {
        assert!(Risk::Low < Risk::Medium);
        assert!(Risk::Medium < Risk::High);
    }

    #[test]
    fn an_unknown_status_is_rejected_rather_than_defaulted() {
        assert!(Status::parse("blocked").is_none(), "blocked is derived, not stored");
        assert!(Status::parse("").is_none());
    }

    #[test]
    fn the_epoch_converts_to_its_civil_date() {
        assert_eq!(civil_from_days(0), (1970, 1, 1));
        assert_eq!(civil_from_days(19_723), (2024, 1, 1));
    }

    #[test]
    fn a_leap_day_converts() {
        assert_eq!(civil_from_days(19_783), (2024, 3, 1));
        assert_eq!(civil_from_days(19_782), (2024, 2, 29));
    }

    #[test]
    fn the_hash_is_stable_and_machine_independent() {
        assert_eq!(short_hash("a title", 4), short_hash("a title", 4));
        assert_ne!(short_hash("a title", 4), short_hash("another title", 4));
        assert_eq!(short_hash("x", 4).len(), 4);
        assert_eq!(short_hash("x", 6).len(), 6);
    }

    #[test]
    fn setting_a_field_leaves_the_rest_byte_identical() {
        let source = "---\nid: T-1\nstatus: todo\n# a comment\n---\nbody\n";
        let updated = set_frontmatter_field(source, "status", "doing").unwrap();
        assert!(updated.contains("status: doing"));
        assert!(updated.contains("# a comment"), "comments must survive");
        assert!(updated.contains("id: T-1"));
        assert!(updated.ends_with("body\n"));
    }

    #[test]
    fn setting_a_field_that_is_absent_reports_rather_than_inventing_it() {
        let source = "---\nid: T-1\n---\nbody\n";
        assert!(set_frontmatter_field(source, "status", "doing").is_none());
    }

    #[test]
    fn a_field_name_in_the_body_is_not_mistaken_for_the_field() {
        let source = "---\nid: T-1\nstatus: todo\n---\nstatus: done\n";
        let updated = set_frontmatter_field(source, "status", "doing").unwrap();
        assert!(updated.ends_with("status: done\n"), "the body must not be touched");
    }

    #[test]
    fn a_record_is_added_before_the_closing_marker() {
        let source = "---\nid: T-1\n---\nbody\n";
        let updated = add_frontmatter_field(source, "verified:\n  sha: abc\n").unwrap();
        let header = updated.split("---").nth(1).unwrap();
        assert!(header.contains("verified:"));
        assert!(updated.ends_with("body\n"));
    }
}
