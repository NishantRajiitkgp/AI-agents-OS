//! The `aios` entry point.
//!
//! Argument parsing is hand-rolled. See `Cargo.toml` for why there are no dependencies.
//!
//! The invocation contract this implements is ADR-013: exit 0 for pass, 1 for a check that
//! failed, 2 for a check that could not run, and the repository root discovered by walking up
//! for `.git` rather than assumed to be the working directory. The 1-versus-2 distinction is
//! the one that matters. A tool that reports "could not run" as a failure trains people to
//! ignore failures; one that reports it as a pass lets a broken check masquerade as a clean
//! one, which is the failure this repository exists to prevent.
//!
//! Compiled and tested in CI only. Every rust-lang.org host is filtered on the development
//! machine's network, so there is no local toolchain and CI is the only compiler this meets.

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
    Subcommand {
        name: "validate",
        summary: "report whether this project's state is sound, for a caller outside it",
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
    println!("  --config F   read configuration from here instead of <root>/aios/config.yml");
    println!("  --format F   json, or human when omitted, where a subcommand offers both");
    println!("  --list       for `check`: name the steps instead of running them");
    println!("  --version    print the version");
    println!("  --help       print this message");
    println!();
    println!("Exit: 0 passed, 1 failed, 2 could not run.");
}

/// Pull `--flag VALUE` out of the arguments, leaving the rest.
fn take_option(args: &mut Vec<String>, flag: &str) -> Option<String> {
    let position = args.iter().position(|a| a == flag)?;
    if position + 1 >= args.len() {
        return None;
    }
    let value = args.remove(position + 1);
    args.remove(position);
    Some(value)
}

/// An environment override, with an empty value read as absent rather than as a setting.
fn from_env(name: &str) -> Option<String> {
    env::var(name).ok().filter(|value| !value.is_empty())
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

    // ADR-013 §4 gives both overrides to the flag over the environment, so the environment is
    // consulted only where the flag left nothing. An empty variable is treated as unset: an
    // exported-but-empty AIOS_ROOT is what a shell script produces when its own lookup failed,
    // and honouring it would turn that into a refusal naming the empty string.
    let explicit_root = take_option(&mut args, "--root").or_else(|| from_env("AIOS_ROOT"));
    let explicit_config = take_option(&mut args, "--config").or_else(|| from_env("AIOS_CONFIG"));

    // ADR-013 §3 names this `--format json`, and the first build to meet the conformance suite
    // spelled it `--json`. The ADR is what a host project reads and cannot be edited to match
    // an implementation, so the implementation moved. An unrecognised value is refused rather
    // than quietly treated as human: a caller asking for a format this does not have wants an
    // error, not prose it is about to try to parse.
    let format = take_option(&mut args, "--format");

    // Each of these takes a value, and `take_option` leaves a valueless one where it lies so
    // that it is reported here rather than silently read as the subcommand's argument.
    for option in ["--root", "--config", "--format"] {
        if args.iter().any(|a| a == option) {
            eprintln!("aios {first}: {option} takes a value");
            return COULD_NOT_RUN;
        }
    }
    let json = match format.as_deref() {
        None | Some("human") => false,
        Some("json") => true,
        Some(other) => {
            eprintln!("aios {first}: unknown format {other:?}; expected human or json");
            return COULD_NOT_RUN;
        }
    };

    let root = match commands::root_from(explicit_root.as_deref()) {
        Ok(root) => root,
        Err(err) => {
            eprintln!("aios {first}: could not run: {err}");
            return COULD_NOT_RUN;
        }
    };

    // Asked once, here, rather than by each subcommand. A missing config is the textbook
    // could-not-run of ADR-013 §2 — the outcome that gets silently read as a pass — and a tool
    // that answers it in seven places answers it differently in one of them.
    let config = commands::config_path(&root, explicit_config.as_deref());
    if !config.is_file() {
        eprintln!(
            "aios {first}: could not run: no config at {}",
            config.display()
        );
        return COULD_NOT_RUN;
    }

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
        "validate" => commands::validate(&root, json),
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
        assert_eq!(take_option(&mut args, "--root"), Some("/tmp/x".to_string()));
        assert_eq!(args, vec!["next".to_string()]);
    }

    #[test]
    fn a_root_flag_with_no_value_is_not_silently_consumed() {
        let mut args = vec!["next".to_string(), "--root".to_string()];
        assert_eq!(take_option(&mut args, "--root"), None);
        assert_eq!(
            args.len(),
            2,
            "leaving it alone lets the caller report the usage error"
        );
    }

    #[test]
    fn a_flag_is_removed_once_read() {
        let mut args = vec!["--list".to_string(), "hygiene.yml".to_string()];
        assert!(take_flag(&mut args, "--list"));
        assert_eq!(args, vec!["hygiene.yml".to_string()]);
        assert!(!take_flag(&mut args, "--list"));
    }

    #[test]
    fn the_format_option_is_spelled_the_way_adr_013_spells_it() {
        // The one clause a stand-in could satisfy while the real binary did not, because a
        // stand-in is written from the ADR and the binary was written from memory of it.
        let dispatcher = include_str!("main.rs")
            .split("#[cfg(test)]")
            .next()
            .unwrap_or_default();
        assert!(
            dispatcher.contains("take_option(&mut args, \"--format\")"),
            "ADR-013 §3 is `--format json`, and it is not this repository's to renegotiate"
        );
        assert!(
            !dispatcher.contains("\"--json\""),
            "the old spelling is back, and the contract now has two readings"
        );
    }

    #[test]
    fn the_exit_codes_are_the_ones_adr_013_names() {
        assert_eq!(OK, 0);
        assert_eq!(commands::FAILED, 1);
        assert_eq!(COULD_NOT_RUN, 2);
    }
}
