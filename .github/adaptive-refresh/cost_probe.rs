use std::collections::BTreeMap;
use std::sync::{LazyLock, Mutex};
use std::time::Instant;

#[derive(Clone, Default, serde::Serialize)]
struct Counter { calls: u64, total_ns: u64, max_ns: u64 }
static COST: LazyLock<Mutex<BTreeMap<&'static str, Counter>>> =
    LazyLock::new(|| Mutex::new(BTreeMap::new()));
pub struct Span { label: &'static str, start: Instant }
impl Span {
    pub fn new(label: &'static str) -> Self { Self { label, start: Instant::now() } }
}
impl Drop for Span {
    fn drop(&mut self) {
        let ns = u64::try_from(self.start.elapsed().as_nanos()).unwrap_or(u64::MAX);
        let mut counters = COST.lock().expect("diagnostic counter mutex");
        let value = counters.entry(self.label).or_default();
        value.calls = value.calls.saturating_add(1);
        value.total_ns = value.total_ns.saturating_add(ns);
        value.max_ns = value.max_ns.max(ns);
    }
}
pub async fn measure<F: std::future::Future>(label: &'static str, future: F) -> F::Output {
    let _span = Span::new(label);
    future.await
}
pub fn reset() { COST.lock().expect("diagnostic reset").clear(); }
pub fn snapshot() -> serde_json::Value {
    serde_json::to_value(COST.lock().expect("diagnostic snapshot").clone()).unwrap()
}
