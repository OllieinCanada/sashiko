//! Fork-only measurements injected into an ephemeral test checkout.
use std::sync::{Mutex, atomic::{AtomicBool, AtomicU64, Ordering}};
use std::time::Instant;
static ACTIVE: AtomicBool = AtomicBool::new(false);
static QUERY: AtomicU64 = AtomicU64::new(0);
static EXECUTE: AtomicU64 = AtomicU64::new(0);
static BATCH: AtomicU64 = AtomicU64::new(0);
static BEGIN_OK: AtomicU64 = AtomicU64::new(0);
static BEGIN_ERR: AtomicU64 = AtomicU64::new(0);
static SAMPLES: Mutex<Vec<(&'static str, u64)>> = Mutex::new(Vec::new());

pub fn sql<T>(kind: &'static str, value: T) -> T {
    if ACTIVE.load(Ordering::Relaxed) {
        match kind {
            "query" => &QUERY,
            "execute" => &EXECUTE,
            "execute_batch" => &BATCH,
            _ => panic!("unknown SQL API"),
        }.fetch_add(1, Ordering::Relaxed);
    }
    value
}
pub fn record(kind: &'static str, elapsed: std::time::Duration) {
    if ACTIVE.load(Ordering::Relaxed) {
        let mut samples = SAMPLES.lock().unwrap();
        assert!(samples.len() < 2_000_000, "measurement sample limit");
        samples.push((kind, elapsed.as_nanos().try_into().unwrap()));
    }
}
pub fn begin(ok: bool) {
    if ACTIVE.load(Ordering::Relaxed) {
        (if ok { &BEGIN_OK } else { &BEGIN_ERR }).fetch_add(1, Ordering::Relaxed);
    }
}
pub fn reset() {
    ACTIVE.store(false, Ordering::SeqCst);
    for value in [&QUERY, &EXECUTE, &BATCH, &BEGIN_OK, &BEGIN_ERR] {
        value.store(0, Ordering::Relaxed);
    }
    SAMPLES.lock().unwrap().clear();
    ACTIVE.store(true, Ordering::SeqCst);
}
pub struct Lane { started: Instant, acquired: Option<Instant>, enabled: bool }
impl Lane {
    pub fn new(in_transaction: bool) -> Self {
        Self { started: Instant::now(), acquired: None, enabled: !in_transaction }
    }
    pub fn acquired(&mut self) {
        if self.enabled {
            record("implicit_mutex_wait", self.started.elapsed());
            self.acquired = Some(Instant::now());
        }
    }
}
impl Drop for Lane {
    fn drop(&mut self) {
        if let Some(acquired) = self.acquired {
            record("serialized_call_hold", acquired.elapsed());
        }
    }
}
pub fn finish() -> serde_json::Value {
    ACTIVE.store(false, Ordering::SeqCst);
    let samples = SAMPLES.lock().unwrap();
    let mut timings = serde_json::Map::new();
    for kind in ["transaction_mutex_wait", "sqlite_begin_wait", "explicit_transaction_hold",
                 "implicit_mutex_wait", "serialized_call_hold"] {
        let mut selected: Vec<u64> = samples.iter().filter(|(k, _)| *k == kind).map(|(_, n)| *n).collect();
        selected.sort_unstable();
        let count = selected.len();
        let percentile = |p: usize| -> Option<u64> {
            if count == 0 { None } else { Some(selected[(count * p).div_ceil(100).saturating_sub(1)]) }
        };
        timings.insert(kind.into(), serde_json::json!({
            "count": count, "sum_ns": selected.iter().map(|n| u128::from(*n)).sum::<u128>().to_string(),
            "p50_ns": percentile(50), "p95_ns": percentile(95), "p99_ns": percentile(99),
            "max_ns": selected.last().copied()
        }));
    }
    serde_json::json!({
        "sql_api_calls": {"query": QUERY.load(Ordering::Relaxed), "execute": EXECUTE.load(Ordering::Relaxed),
                          "execute_batch": BATCH.load(Ordering::Relaxed)},
        "begin_immediate_success": BEGIN_OK.load(Ordering::Relaxed),
        "begin_immediate_failure": BEGIN_ERR.load(Ordering::Relaxed),
        "timings": timings
    })
}
