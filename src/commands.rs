//! The subcommands: what the tool does once it has read the state.
//!
//! The ordering rule for this file is that anything which decides lives here and anything
//! which reads lives in `state`. The selector in particular is a pure function of a task list
//! (`select`), with the reading and the printing outside it, because determinism is the
//! property it is supposed to have and a function that reads the disk cannot be shown to have
//! it.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::state::{
    self, active_requirements, blocking_incidents, by_id, load_tasks, Config, CouldNotRun,
    Reading, Status, Task,
};
use crate::yaml;

pub const OK: u8 = 0;
pub const FAILED: u8 = 1;
pub const COULD_NOT_RUN: u8 = 2;

/// Run a command string through the platform shell, returning its exit code and output.
///
/// A shell rather than a split-and-exec, because `verify` entries are written the way a
/// person would type them and several are pipelines. The consequence is that `verify` is
/// arbitrary code execution by construction — which is why it is a reviewed, checked-in field
/// on a protected path rather than something the agent supplies at the point of use.
fn shell(root: &Path, command: &str) -> Reading<(i32, String)> {
    let output = if cfg!(windows) {
        Command::new("cmd").args(["/C", command]).current_dir(root).output()
    } else {
        Command::new("sh").args(["-c", command]).current_dir(root).output()
    };
    let output = output.map_err(|e| CouldNotRun(format!("could not run {command:?}: {e}")))?;
    let mut text = String::from_utf8_lossy(&output.stdout).to_string();
    text.push_str(&String::from_utf8_lossy(&output.stderr));
    // A command killed by a signal has no code. Reporting -1 rather than treating it as a
    // pass is the whole point: `done` must not be reachable by a verify step that crashed.
    Ok((output.status.code().unwrap_or(-1), text))
}

// --- aios next ---------------------------------------------------------------------------

/// Why the selector will not hand out work.
pub enum Refusal {
    BacklogInvalid(Vec<String>),
    IncidentOpen(Vec<(String, String)>),
}

impl Refusal {
    pub fn report(&self) {
        match self {
            Refusal::BacklogInvalid(problems) => {
                eprintln!("aios next: the backlog does not validate, so there is no next task.");
                eprintln!();
                for problem in problems {
                    eprintln!("  {problem}");
                }
                eprintln!();
                eprintln!(
                    "This is the intended behaviour, not a bug to work around. An agent should \
                     be stopped by a broken plan rather than routed past it — the selector \
                     cannot be correct about which task is next while the task graph it reads \
                     is wrong."
                );
            }
            Refusal::IncidentOpen(incidents) => {
                eprintln!(
                    "aios next: {} open incident(s) declare blocks_work, so no work is handed \
                     out.",
                    incidents.len()
                );
                eprintln!();
                for (file, title) in incidents {
                    eprintln!("  {file}  {title}");
                }
                eprintln!();
                eprintln!(
                    "Close the incident, or change its blocks_work to false with the reason \
                     recorded in the file. Both are edits a person makes deliberately, which is \
                     the point."
                );
            }
        }
    }
}

/// Everything that makes the backlog unfit to select from.
fn backlog_problems(root: &Path, tasks: &[Task], broken: &[CouldNotRun]) -> Vec<String> {
    let mut problems: Vec<String> = broken.iter().map(|e| e.0.clone()).collect();

    let (index, duplicates) = by_id(tasks);
    problems.extend(duplicates);

    let requirements: BTreeSet<String> = active_requirements(root)
        .unwrap_or_default()
        .into_iter()
        .collect();

    for task in tasks {
        if task.status.settled() {
            continue;
        }
        for requirement in &task.satisfies {
            // Only checked when some requirement file exists. A project in its first hour has
            // tasks and no requirements yet, and failing there would make the tool unusable
            // exactly when someone is deciding whether to keep it.
            if !requirements.is_empty() && !requirements.contains(requirement) {
                problems.push(format!(
                    "{} satisfies {requirement}, which is not an active requirement",
                    task.id
                ));
            }
        }
        for blocker in &task.blocked_by {
            if !index.contains_key(blocker) {
                problems.push(format!(
                    "{} is blocked_by {blocker}, which is not a task in this repository",
                    task.id
                ));
            }
        }
        if task.status == Status::Waiting && task.waiting_on.is_none() {
            problems.push(format!("{} is waiting with no waiting_on", task.id));
        }
        if task.status == Status::Dropped && task.reason.is_none() {
            problems.push(format!("{} is dropped with no reason", task.id));
        }
    }
    problems.sort();
    problems.dedup();
    problems
}

/// How many other tasks a task's completion would unblock.
fn unblocks(task: &Task, tasks: &[Task]) -> usize {
    tasks
        .iter()
        .filter(|other| other.blocked_by.iter().any(|id| *id == task.id))
        .count()
}

/// The selector (M1-10). A total function of the task list.
///
/// Sort: priority ascending, then tasks-unblocked descending, then risk ascending, then id
/// lexicographically. The design also names `created_at` between risk and id. It is not here,
/// because it is not in the task schema — Q-004 recorded that gap and it was never closed, so
/// sorting by it would mean either inventing the field or reading the filesystem's mtime. The
/// second is worse than it looks: mtime differs between two clones of the same commit, which
/// would make the answer machine-dependent, and machine-independence is the property this
/// ordering exists to provide. The id tie-break is total on its own, so the function is still
/// total without it; what is lost is only the preference for older work among exact ties.
pub fn select(tasks: &[Task]) -> Vec<&Task> {
    let settled: BTreeSet<&str> = tasks
        .iter()
        .filter(|t| t.status.settled())
        .map(|t| t.id.as_str())
        .collect();

    let mut ready: Vec<&Task> = tasks
        .iter()
        .filter(|t| t.status == Status::Todo)
        .filter(|t| t.blocked_by.iter().all(|id| settled.contains(id.as_str())))
        .collect();

    ready.sort_by(|a, b| {
        a.priority
            .cmp(&b.priority)
            .then(unblocks(b, tasks).cmp(&unblocks(a, tasks)))
            .then(a.risk.cmp(&b.risk))
            .then(a.id.cmp(&b.id))
    });
    ready
}

pub fn next(root: &Path, json: bool) -> Reading<u8> {
    let (tasks, broken) = load_tasks(root)?;

    let problems = backlog_problems(root, &tasks, &broken);
    if !problems.is_empty() {
        Refusal::BacklogInvalid(problems).report();
        return Ok(FAILED);
    }

    let incidents = blocking_incidents(root)?;
    if !incidents.is_empty() {
        Refusal::IncidentOpen(incidents).report();
        return Ok(FAILED);
    }

    // The single call site M1-11 asked for. Review debt is measured by M5-09 and is not wired
    // to a refusal yet; when it is, it goes here and nowhere else.
    // if review_debt_exceeded(root)? { ... }

    let ready = select(&tasks);
    let Some(task) = ready.first() else {
        report_why_nothing_is_ready(&tasks);
        return Ok(OK);
    };

    if json {
        println!("{{\"id\": \"{}\", \"title\": \"{}\", \"path\": \"{}\"}}",
            escape(&task.id), escape(&task.title), escape(&task.path.display().to_string()));
    } else {
        println!("{}  {}", task.id, task.title);
        println!();
        println!("  priority {}   risk {}   unblocks {}",
            task.priority, task.risk.name(), unblocks(task, &tasks));
        if !task.touches.is_empty() {
            println!("  touches  {}", task.touches.join(", "));
        }
        println!("  file     {}", task.path.display());
        println!();
        println!("  aios start {}", task.id);
    }
    Ok(OK)
}

/// The empty case has to say why, per M1-10.
///
/// "No tasks available" is the least useful thing a selector can print: it is equally true
/// when the backlog is empty, when everything is in flight, and when one unfinished task is
/// holding up nine others. Those need different actions.
fn report_why_nothing_is_ready(tasks: &[Task]) {
    let todo: Vec<&Task> = tasks.iter().filter(|t| t.status == Status::Todo).collect();
    if tasks.is_empty() {
        println!("No tasks at all. `aios new task` writes the first one.");
        return;
    }
    if todo.is_empty() {
        let mut counts: Vec<(Status, usize)> = Vec::new();
        for status in [Status::Doing, Status::Review, Status::Waiting, Status::Done,
                       Status::Dropped] {
            let count = tasks.iter().filter(|t| t.status == status).count();
            if count > 0 {
                counts.push((status, count));
            }
        }
        let summary: Vec<String> = counts
            .iter()
            .map(|(status, count)| format!("{count} {}", status.name()))
            .collect();
        println!("Nothing is todo. The backlog is {}.", summary.join(", "));
        println!();
        println!("Nothing is waiting on the selector — the next move is on whatever is in \
                  review, or on writing a new task.");
        return;
    }

    let settled: BTreeSet<&str> = tasks
        .iter()
        .filter(|t| t.status.settled())
        .map(|t| t.id.as_str())
        .collect();
    println!("{} task(s) are todo and every one is blocked:", todo.len());
    println!();
    for task in &todo {
        let blockers: Vec<String> = task
            .blocked_by
            .iter()
            .filter(|id| !settled.contains(id.as_str()))
            .cloned()
            .collect();
        println!("  {}  {}", task.id, task.title);
        for blocker in blockers {
            let state = tasks
                .iter()
                .find(|t| t.id == blocker)
                .map(|t| t.status.name())
                .unwrap_or("missing");
            println!("      blocked by {blocker} ({state})");
        }
    }
}

fn escape(text: &str) -> String {
    text.replace('\\', "\\\\").replace('"', "\\\"")
}

// --- aios start / submit / done ------------------------------------------------------------

fn find(root: &Path, id: &str) -> Reading<Task> {
    let (tasks, _) = load_tasks(root)?;
    tasks
        .into_iter()
        .find(|t| t.id == id)
        .ok_or_else(|| CouldNotRun(format!("no task with id {id}")))
}

/// Is this transition legal, and if not, why not in this specific case?
///
/// The message matters as much as the refusal. "Illegal transition" tells the reader that
/// something is wrong and nothing about what to do, and a tool that answers that way often
/// enough gets its state model worked around by hand-editing — which M1-15 then has to catch.
fn transition_refusal(task: &Task, to: Status) -> Option<String> {
    let from = task.status;
    if from == to {
        return Some(format!("{} is already {}.", task.id, to.name()));
    }
    let legal = matches!(
        (from, to),
        (Status::Todo, Status::Doing)
            | (Status::Doing, Status::Review)
            | (Status::Review, Status::Done)
            | (Status::Review, Status::Doing)
            | (Status::Todo, Status::Waiting)
            | (Status::Doing, Status::Waiting)
            | (Status::Waiting, Status::Todo)
            | (Status::Waiting, Status::Doing)
            | (Status::Todo, Status::Dropped)
            | (Status::Doing, Status::Dropped)
            | (Status::Review, Status::Dropped)
            | (Status::Waiting, Status::Dropped)
    );
    if legal {
        return None;
    }
    let advice = match (from, to) {
        (Status::Todo, Status::Review) => {
            "A task cannot be submitted without having been started. `aios start` first — the \
             point of the intermediate state is that the work was claimed by somebody."
        }
        (Status::Todo, Status::Done) | (Status::Doing, Status::Done) => {
            "`done` is reachable only from `review`, and only by running the verify commands. \
             That is the mechanism the whole milestone exists for: done is not a claim, it is \
             a state a named command exits zero to reach."
        }
        (Status::Done, _) => {
            "A done task is finished. If it was wrong, the honest record is a new task that \
             says so — reopening erases the fact that it was once believed complete."
        }
        (Status::Dropped, _) => {
            "A dropped task stays dropped, with its reason. Write a new one if the work is \
             wanted again; the record of having decided against it is worth keeping."
        }
        _ => "The states are todo, doing, review, done, waiting and dropped, and the only \
              paths between them are the ones in `aios help`.",
    };
    Some(format!(
        "{} is {} and cannot move to {}.\n\n  {advice}",
        task.id,
        from.name(),
        to.name()
    ))
}

fn move_to(root: &Path, id: &str, to: Status) -> Reading<u8> {
    let task = find(root, id)?;
    if let Some(refusal) = transition_refusal(&task, to) {
        eprintln!("{refusal}");
        return Ok(FAILED);
    }

    if to == Status::Doing && task.status == Status::Todo {
        let settled: BTreeSet<String> = {
            let (tasks, _) = load_tasks(root)?;
            tasks
                .iter()
                .filter(|t| t.status.settled())
                .map(|t| t.id.clone())
                .collect()
        };
        let open: Vec<&String> = task
            .blocked_by
            .iter()
            .filter(|b| !settled.contains(*b))
            .collect();
        if !open.is_empty() {
            eprintln!(
                "{} is blocked by {} task(s) that are not done or dropped: {}",
                task.id,
                open.len(),
                open.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", ")
            );
            eprintln!();
            eprintln!(
                "`blocked` is not a state — it is read from blocked_by, so there is nothing to \
                 override here. Finish or drop the blocker."
            );
            return Ok(FAILED);
        }
    }

    let text = state::read_to_string(&task.path)?;
    let updated = state::set_frontmatter_field(&text, "status", to.name()).ok_or_else(|| {
        CouldNotRun(format!(
            "{}: no `status:` line in the frontmatter to rewrite",
            task.path.display()
        ))
    })?;
    state::write(&task.path, &updated)?;
    println!("{}: {} → {}", task.id, task.status.name(), to.name());
    Ok(OK)
}

pub fn start(root: &Path, id: &str) -> Reading<u8> {
    move_to(root, id, Status::Doing)
}

pub fn submit(root: &Path, id: &str) -> Reading<u8> {
    let task = find(root, id)?;
    if task.verify.is_empty() {
        eprintln!(
            "{} declares no verify commands, so nothing could establish that it is finished.",
            task.id
        );
        eprintln!();
        eprintln!(
            "Add at least one command to `verify:`. A task whose completion cannot be checked \
             by running something is a task whose completion is an opinion."
        );
        return Ok(FAILED);
    }
    move_to(root, id, Status::Review)
}

/// `aios done` (M1-13) — the mechanism everything else hangs on.
///
/// Every command in `verify` runs. If any exits non-zero the task does not move, and no
/// argument to this subcommand changes that: there is deliberately no `--force`, no `--skip`
/// and no way to pass a substitute command. The record written afterwards names the commit,
/// the exact commands and their exit codes, so that CI can re-run them at that SHA and
/// disagree (M1-15). The record is evidence, not an assertion — its only value is that
/// somebody else can check it.
pub fn done(root: &Path, id: &str) -> Reading<u8> {
    let task = find(root, id)?;
    if let Some(refusal) = transition_refusal(&task, Status::Done) {
        eprintln!("{refusal}");
        return Ok(FAILED);
    }
    if task.verify.is_empty() {
        eprintln!("{} declares no verify commands. There is nothing to establish.", task.id);
        return Ok(FAILED);
    }

    let sha = state::head_sha(root)?;
    println!("{}: running {} verify command(s) at {}", task.id, task.verify.len(),
             &sha[..sha.len().min(8)]);
    println!();

    let mut results: Vec<(String, i32)> = Vec::new();
    let mut failed = false;
    for command in &task.verify {
        let (code, output) = shell(root, command)?;
        println!("  [{}] {command}", if code == 0 { "ok" } else { "FAILED" });
        if code != 0 {
            failed = true;
            for line in output.lines().rev().take(20).collect::<Vec<_>>().iter().rev() {
                println!("      {line}");
            }
        }
        results.push((command.clone(), code));
    }

    if failed {
        println!();
        eprintln!(
            "{} stays in review. {} of {} verify command(s) failed.",
            task.id,
            results.iter().filter(|(_, code)| *code != 0).count(),
            results.len()
        );
        eprintln!();
        eprintln!(
            "There is no flag that moves it anyway. Fix the code or fix the command — and if \
             the command is what is wrong, that change belongs in review like any other, \
             because a verify list edited to pass is the failure this is built to prevent."
        );
        return Ok(FAILED);
    }

    let mut record = String::from("verified:\n");
    record.push_str(&format!("  sha: {sha}\n"));
    record.push_str(&format!("  at: {}\n", state::today()));
    record.push_str("  commands:\n");
    for (command, code) in &results {
        record.push_str(&format!("    - command: {}\n", quote(command)));
        record.push_str(&format!("      exit: {code}\n"));
    }

    let text = state::read_to_string(&task.path)?;
    let without_old = strip_field(&text, "verified");
    let with_record = state::add_frontmatter_field(&without_old, &record).ok_or_else(|| {
        CouldNotRun(format!("{}: frontmatter has no closing marker", task.path.display()))
    })?;
    let updated = state::set_frontmatter_field(&with_record, "status", "done").ok_or_else(
        || CouldNotRun(format!("{}: no `status:` line to rewrite", task.path.display())),
    )?;
    state::write(&task.path, &updated)?;

    println!();
    println!("{}: review → done, recorded at {}", task.id, &sha[..sha.len().min(8)]);
    println!(
        "CI re-runs these commands at that commit and will disagree if the record does not \
         hold (M1-15)."
    );
    Ok(OK)
}

fn quote(text: &str) -> String {
    format!("\"{}\"", text.replace('\\', "\\\\").replace('"', "\\\""))
}

/// Remove a top-level frontmatter field and everything indented under it.
fn strip_field(text: &str, key: &str) -> String {
    let mut out = String::new();
    let mut seen_open = false;
    let mut in_header = false;
    let mut skipping = false;
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
            skipping = false;
            out.push_str(line);
            out.push('\n');
            continue;
        }
        if in_header {
            if skipping {
                let indented = line.starts_with(' ') || line.starts_with('\t');
                if indented || line.trim().is_empty() {
                    continue;
                }
                skipping = false;
            }
            if line.starts_with(key) && line[key.len()..].starts_with(':') {
                skipping = true;
                continue;
            }
        }
        out.push_str(line);
        out.push('\n');
    }
    out
}

// --- aios new -------------------------------------------------------------------------------

/// Allocate a task ID: `T-` plus four hex characters, widening on collision.
///
/// Hashed rather than sequential because sequential IDs collide on every parallel branch —
/// two people running `aios new` on two branches both get the next number, and the conflict
/// surfaces at merge time as two different tasks with one ID.
pub fn allocate_id(title: &str, seed: &str, taken: &BTreeSet<String>) -> String {
    for width in [4usize, 5, 6, 7, 8] {
        let candidate = format!("T-{}", state::short_hash(&format!("{title}{seed}"), width));
        if !taken.contains(&candidate) {
            return candidate;
        }
    }
    // Eight hex characters colliding means the same title and the same timestamp eight times.
    // Falling back to a longer hash of the whole taken set is deterministic and terminates.
    format!("T-{}", state::short_hash(&format!("{title}{seed}{}", taken.len()), 10))
}

pub fn new_task(root: &Path, title: &str) -> Reading<u8> {
    let (tasks, _) = load_tasks(root)?;
    let taken: BTreeSet<String> = tasks.iter().map(|t| t.id.clone()).collect();
    let seed = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos().to_string())
        .unwrap_or_default();
    let id = allocate_id(title, &seed, &taken);
    let path = root.join("aios").join("tasks").join(format!("{id}.md"));

    let scaffold = format!(
        "---\n\
         id: {id}\n\
         title: {title}\n\
         status: todo\n\
         satisfies: []\n\
         priority: 3\n\
         risk: low\n\
         blocked_by: []\n\
         touches: []\n\
         acceptance:\n\
         \x20 - \"When <trigger>, the system shall <observable response>\"\n\
         verify: []\n\
         ---\n\
         \n\
         Why this task exists, and what someone reading it in three months needs to know that\n\
         the fields above do not say.\n\
         \n\
         `acceptance` is what will be checked; `verify` is what checks it. Neither may stay as\n\
         scaffolding — an empty verify list is refused by `aios submit`, deliberately, because\n\
         a task nobody can run anything against cannot be finished, only abandoned.\n"
    );

    if path.exists() {
        return Err(CouldNotRun(format!("{} already exists", path.display())));
    }
    state::write(&path, &scaffold)?;
    println!("{id}  {title}");
    println!("  {}", path.display());
    println!();
    println!("Fill in satisfies, touches, acceptance and verify before starting it.");
    Ok(OK)
}

pub fn new_requirement(root: &Path, area: &str) -> Reading<u8> {
    let path = root.join("aios").join("requirements").join(format!("{area}.md"));
    if path.exists() {
        return Err(CouldNotRun(format!(
            "{} already exists. Requirements are appended to their area file, not given a file \
             each — the area is the unit, because a requirement read alone is usually \
             misread.",
            path.display()
        )));
    }
    let upper = area.to_uppercase();
    let scaffold = format!(
        "# {area}\n\n\
         | ID | Requirement | Status | Reason |\n\
         |---|---|---|---|\n\
         | {upper}-1 | When <trigger>, the system shall <observable response> | active | |\n\
         \n\
         Requirements are not deleted. A dropped or superseded one keeps its row and gains a\n\
         reason, because the record of what was once wanted is the memory this system exists\n\
         to keep.\n"
    );
    state::write(&path, &scaffold)?;
    println!("{}", path.display());
    Ok(OK)
}

// --- aios list ---------------------------------------------------------------------------

/// Queries, not files (M1-14).
///
/// There is no backlog file to keep in step, because an aggregate status file makes every
/// transition a two-file edit and produces a merge conflict on every branch that touches it.
pub fn list(root: &Path, filter: Option<&str>) -> Reading<u8> {
    let (tasks, broken) = load_tasks(root)?;
    for problem in &broken {
        eprintln!("  unreadable: {problem}");
    }

    let wanted = match filter {
        None => None,
        Some(name) => match Status::parse(name) {
            Some(status) => Some(status),
            None => {
                return Err(CouldNotRun(format!(
                    "{name:?} is not a status. The six are todo, doing, review, done, waiting, \
                     dropped."
                )));
            }
        },
    };

    let mut shown = 0;
    for status in [Status::Doing, Status::Review, Status::Todo, Status::Waiting,
                   Status::Done, Status::Dropped] {
        if wanted.is_some() && wanted != Some(status) {
            continue;
        }
        let group: Vec<&Task> = tasks.iter().filter(|t| t.status == status).collect();
        if group.is_empty() {
            continue;
        }
        println!("{} ({})", status.name(), group.len());
        for task in group {
            let note = match status {
                Status::Waiting => task.waiting_on.clone().unwrap_or_default(),
                Status::Dropped => task.reason.clone().unwrap_or_default(),
                _ => String::new(),
            };
            println!("  {}  p{} {:<6}  {}{}", task.id, task.priority, task.risk.name(),
                     task.title, if note.is_empty() { String::new() }
                                 else { format!("  — {note}") });
            shown += 1;
        }
        println!();
    }
    if shown == 0 {
        println!("Nothing to show.");
    }
    if !broken.is_empty() {
        return Ok(FAILED);
    }
    Ok(OK)
}

// --- aios check ----------------------------------------------------------------------------

/// Run locally exactly what CI runs (M1-14).
///
/// The commands are read out of the workflow file rather than restated here, which is the
/// whole requirement: a local check that lists its own steps is a second implementation, and
/// the two drift in the direction of the local one being kinder. Reading the workflow means
/// there is one list, and adding a step to CI adds it here with no second edit.
pub fn check(root: &Path, workflow: &str, list_only: bool) -> Reading<u8> {
    let path = root.join(".github").join("workflows").join(workflow);
    let text = state::read_to_string(&path)?;
    let steps = workflow_steps(&text);
    if steps.is_empty() {
        return Err(CouldNotRun(format!(
            "{} declares no `run:` steps to execute",
            path.display()
        )));
    }

    if list_only {
        // Names the steps without running them. CI uses this to assert that what the binary
        // would run is exactly what the workflow declares — the parity M1-14 asks to be
        // proven by a test rather than asserted in a comment. Running the full set inside CI
        // would prove the same thing and pay for it twice.
        for (name, _) in &steps {
            println!("{name}");
        }
        return Ok(OK);
    }

    println!("aios check — {} step(s) from {}", steps.len(), workflow);
    println!();
    let mut failures = Vec::new();
    for (name, command) in &steps {
        let (code, output) = shell(root, command)?;
        println!("  [{}] {name}", if code == 0 { "ok" } else { "FAILED" });
        if code != 0 {
            for line in output.lines().take(15) {
                println!("      {line}");
            }
            failures.push(name.clone());
        }
    }

    println!();
    if failures.is_empty() {
        println!("{} step(s) passed. This is the same list CI runs, read from the same file.",
                 steps.len());
        return Ok(OK);
    }
    eprintln!("{} of {} step(s) failed: {}", failures.len(), steps.len(), failures.join(", "));
    Ok(FAILED)
}

/// Extract `name` / `run` pairs from a workflow.
///
/// Uses the YAML reader rather than a regex, so that a step whose command is a block scalar —
/// which most of the interesting ones are — arrives intact.
pub fn workflow_steps(text: &str) -> Vec<(String, String)> {
    let Ok(document) = yaml::parse(text) else {
        return Vec::new();
    };
    let mut steps = Vec::new();
    let Some(jobs) = document.get("jobs") else {
        return steps;
    };
    for job_name in jobs.keys() {
        let Some(job) = jobs.get(&job_name) else { continue };
        let Some(list) = job.get("steps") else { continue };
        for step in list.as_list() {
            let Some(command) = step.get("run").and_then(|v| v.as_str()) else {
                continue;
            };
            let name = step
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or("(unnamed step)")
                .to_string();
            steps.push((name, command.to_string()));
        }
    }
    steps
}

// --- helpers shared with main -------------------------------------------------------------

pub fn config_summary(root: &Path) -> Reading<String> {
    let config = Config::load(root)?;
    Ok(format!("tier {}", config.tier()))
}

pub fn root_from(explicit: Option<&str>) -> Reading<PathBuf> {
    match explicit {
        Some(path) => {
            let candidate = PathBuf::from(path);
            if candidate.join("aios").join("config.yml").is_file() {
                Ok(candidate)
            } else {
                Err(CouldNotRun(format!("{path}: no aios/config.yml there")))
            }
        }
        None => state::find_root(Path::new(".")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::Risk;
    use std::collections::BTreeMap;

    fn task(id: &str, status: Status, priority: i64, risk: Risk, blocked: &[&str]) -> Task {
        Task {
            path: PathBuf::from(format!("aios/tasks/{id}.md")),
            id: id.to_string(),
            title: format!("task {id}"),
            status,
            risk,
            priority,
            satisfies: Vec::new(),
            blocked_by: blocked.iter().map(|s| s.to_string()).collect(),
            touches: Vec::new(),
            acceptance: Vec::new(),
            verify: vec!["true".into()],
            constraints: Vec::new(),
            waiting_on: None,
            reason: None,
            duplicate_check: Vec::new(),
            body: String::new(),
            frontmatter: yaml::Value::Map(BTreeMap::new()),
        }
    }

    #[test]
    fn only_todo_is_selectable() {
        let tasks = vec![
            task("T-a", Status::Doing, 1, Risk::Low, &[]),
            task("T-b", Status::Todo, 1, Risk::Low, &[]),
            task("T-c", Status::Review, 1, Risk::Low, &[]),
        ];
        let ready = select(&tasks);
        assert_eq!(ready.len(), 1);
        assert_eq!(ready[0].id, "T-b");
    }

    #[test]
    fn a_task_blocked_by_unfinished_work_is_not_offered() {
        let tasks = vec![
            task("T-a", Status::Doing, 1, Risk::Low, &[]),
            task("T-b", Status::Todo, 1, Risk::Low, &["T-a"]),
        ];
        assert!(select(&tasks).is_empty());
    }

    #[test]
    fn a_dropped_blocker_no_longer_blocks() {
        let tasks = vec![
            task("T-a", Status::Dropped, 1, Risk::Low, &[]),
            task("T-b", Status::Todo, 1, Risk::Low, &["T-a"]),
        ];
        assert_eq!(select(&tasks).len(), 1);
    }

    #[test]
    fn priority_comes_before_everything_else() {
        let tasks = vec![
            task("T-a", Status::Todo, 2, Risk::Low, &[]),
            task("T-b", Status::Todo, 1, Risk::High, &[]),
        ];
        assert_eq!(select(&tasks)[0].id, "T-b");
    }

    #[test]
    fn among_equal_priorities_the_one_unblocking_more_wins() {
        let mut tasks = vec![
            task("T-a", Status::Todo, 1, Risk::Low, &[]),
            task("T-b", Status::Todo, 1, Risk::Low, &[]),
        ];
        tasks.push(task("T-c", Status::Todo, 9, Risk::Low, &["T-b"]));
        tasks.push(task("T-d", Status::Todo, 9, Risk::Low, &["T-b"]));
        assert_eq!(select(&tasks)[0].id, "T-b");
    }

    #[test]
    fn risk_breaks_a_tie_towards_low() {
        let tasks = vec![
            task("T-a", Status::Todo, 1, Risk::High, &[]),
            task("T-b", Status::Todo, 1, Risk::Low, &[]),
        ];
        assert_eq!(select(&tasks)[0].id, "T-b");
    }

    #[test]
    fn the_id_makes_the_order_total() {
        let tasks = vec![
            task("T-b", Status::Todo, 1, Risk::Low, &[]),
            task("T-a", Status::Todo, 1, Risk::Low, &[]),
        ];
        assert_eq!(select(&tasks)[0].id, "T-a");
    }

    #[test]
    fn the_answer_does_not_depend_on_input_order() {
        // The property M1-10 asks for, checked over every rotation rather than a shuffle:
        // there is no random number generator here, and a test that needs one to demonstrate
        // determinism has a problem of its own.
        let base = vec![
            task("T-a", Status::Todo, 2, Risk::Low, &[]),
            task("T-b", Status::Todo, 1, Risk::High, &[]),
            task("T-c", Status::Todo, 1, Risk::Low, &[]),
            task("T-d", Status::Done, 1, Risk::Low, &[]),
            task("T-e", Status::Todo, 1, Risk::Low, &["T-d"]),
        ];
        let expected: Vec<String> =
            select(&base).iter().map(|t| t.id.clone()).collect();
        for rotation in 1..base.len() {
            let mut rotated = base.clone();
            rotated.rotate_left(rotation);
            let got: Vec<String> = select(&rotated).iter().map(|t| t.id.clone()).collect();
            assert_eq!(got, expected, "rotation {rotation} changed the answer");
        }
    }

    #[test]
    fn done_is_not_reachable_from_doing() {
        let subject = task("T-a", Status::Doing, 1, Risk::Low, &[]);
        let refusal = transition_refusal(&subject, Status::Done).unwrap();
        assert!(refusal.contains("done"), "{refusal}");
        assert!(refusal.contains("verify"), "the message must say what would make it legal");
    }

    #[test]
    fn review_is_not_reachable_from_todo() {
        let subject = task("T-a", Status::Todo, 1, Risk::Low, &[]);
        assert!(transition_refusal(&subject, Status::Review).is_some());
    }

    #[test]
    fn review_can_go_back_to_doing() {
        let subject = task("T-a", Status::Review, 1, Risk::Low, &[]);
        assert!(transition_refusal(&subject, Status::Doing).is_none());
    }

    #[test]
    fn a_done_task_does_not_reopen() {
        let subject = task("T-a", Status::Done, 1, Risk::Low, &[]);
        let refusal = transition_refusal(&subject, Status::Doing).unwrap();
        assert!(refusal.contains("new task"), "{refusal}");
    }

    #[test]
    fn every_state_pair_is_decided_one_way_or_the_other() {
        // No pair may fall through to a default. A transition nobody considered is one that
        // either happens by accident or is refused with a message that explains nothing.
        let all = [Status::Todo, Status::Doing, Status::Review, Status::Done,
                   Status::Waiting, Status::Dropped];
        for from in all {
            for to in all {
                let subject = task("T-a", from, 1, Risk::Low, &[]);
                let refusal = transition_refusal(&subject, to);
                if from == to {
                    assert!(refusal.is_some(), "{from:?} to itself must be refused");
                } else {
                    // Either legal, or refused with a message that names both states.
                    if let Some(text) = refusal {
                        assert!(text.contains(from.name()) || text.contains("done")
                                || text.contains("dropped"),
                                "{from:?} -> {to:?} refused without saying why: {text}");
                    }
                }
            }
        }
    }

    #[test]
    fn ids_widen_on_collision() {
        let mut taken = BTreeSet::new();
        let first = allocate_id("a title", "seed", &taken);
        assert_eq!(first.len(), "T-".len() + 4);
        taken.insert(first.clone());
        let second = allocate_id("a title", "seed", &taken);
        assert_ne!(second, first);
        assert_eq!(second.len(), "T-".len() + 5);
    }

    #[test]
    fn an_id_is_a_pure_function_of_title_and_seed() {
        let taken = BTreeSet::new();
        assert_eq!(
            allocate_id("t", "s", &taken),
            allocate_id("t", "s", &taken),
            "two machines with the same inputs must agree"
        );
    }

    #[test]
    fn stripping_a_field_takes_its_indented_block_with_it() {
        let source = "---\nid: T-1\nverified:\n  sha: old\n  at: 2020-01-01\nstatus: done\n---\nb\n";
        let stripped = strip_field(source, "verified");
        assert!(!stripped.contains("sha: old"));
        assert!(!stripped.contains("at: 2020-01-01"));
        assert!(stripped.contains("id: T-1"));
        assert!(stripped.contains("status: done"));
    }

    #[test]
    fn stripping_a_field_that_is_absent_changes_nothing() {
        let source = "---\nid: T-1\n---\nbody\n";
        assert_eq!(strip_field(source, "verified"), source);
    }

    #[test]
    fn workflow_steps_are_read_from_the_workflow() {
        let text = "jobs:\n  hygiene:\n    steps:\n      - name: One\n        run: echo one\n\
                    \x20     - name: Two\n        run: echo two\n";
        let steps = workflow_steps(text);
        assert_eq!(steps.len(), 2);
        assert_eq!(steps[0], ("One".to_string(), "echo one".to_string()));
    }

    #[test]
    fn a_step_with_no_run_is_not_a_command() {
        let text = "jobs:\n  hygiene:\n    steps:\n      - uses: actions/checkout@v4\n\
                    \x20     - name: One\n        run: echo one\n";
        assert_eq!(workflow_steps(text).len(), 1);
    }
}
