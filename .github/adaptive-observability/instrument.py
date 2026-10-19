"""Inject fork-only SQL API counts and writer-boundary timings."""
import re

def once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError("instrumentation anchor mismatch: " + before[:100])
    return text.replace(before, after)

def mask(source):
    chars = list(source)
    index = 0
    while index < len(source):
        start = index
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = len(source) if end < 0 else end
        elif source.startswith("/*", index):
            depth = 1
            index += 2
            while depth and index < len(source):
                if source.startswith("/*", index): depth += 1; index += 2
                elif source.startswith("*/", index): depth -= 1; index += 2
                else: index += 1
        else:
            raw = re.match(r'(?:br|r)(#*)"', source[index:])
            char = re.match(r"'(?:\\.|[^'\\\n])'", source[index:])
            if raw:
                closing = '"' + raw.group(1)
                end = source.find(closing, index + len(raw.group()))
                if end < 0: raise RuntimeError("unclosed raw string")
                index = end + len(closing)
            elif source[index] == '"':
                index += 1
                while index < len(source):
                    if source[index] == "\\": index += 2
                    elif source[index] == '"': index += 1; break
                    else: index += 1
            elif char:
                index += len(char.group())
            else:
                index += 1
                continue
        for at in range(start, index):
            if chars[at] != "\n": chars[at] = " "
    return "".join(chars)

def count_calls(source):
    code = mask(source)
    edits = []
    counts = {}
    pattern = r'\b(conn|tx_conn|tx|stmt)\s*\.\s*(query|execute|execute_batch)\s*\('
    for match in re.finditer(pattern, code):
        start = match.end()
        depth = 0
        end = start
        for end in range(start, len(code)):
            value = code[end]
            if value in "([{": depth += 1
            elif value in ")]}":
                if depth == 0: break
                depth -= 1
            elif value == "," and depth == 0: break
        else: raise RuntimeError("unclosed SQL API call")
        kind = match.group(2)
        edits.append((start, end, 'crate::db::hosted_probe::sql("' + kind + '", ' + source[start:end] + ')'))
        counts[kind] = counts.get(kind, 0) + 1
    for start, end, value in reversed(edits):
        source = source[:start] + value + source[end:]
    return source, counts

def instrument_db(source):
    source = once(source, "    _guard: tokio::sync::OwnedMutexGuard<()>,",
                  "    _guard: tokio::sync::OwnedMutexGuard<()>,\n    probe_started: Option<std::time::Instant>,")
    old = """        let guard = self.tx_lock.clone().lock_owned().await;
        let tx = self
            .tx_conn
            .transaction_with_behavior(libsql::TransactionBehavior::Immediate)
            .await?;
        Ok(DatabaseTransaction {
            tx: Some(tx),
            _guard: guard,
        })"""
    new = """        let waiting = std::time::Instant::now();
        let guard = self.tx_lock.clone().lock_owned().await;
        hosted_probe::record("transaction_mutex_wait", waiting.elapsed());
        let acquiring = std::time::Instant::now();
        let outcome = self.tx_conn.transaction_with_behavior(libsql::TransactionBehavior::Immediate).await;
        hosted_probe::record("sqlite_begin_wait", acquiring.elapsed());
        hosted_probe::begin(outcome.is_ok());
        let tx = outcome?;
        Ok(DatabaseTransaction {
            tx: Some(tx), _guard: guard,
            probe_started: Some(std::time::Instant::now()),
        })"""
    source = once(source, old, new)
    source = once(source, "    pub async fn commit(self) -> Result<()> {", "    pub async fn commit(mut self) -> Result<()> {")
    source = once(source, "    pub async fn rollback(self) -> Result<()> {", "    pub async fn rollback(mut self) -> Result<()> {")
    # Commit and explicit rollback stop at the successful SQL completion;
    # failed completion or implicit rollback is recorded by Drop instead.
    for method in ["commit", "rollback"]:
        start = source.index("    pub async fn " + method + "(")
        end = source.index("\n    }\n", start)
        chunk = source[start:end]
        chunk = once(chunk, "        Ok(())", """        if let Some(started) = self.probe_started.take() {
            hosted_probe::record("explicit_transaction_hold", started.elapsed());
        }
        Ok(())""")
        source = source[:start] + chunk + source[end:]
    source = once(source, """        if let Some(tx) = self.tx.take() {
            Self::drop_quietly(tx);
        }""", """        if let Some(tx) = self.tx.take() {
            Self::drop_quietly(tx);
        }
        if let Some(started) = self.probe_started.take() {
            hosted_probe::record("explicit_transaction_hold", started.elapsed());
        }""")
    for method in ["execute", "execute_batch", "query_returning_i64"]:
        prefix = "    pub async fn " if method != "query_returning_i64" else "    async fn "
        start = source.index(prefix + method + "(")
        end = source.index("\n    }\n", start)
        chunk = source[start:end]
        chunk = once(chunk, "        let _guard = if self.in_transaction {",
                     "        let mut lane = hosted_probe::Lane::new(self.in_transaction);\n        let _guard = if self.in_transaction {")
        anchor = "        };\n"
        pos = chunk.index(anchor, chunk.index("let _guard"))
        chunk = chunk[:pos] + chunk[pos:].replace(anchor, anchor + "        lane.acquired();\n", 1)
        source = source[:start] + chunk + source[end:]
    source, counts = count_calls(source)
    source += '\n#[cfg(feature = "server")]\n#[path = "db/hosted_probe.rs"]\npub mod hosted_probe;\n'
    return source, counts
