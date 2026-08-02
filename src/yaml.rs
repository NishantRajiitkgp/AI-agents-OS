//! A parser for the subset of YAML this repository's state is written in.
//!
//! Not a YAML implementation, and it should not grow into one. It reads what
//! `aios/config.yml`, the task frontmatter and the gate registry actually contain: nested
//! maps, lists, quoted and bare scalars, block scalars, comments. It does not do anchors,
//! aliases, flow maps, multi-document streams, or the several ways YAML lets a string mean a
//! boolean. Anything it does not understand is an error rather than a guess, because a state
//! file that parses differently from how it reads is the failure this whole system is built
//! to prevent.
//!
//! Hand-written because `Cargo.toml` carries no dependencies, and that constraint is load
//! bearing rather than incidental — see the comment there. A tool that blocks a merge over an
//! unvetted dependency cannot arrive with a transitive tree of its own.

use std::collections::BTreeMap;
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Scalar(String),
    List(Vec<Value>),
    Map(BTreeMap<String, Value>),
}

#[derive(Debug)]
pub struct ParseError {
    pub line: usize,
    pub message: String,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

impl Value {
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Map(map) => map.get(key),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::Scalar(s) => Some(s.as_str()),
            _ => None,
        }
    }

    /// A list, or a single scalar treated as a list of one.
    ///
    /// The leniency is deliberate and narrow. `touches: aios/bin/**` and `touches:` followed
    /// by one item mean the same thing to every human who writes either, and refusing the
    /// first would be pedantry that produces no better state file.
    pub fn as_list(&self) -> Vec<&Value> {
        match self {
            Value::List(items) => items.iter().collect(),
            Value::Scalar(_) | Value::Map(_) => vec![self],
        }
    }

    pub fn strings(&self) -> Vec<String> {
        self.as_list()
            .iter()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect()
    }

    pub fn keys(&self) -> Vec<String> {
        match self {
            Value::Map(map) => map.keys().cloned().collect(),
            _ => Vec::new(),
        }
    }

    /// The scalar as an integer, if it is one.
    ///
    /// Returns None rather than 0 for a non-number. A budget that silently reads as zero is a
    /// budget that blocks everything, and the caller should decide what a missing one means.
    pub fn as_int(&self) -> Option<i64> {
        self.as_str().and_then(|s| s.trim().parse::<i64>().ok())
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self.as_str()?.trim() {
            "true" | "True" | "yes" => Some(true),
            "false" | "False" | "no" => Some(false),
            _ => None,
        }
    }
}

struct Line {
    number: usize,
    indent: usize,
    content: String,
}

/// Strip a trailing comment that is not inside quotes.
fn strip_comment(text: &str) -> String {
    let mut out = String::new();
    let mut quote: Option<char> = None;
    let mut previous = ' ';
    for ch in text.chars() {
        match quote {
            Some(q) => {
                if ch == q {
                    quote = None;
                }
            }
            None => {
                if ch == '\'' || ch == '"' {
                    quote = Some(ch);
                } else if ch == '#' && (previous == ' ' || previous == '\t' || out.is_empty()) {
                    break;
                }
            }
        }
        out.push(ch);
        previous = ch;
    }
    out.trim_end().to_string()
}

fn unquote(text: &str) -> String {
    let trimmed = text.trim();
    let bytes: Vec<char> = trimmed.chars().collect();
    if bytes.len() >= 2 {
        let first = bytes[0];
        let last = bytes[bytes.len() - 1];
        if (first == '\'' && last == '\'') || (first == '"' && last == '"') {
            let inner: String = bytes[1..bytes.len() - 1].iter().collect();
            // Single quotes are literal in YAML apart from a doubled quote. Double quotes take
            // escapes; only the two that appear in this repository's files are handled, and
            // anything else is left alone rather than half-decoded.
            return if first == '\'' {
                inner.replace("''", "'")
            } else {
                inner.replace("\\n", "\n").replace("\\\"", "\"")
            };
        }
    }
    trimmed.to_string()
}

/// Split `key: value` at the first colon that is not inside quotes.
///
/// Necessary because the deny list is a map keyed by regexes, and those contain colons.
fn split_key(text: &str) -> Option<(String, String)> {
    let mut quote: Option<char> = None;
    let chars: Vec<char> = text.chars().collect();
    for (i, &ch) in chars.iter().enumerate() {
        match quote {
            Some(q) => {
                if ch == q {
                    quote = None;
                }
            }
            None => {
                if ch == '\'' || ch == '"' {
                    quote = Some(ch);
                } else if ch == ':' {
                    let after = chars.get(i + 1).copied();
                    // A colon only separates when followed by space or end of line. `a:b` is
                    // a scalar in YAML, and URLs and regexes depend on that.
                    if after.is_none() || after == Some(' ') || after == Some('\t') {
                        let key: String = chars[..i].iter().collect();
                        let value: String = chars[i + 1..].iter().collect();
                        return Some((unquote(&key), value.trim().to_string()));
                    }
                }
            }
        }
    }
    None
}

/// Parse an inline flow sequence: `[a, b, c]`.
///
/// Supported because the generated deny-list map is written that way and reading it back is
/// how the binary will check it. Nested flow collections are not supported.
fn parse_flow_list(text: &str) -> Option<Value> {
    let trimmed = text.trim();
    if !trimmed.starts_with('[') || !trimmed.ends_with(']') {
        return None;
    }
    let inner = &trimmed[1..trimmed.len() - 1];
    if inner.trim().is_empty() {
        return Some(Value::List(Vec::new()));
    }
    let mut items = Vec::new();
    let mut current = String::new();
    let mut quote: Option<char> = None;
    for ch in inner.chars() {
        match quote {
            Some(q) => {
                if ch == q {
                    quote = None;
                }
                current.push(ch);
            }
            None => {
                if ch == '\'' || ch == '"' {
                    quote = Some(ch);
                    current.push(ch);
                } else if ch == ',' {
                    items.push(Value::Scalar(unquote(&current)));
                    current = String::new();
                } else {
                    current.push(ch);
                }
            }
        }
    }
    if !current.trim().is_empty() {
        items.push(Value::Scalar(unquote(&current)));
    }
    Some(Value::List(items))
}

fn scalar(text: &str) -> Value {
    if let Some(list) = parse_flow_list(text) {
        return list;
    }
    Value::Scalar(unquote(text))
}

fn lines_of(source: &str) -> Vec<Line> {
    let mut out = Vec::new();
    for (index, raw) in source.lines().enumerate() {
        let expanded = raw.replace('\t', "    ");
        let stripped = strip_comment(&expanded);
        if stripped.trim().is_empty() {
            continue;
        }
        if stripped.trim() == "---" || stripped.trim() == "..." {
            continue;
        }
        let indent = stripped.len() - stripped.trim_start().len();
        out.push(Line {
            number: index + 1,
            indent,
            content: stripped.trim().to_string(),
        });
    }
    out
}

/// Read a block scalar (`|`, `>`, `|-`, `>-`) starting after its header.
///
/// Reads from the raw source rather than the stripped lines, because a `#` inside a block
/// scalar is text and stripping it there would silently rewrite prose. The gate registry is
/// full of `>-` notes and several contain one.
fn block_scalar(raw: &[&str], start: usize, parent_indent: usize, folded: bool) -> (String, usize) {
    let mut collected: Vec<String> = Vec::new();
    let mut index = start;
    while index < raw.len() {
        let line = raw[index].replace('\t', "    ");
        if line.trim().is_empty() {
            collected.push(String::new());
            index += 1;
            continue;
        }
        let indent = line.len() - line.trim_start().len();
        if indent <= parent_indent {
            break;
        }
        collected.push(line.trim_end().to_string());
        index += 1;
    }
    while collected.last().map(|l| l.is_empty()).unwrap_or(false) {
        collected.pop();
    }
    let common = collected
        .iter()
        .filter(|l| !l.is_empty())
        .map(|l| l.len() - l.trim_start().len())
        .min()
        .unwrap_or(0);
    let body: Vec<String> = collected
        .iter()
        .map(|l| {
            if l.len() >= common {
                l[common..].to_string()
            } else {
                String::new()
            }
        })
        .collect();

    let text = if folded {
        // Folded: single newlines become spaces, blank lines become newlines.
        let mut out = String::new();
        for line in &body {
            if line.is_empty() {
                out.push('\n');
            } else {
                if !out.is_empty() && !out.ends_with('\n') {
                    out.push(' ');
                }
                out.push_str(line);
            }
        }
        out
    } else {
        body.join("\n")
    };
    (text, index)
}

/// Parse a document.
pub fn parse(source: &str) -> Result<Value, ParseError> {
    let raw: Vec<&str> = source.lines().collect();
    let lines = lines_of(source);
    let mut cursor = 0;
    let value = parse_block(&lines, &mut cursor, 0, &raw)?;
    Ok(value)
}

fn parse_block(
    lines: &[Line],
    cursor: &mut usize,
    indent: usize,
    raw: &[&str],
) -> Result<Value, ParseError> {
    if *cursor >= lines.len() {
        return Ok(Value::Map(BTreeMap::new()));
    }
    if lines[*cursor].content.starts_with("- ") || lines[*cursor].content == "-" {
        parse_list(lines, cursor, indent, raw)
    } else {
        parse_map(lines, cursor, indent, raw)
    }
}

fn parse_list(
    lines: &[Line],
    cursor: &mut usize,
    indent: usize,
    raw: &[&str],
) -> Result<Value, ParseError> {
    let mut items = Vec::new();
    while *cursor < lines.len() {
        let line = &lines[*cursor];
        if line.indent < indent {
            break;
        }
        if !(line.content.starts_with("- ") || line.content == "-") {
            break;
        }
        let rest = line.content[1..].trim().to_string();
        let item_indent = line.indent;
        *cursor += 1;

        if rest.is_empty() {
            let nested = parse_block(lines, cursor, item_indent + 1, raw)?;
            items.push(nested);
            continue;
        }

        // `- key: value` opens a map whose remaining keys are indented to where the key
        // began, which is two columns past the dash.
        if let Some((key, value)) = split_key(&rest) {
            let mut map = BTreeMap::new();
            let key_column = item_indent + 2;
            if value.is_empty() {
                let nested = parse_value_after_key(lines, cursor, key_column, raw, line.number)?;
                map.insert(key, nested);
            } else {
                map.insert(key, scalar(&value));
            }
            while *cursor < lines.len() && lines[*cursor].indent == key_column {
                let following = &lines[*cursor];
                if following.content.starts_with("- ") {
                    break;
                }
                let Some((k, v)) = split_key(&following.content) else {
                    break;
                };
                *cursor += 1;
                if v.is_empty() {
                    let nested =
                        parse_value_after_key(lines, cursor, key_column, raw, following.number)?;
                    map.insert(k, nested);
                } else if let Some(header) = block_header(&v) {
                    let (text, next) = block_scalar(raw, following.number, key_column, header);
                    map.insert(k, Value::Scalar(text));
                    skip_to_raw_line(lines, cursor, next);
                } else {
                    map.insert(k, scalar(&v));
                }
            }
            items.push(Value::Map(map));
            continue;
        }

        items.push(scalar(&rest));
    }
    Ok(Value::List(items))
}

/// `|` and `>` with their chomping indicators. Returns Some(folded) when it is one.
fn block_header(value: &str) -> Option<bool> {
    match value.trim() {
        "|" | "|-" | "|+" => Some(false),
        ">" | ">-" | ">+" => Some(true),
        _ => None,
    }
}

/// After consuming a raw block scalar, move the line cursor past everything it swallowed.
fn skip_to_raw_line(lines: &[Line], cursor: &mut usize, raw_index: usize) {
    while *cursor < lines.len() && lines[*cursor].number <= raw_index {
        *cursor += 1;
    }
}

fn parse_value_after_key(
    lines: &[Line],
    cursor: &mut usize,
    key_indent: usize,
    raw: &[&str],
    _line: usize,
) -> Result<Value, ParseError> {
    if *cursor >= lines.len() {
        return Ok(Value::Scalar(String::new()));
    }
    let next = &lines[*cursor];
    if next.indent <= key_indent && !next.content.starts_with("- ") {
        // Nothing indented under it: an empty value, which YAML calls null.
        return Ok(Value::Scalar(String::new()));
    }
    // A list may sit at the same indent as its key, which is the common style.
    if next.content.starts_with("- ") || next.content == "-" {
        if next.indent >= key_indent {
            return parse_list(lines, cursor, next.indent, raw);
        }
        return Ok(Value::Scalar(String::new()));
    }
    parse_map(lines, cursor, next.indent, raw)
}

fn parse_map(
    lines: &[Line],
    cursor: &mut usize,
    indent: usize,
    raw: &[&str],
) -> Result<Value, ParseError> {
    let mut map = BTreeMap::new();
    while *cursor < lines.len() {
        let line = &lines[*cursor];
        if line.indent < indent {
            break;
        }
        if line.indent > indent {
            return Err(ParseError {
                line: line.number,
                message: format!(
                    "indented {} where {} was expected; this parser reads a subset of YAML and \
                     will not guess at the intent",
                    line.indent, indent
                ),
            });
        }
        if line.content.starts_with("- ") {
            break;
        }
        let Some((key, value)) = split_key(&line.content) else {
            return Err(ParseError {
                line: line.number,
                message: format!("{:?} is not `key: value`", line.content),
            });
        };
        let number = line.number;
        *cursor += 1;

        if let Some(folded) = block_header(&value) {
            let (text, next) = block_scalar(raw, number, indent, folded);
            map.insert(key, Value::Scalar(text));
            skip_to_raw_line(lines, cursor, next);
            continue;
        }

        if value.is_empty() {
            let nested = parse_value_after_key(lines, cursor, indent, raw, number)?;
            map.insert(key, nested);
        } else {
            map.insert(key, scalar(&value));
        }
    }
    Ok(Value::Map(map))
}

/// Split a markdown file into its YAML frontmatter and body.
///
/// The frontmatter must open on the very first line. A file whose `---` is on line two is
/// rejected rather than searched for, because that is exactly what a byte-order mark produces
/// and treating it as frontmatter would make a BOM invisible — which it already was once, in
/// the hook incident this repository records.
pub fn frontmatter(source: &str) -> Result<(Value, String), ParseError> {
    let mut lines = source.lines();
    let Some(first) = lines.next() else {
        return Err(ParseError {
            line: 1,
            message: "file is empty".into(),
        });
    };
    if first.trim_end() != "---" {
        return Err(ParseError {
            line: 1,
            message: "no YAML frontmatter: the first line must be exactly `---`".into(),
        });
    }
    let mut header = String::new();
    let mut body = String::new();
    let mut in_body = false;
    for (index, line) in source.lines().enumerate().skip(1) {
        if !in_body && line.trim_end() == "---" {
            in_body = true;
            continue;
        }
        if in_body {
            body.push_str(line);
            body.push('\n');
        } else {
            header.push_str(line);
            header.push('\n');
        }
        let _ = index;
    }
    if !in_body {
        return Err(ParseError {
            line: source.lines().count(),
            message: "frontmatter is never closed by a second `---`".into(),
        });
    }
    Ok((parse(&header)?, body))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_a_flat_map() {
        let value = parse("id: T-950a\nstatus: doing\n").unwrap();
        assert_eq!(value.get("id").unwrap().as_str(), Some("T-950a"));
        assert_eq!(value.get("status").unwrap().as_str(), Some("doing"));
    }

    #[test]
    fn reads_a_list() {
        let value = parse("touches:\n  - aios/bin/**\n  - tests/**\n").unwrap();
        assert_eq!(
            value.get("touches").unwrap().strings(),
            vec!["aios/bin/**".to_string(), "tests/**".to_string()]
        );
    }

    #[test]
    fn a_lone_scalar_reads_as_a_list_of_one() {
        let value = parse("touches: aios/bin/**\n").unwrap();
        assert_eq!(
            value.get("touches").unwrap().strings(),
            vec!["aios/bin/**".to_string()]
        );
    }

    #[test]
    fn reads_nested_maps() {
        let value = parse("budgets:\n  task_file_lines: 60\n  root_markdown_files: 5\n").unwrap();
        let budgets = value.get("budgets").unwrap();
        assert_eq!(budgets.get("task_file_lines").unwrap().as_int(), Some(60));
    }

    #[test]
    fn reads_a_list_of_maps() {
        let source = "gates:\n  - id: one\n    class: contract\n  - id: two\n    class: report\n";
        let value = parse(source).unwrap();
        let gates = value.get("gates").unwrap().as_list();
        assert_eq!(gates.len(), 2);
        assert_eq!(gates[0].get("id").unwrap().as_str(), Some("one"));
        assert_eq!(gates[1].get("class").unwrap().as_str(), Some("report"));
    }

    #[test]
    fn a_colon_inside_a_key_does_not_split_it() {
        // The deny list is keyed by regexes, several of which contain a colon.
        let value = parse("'a(?:b|c)': ['x:*']\n").unwrap();
        assert_eq!(
            value.get("a(?:b|c)").unwrap().strings(),
            vec!["x:*".to_string()]
        );
    }

    #[test]
    fn a_colon_with_no_space_after_it_is_not_a_separator() {
        let value = parse("url: https://example.com/x\n").unwrap();
        assert_eq!(
            value.get("url").unwrap().as_str(),
            Some("https://example.com/x")
        );
    }

    #[test]
    fn a_hash_inside_quotes_is_not_a_comment() {
        let value = parse("pattern: '#!/bin/sh'\n").unwrap();
        assert_eq!(value.get("pattern").unwrap().as_str(), Some("#!/bin/sh"));
    }

    #[test]
    fn a_trailing_comment_is_removed() {
        let value = parse("tier: prototype  # for now\n").unwrap();
        assert_eq!(value.get("tier").unwrap().as_str(), Some("prototype"));
    }

    #[test]
    fn reads_a_folded_block_scalar() {
        let value = parse("note: >-\n  one line\n  and another\n").unwrap();
        assert_eq!(
            value.get("note").unwrap().as_str(),
            Some("one line and another")
        );
    }

    #[test]
    fn a_hash_inside_a_block_scalar_survives() {
        let value = parse("note: >-\n  a # b\n").unwrap();
        assert_eq!(value.get("note").unwrap().as_str(), Some("a # b"));
    }

    #[test]
    fn reads_a_literal_block_scalar() {
        let value = parse("body: |\n  first\n  second\n").unwrap();
        assert_eq!(value.get("body").unwrap().as_str(), Some("first\nsecond"));
    }

    #[test]
    fn reads_an_empty_flow_list() {
        let value = parse("mcp_servers: []\n").unwrap();
        assert_eq!(value.get("mcp_servers").unwrap().strings().len(), 0);
    }

    #[test]
    fn frontmatter_splits_header_from_body() {
        let (header, body) = frontmatter("---\nid: T-1\n---\nprose here\n").unwrap();
        assert_eq!(header.get("id").unwrap().as_str(), Some("T-1"));
        assert_eq!(body.trim(), "prose here");
    }

    #[test]
    fn frontmatter_not_on_the_first_line_is_refused() {
        // A byte-order mark produces exactly this, and it was invisible once already.
        assert!(frontmatter("\u{feff}---\nid: T-1\n---\n").is_err());
    }

    #[test]
    fn unclosed_frontmatter_is_refused() {
        assert!(frontmatter("---\nid: T-1\nno closing marker\n").is_err());
    }

    #[test]
    fn a_line_that_is_not_a_pair_is_an_error_not_a_guess() {
        assert!(parse("id: T-1\nthis is prose\n").is_err());
    }

    #[test]
    fn an_int_that_is_not_one_reads_as_none_rather_than_zero() {
        let value = parse("cap: soon\n").unwrap();
        assert_eq!(value.get("cap").unwrap().as_int(), None);
    }
}
