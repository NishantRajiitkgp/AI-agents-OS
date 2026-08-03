// A host project in another ecosystem, calling `aios` the way its own task runner would.
//
// This is the cross-ecosystem side of ADR-013. The Python conformance suite proves the
// contract holds; this proves the contract is *callable* from a project that shares nothing
// with the implementation — no runtime, no package manager, no build system, no knowledge of
// what the binary is written in. If this file needed to know, the contract would have failed.
//
// Deliberately dependency-free. `npm install` here would mean the proof that the OS imposes
// no runtime had itself pulled in a dependency tree.
//
// Usage: node check.mjs <path-to-aios-executable>
// Exit codes are this harness's own: 0 every assertion held, 1 one did not.

import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const executable = process.argv[2] ?? process.env.AIOS_BINARY;
if (!executable) {
  console.error("usage: node check.mjs <path-to-aios-executable>");
  process.exit(1);
}

const failures = [];
let checked = 0;

function check(description, condition, detail = "") {
  checked += 1;
  if (condition) {
    console.log(`  ok    ${description}`);
  } else {
    console.log(`  FAIL  ${description}${detail ? ` — ${detail}` : ""}`);
    failures.push(description);
  }
}

/** A scratch repository for the host project, rebuilt per scenario.
 *
 * `broken` used to write an empty file named BROKEN at the root, which no implementation
 * would ever look for — so the clause "a failing check exits 1" could not be met by the kind
 * of thing the clause is about. It now writes a task whose status is outside the state
 * machine, which the template defines and every subject must recognise to be able to fail.
 */
function scratch({ broken = false, config = true } = {}) {
  const root = mkdtempSync(join(tmpdir(), "aios-host-"));
  mkdirSync(join(root, ".git"));
  mkdirSync(join(root, "aios", "tasks"), { recursive: true });
  mkdirSync(join(root, "src", "nested"), { recursive: true });
  if (config) writeFileSync(join(root, "aios", "config.yml"), "tier: prototype\n");
  if (broken) {
    writeFileSync(join(root, "aios", "tasks", "T-0001.md"),
      "---\nid: T-0001\nstatus: nonsense\n---\n");
  }
  writeFileSync(join(root, "package.json"),
    JSON.stringify({ name: "host-project", scripts: { check: "node check.mjs" } }, null, 2));
  return root;
}

// Node has refused to spawn .cmd and .bat without a shell since a 2024 advisory. A real
// executable never needs this; a batch stand-in on Windows does, and without the fallback the
// whole harness reports every clause as violated when nothing was ever called.
const batchStandIn = process.platform === "win32" && /\.(cmd|bat)$/i.test(executable);

// The subcommand a host task runner calls. This harness invoked the executable bare until the
// first release build met it, and the binary treats being told nothing as a usage error —
// deliberately, so that a script calling it wrong hears about it. Rather than make silence
// mean "check", the tool grew something explicit to call.
const COMMAND = ["validate"];

function invoke(root, args = [], { cwd = root, env = {} } = {}) {
  // Under a shell, Node passes the command through unquoted, so a path containing spaces is
  // read as a command plus arguments. Quoting is the shell's problem, not the contract's.
  const quote = (value) => (batchStandIn && value.includes(" ") ? `"${value}"` : value);
  const result = spawnSync(quote(executable), [...COMMAND, ...args].map(quote), {
    cwd, encoding: "utf8", env: { ...process.env, ...env }, shell: batchStandIn,
  });
  if (result.error || result.status === null) {
    console.error(`\ncould not run ${executable}: ` +
      `${result.error?.message ?? "no exit status"}`);
    console.error("Nothing below this point would be a statement about the contract.");
    process.exit(2);
  }
  return result;
}

console.log(`host-project: calling ${executable}\n`);

// ADR-013 §2 — the three exit codes, and the distinction that matters.
{
  const passing = invoke(scratch());
  check("a passing check exits 0", passing.status === 0, `got ${passing.status}`);

  const failing = invoke(scratch({ broken: true }));
  check("a failing check exits 1", failing.status === 1, `got ${failing.status}`);

  const stuck = invoke(scratch({ config: false }));
  check("a check that cannot run exits 2", stuck.status === 2, `got ${stuck.status}`);

  check("pass, fail and could-not-run are three distinct codes",
    new Set([passing.status, failing.status, stuck.status]).size === 3);

  check("no reserved exit code is used",
    ![passing, failing, stuck].some((r) => r.status >= 3 && r.status <= 125));

  // The mapping a host project actually writes. Both of §2's promised readings must hold.
  check("mapping non-zero to failure is safe",
    passing.status === 0 && failing.status !== 0 && stuck.status !== 0);
}

// ADR-013 §3 — machine-readable behind a flag, streams split by role.
{
  const root = scratch();
  const human = invoke(root);
  check("the default output is not JSON", (() => {
    try { JSON.parse(human.stdout); return false; } catch { return true; }
  })());

  const machine = invoke(root, ["--format", "json"]);
  let parsed = null;
  try { parsed = JSON.parse(machine.stdout); } catch { /* reported below */ }
  check("--format json puts one parseable document on stdout", parsed !== null,
    `stdout was ${JSON.stringify(machine.stdout.slice(0, 80))}`);
  check("the verdict is readable without parsing prose", parsed?.verdict === "pass");
  // Asserted as "stdout parses and stderr is not silent", not by looking for a particular
  // diagnostic. The stand-in printed a literal `working...`, and requiring that of a subject
  // would check one implementation's wording rather than the clause.
  check("diagnostics stay off the machine-readable stdout",
    parsed !== null && machine.stderr.trim() !== "",
    `stderr was ${JSON.stringify(machine.stderr.slice(0, 80))}`);
}

// ADR-013 §4 — root discovery upward, refused rather than guessed.
{
  const root = scratch();
  const deep = invoke(root, ["--format", "json"], { cwd: join(root, "src", "nested") });
  check("invoking from a subdirectory finds the same root", deep.status === 0,
    `got ${deep.status}`);

  // The decoy carries a valid config so only root discovery separates the outcomes.
  const decoy = mkdtempSync(join(tmpdir(), "aios-decoy-"));
  mkdirSync(join(decoy, "aios"));
  writeFileSync(join(decoy, "aios", "config.yml"), "tier: prototype\n");
  const outside = invoke(root, [], { cwd: decoy });
  check("a directory with a config but no repository root is refused",
    outside.status === 2, `got ${outside.status}`);

  check("--root overrides discovery",
    invoke(root, ["--root", root], { cwd: decoy }).status === 0);
  check("AIOS_ROOT overrides discovery",
    invoke(root, [], { cwd: decoy, env: { AIOS_ROOT: root } }).status === 0);
  rmSync(decoy, { recursive: true, force: true });
}

// The claim ADR-005 makes and this file is the only thing that can check: nothing of the
// implementation's ecosystem is required to be here.
{
  const toolchain = ["cargo", "rustc", "rustup"].filter((tool) =>
    spawnSync(process.platform === "win32" ? "where" : "which", [tool]).status === 0);
  if (toolchain.length === 0) {
    check("the implementation's toolchain is absent from this machine", true);
  } else {
    console.log(`  note  toolchain present (${toolchain.join(", ")}) — runtime-free ` +
      `invocation is not proven here. Run this where it is absent.`);
  }
  check("this host project has no dependencies of its own",
    !existsSync(join(process.cwd(), "node_modules")));
}

console.log(`\n${checked - failures.length}/${checked} held.`);
if (failures.length > 0) {
  console.error(`${failures.length} contract violation(s).`);
  process.exit(1);
}
