//! The `aios` entry point.
//!
//! Argument parsing is hand-rolled. See `Cargo.toml` for why there are no dependencies.
//!
//! The invocation contract this implements is ADR-013: exit 0 for pass, 1 for a check that
//! failed, 2 for a check that could not run, and the repository root discovered by walking up
//! for `aios/config.yml` rather than assumed to be the working directory. The 1-versus-2
//! distinction is the one that matters. A tool that reports "could not run" as a failure
//! trains people to ignore failures; one that reports it as a pass lets a broken check
//! masquerade as a clean one, which is the failure this repository exists to prevent.
//!
//! NOT YET COMPILED. Every rust-lang.org host is filtered on the development machine's
//! network, so there is no local toolchain and CI is the first compiler this will meet. The
//! tests below and in each module are written to be run there, and until they have been, none
//! of the tasks this implements is `done` in the sense this project means it — a state
//! reached when a named command exits zero, not a claim anybody makes.

mod commands;
mod state;
mod yaml;

use std::env;
use std::process::ExitCode;

use commands::{COULD_NOT_RUN, OK};

struct Subcommand {
    name: &'static str,
    summary: &'static str,
}

const SUBCOMMANDS: &[Subcommand] = &[
    Subcommand {
        name: "new",
        summary: "scaffold a task or requirement and allocate its ID",
    },
    Subcommand {
        name: "next",
        summary: "select the next task deterministically",
    },
    Subcommand {
        name: "start",
        summary: "move a task to doing",
    },
    Subcommand {
        name: "submit",
        summary: "move a task to review",
    },
    Subcommand {
        name: "done",
        summary: "run every verify command, then write the record",
    },
    Subcommand {
        name: "list",
        summary: "query tasks by state",
    },
    Subcommand {
        name: "check",
        summary: "run locally exactly what CI runs",
    },
];

fn print_help() {
    println!(
        "aios {} — reads and checks project state",
        env!("CARGO_PKG_VERSION")
    );
    println!();
    println!("Usage: aios <subcommand> [options]");
    println!();
    println!("Subcommands:");
    for command in SUBCOMMANDS {
        println!("  {:<8} {}", command.name, command.summary);
    }
    println!();
    println!("States: todo → doing → review → done");
    println!("        plus waiting (needs waiting_on) and dropped (needs a reason).");
    println!("        `blocked` is not a state — it is read from blocked_by.");
    println!();
    println!("  --root PATH  use this repository root instead of discovering one");
    println!("  --json       machine-readable output, where a subcommand offers it");
    println!("  --list       for `check`: name the steps instead of running them");
    println!("  --version    print the version");
    println!("  --help       print this message");
    println!();
    println!("Exit: 0 passed, 1 failed, 2 could not run.");
}

/// Pull `--root PATH` out of the arguments, leaving the rest.
fn take_root(args: &mut Vec<String>) -> Option<String> {
    let position = args.iter().position(|a| a == "--root")?;
    if position + 1 >= args.len() {
        return None;
    }
    let value = args.remove(position + 1);
    args.remove(position);
    Some(value)
}

fn take_flag(args: &mut Vec<String>, flag: &str) -> bool {
    match args.iter().position(|a| a == flag) {
        Some(position) => {
            args.remove(position);
            true
        }
        None => false,
    }
}

fn run() -> u8 {
    let mut args: Vec<String> = env::args().skip(1).collect();

    let Some(first) = args.first().cloned() else {
        // No arguments is a usage error, not a success. A tool that exits zero when told
        // nothing teaches a script that calling it wrong is fine.
        print_help();
        return COULD_NOT_RUN;
    };

    match first.as_str() {
        "--version" | "-V" => {
            println!("aios {}", env!("CARGO_PKG_VERSION"));
            return OK;
        }
        "--help" | "-h" | "help" => {
            print_help();
            return OK;
        }
        _ => {}
    }

    if !SUBCOMMANDS.iter().any(|c| c.name == first) {
        eprintln!("aios: unknown subcommand {first:?}");
        eprintln!("run `aios help` for the list");
        return COULD_NOT_RUN;
    }

    args.remove(0);
    let explicit_root = take_root(&mut args);
    let json = take_flag(&mut args, "--json");

    let root = match commands::root_from(explicit_root.as_deref()) {
        Ok(root) => root,
        Err(err) => {
            eprintln!("aios {first}: {err}");
            return COULD_NOT_RUN;
        }
    };

    let outcome = match first.as_str() {
        "new" => match args.first().map(String::as_str) {
            Some("task") => match args.get(1) {
                Some(title) => commands::new_task(&root, title),
                None => usage("aios new task \"<title>\""),
            },
            Some("req") => match args.get(1) {
                Some(area) => commands::new_requirement(&root, area),
                None => usage("aios new req <area>"),
            },
            _ => usage("aios new task \"<title>\" | aios new req <area>"),
        },
        "next" => commands::next(&root, json),
        "start" => match args.first() {
            Some(id) => commands::start(&root, id),
            None => usage("aios start <id>"),
        },
        "submit" => match args.first() {
            Some(id) => commands::submit(&root, id),
            None => usage("aios submit <id>"),
        },
        "done" => match args.first() {
            Some(id) => commands::done(&root, id),
            None => usage("aios done <id>"),
        },
        "list" => commands::list(&root, args.first().map(String::as_str)),
        "check" => {
            let list_only = take_flag(&mut args, "--list");
            let workflow = args
                .first()
                .cloned()
                .unwrap_or_else(|| "hygiene.yml".to_string());
            commands::check(&root, &workflow, list_only)
        }
        _ => unreachable!("membership was checked above"),
    };

    match outcome {
        Ok(code) => code,
        Err(err) => {
            eprintln!("aios {first}: could not run: {err}");
            COULD_NOT_RUN
        }
    }
}

fn usage(form: &str) -> state::Reading<u8> {
    Err(state::CouldNotRun(format!("usage: {form}")))
}

fn main() -> ExitCode {
    ExitCode::from(run())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn subcommand_names_are_unique() {
        for (i, command) in SUBCOMMANDS.iter().enumerate() {
            for other in &SUBCOMMANDS[i + 1..] {
                assert_ne!(command.name, other.name, "duplicate subcommand");
            }
        }
    }

    #[test]
    fn root_is_taken_with_its_value() {
        let mut args = vec![
            "next".to_string(),
            "--root".to_string(),
            "/tmp/x".to_string(),
        ];
        assert_eq!(take_root(&mut args), Some("/tmp/x".to_string()));
        assert_eq!(args, vec!["next".to_string()]);
    }

    #[test]
    fn a_root_flag_with_no_value_is_not_silently_consumed() {
        let mut args = vec!["next".to_string(), "--root".to_string()];
        assert_eq!(take_root(&mut args), None);
        assert_eq!(
            args.len(),
            2,
            "leaving it alone lets the caller report the usage error"
        );
    }

    #[test]
    fn a_flag_is_removed_once_read() {
        let mut args = vec!["--json".to_string(), "todo".to_string()];
        assert!(take_flag(&mut args, "--json"));
        assert_eq!(args, vec!["todo".to_string()]);
        assert!(!take_flag(&mut args, "--json"));
    }

    #[test]
    fn the_exit_codes_are_the_ones_adr_013_names() {
        assert_eq!(OK, 0);
        assert_eq!(commands::FAILED, 1);
        assert_eq!(COULD_NOT_RUN, 2);
    }
}
