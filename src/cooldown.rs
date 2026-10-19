// Copyright 2026 The Sashiko Authors
// SPDX-License-Identifier: Apache-2.0

//! Bounded publication policy. This module performs no I/O or accounting.

use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};

/// Resource ceilings, not defaults or deployment recommendations.
pub const MAX_WINDOW_SECONDS: u32 = 31 * 86400;
pub const MAX_EXTRA_SECONDS: u32 = 7 * 86400;
pub const MAX_HISTORY_ROWS: u32 = 4096;
pub const MAX_SERIES_PARTS: u32 = 1024;

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CooldownConfig {
    /// Enablement is always local to one list; omitted never means enabled.
    #[serde(default)]
    pub enabled: bool,
    pub window_seconds: Option<u32>,
    pub burst: Option<u32>,
    pub step_seconds: Option<u32>,
    pub max_extra_seconds: Option<u32>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CooldownPolicy {
    pub window_seconds: u32,
    pub burst: u32,
    pub step_seconds: u32,
    pub max_extra_seconds: u32,
}

impl CooldownConfig {
    pub fn resolve(&self, defaults: Option<&Self>) -> Result<Option<CooldownPolicy>> {
        let inherited = defaults.cloned().unwrap_or_default();
        if inherited.enabled {
            bail!("adaptive cooldown defaults cannot enable lists");
        }
        // Validate supplied numeric values even for an explicitly disabled entry.
        for (name, value, ceiling) in [
            ("window_seconds", self.window_seconds.or(inherited.window_seconds), MAX_WINDOW_SECONDS),
            ("burst", self.burst.or(inherited.burst), MAX_HISTORY_ROWS),
            ("step_seconds", self.step_seconds.or(inherited.step_seconds), MAX_EXTRA_SECONDS),
            ("max_extra_seconds", self.max_extra_seconds.or(inherited.max_extra_seconds), MAX_EXTRA_SECONDS),
        ] {
            if value.is_some_and(|v| v == 0 || v > ceiling) {
                bail!("adaptive cooldown {name} is outside supported bounds");
            }
        }
        let values = (
            self.window_seconds.or(inherited.window_seconds),
            self.burst.or(inherited.burst),
            self.step_seconds.or(inherited.step_seconds),
            self.max_extra_seconds.or(inherited.max_extra_seconds),
        );
        match values {
            (Some(window_seconds), Some(burst), Some(step_seconds), Some(max_extra_seconds)) => {
                let policy = CooldownPolicy { window_seconds, burst, step_seconds, max_extra_seconds };
                policy.validate()?;
                Ok(self.enabled.then_some(policy))
            }
            _ if self.enabled => bail!("enabled adaptive cooldown requires window, burst, step and cap"),
            _ => Ok(None),
        }
    }
}

/// Input attached to one ingestion handle, never mutable connection state.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CooldownContext {
    pub list: String,
    pub author: String,
    pub policy: CooldownPolicy,
    pub legacy_deadline: Option<i64>,
}

pub fn message_key(raw: &str) -> Result<String> {
    let key = raw.trim().trim_start_matches('<').trim_end_matches('>');
    if key.is_empty() || key.len() > 998 || key.contains(['<', '>', '\r', '\n', '\0'])
        || key.bytes().any(|b| b.is_ascii_whitespace())
    {
        bail!("unsupported adaptive cooldown Message-ID");
    }
    Ok(key.to_owned())
}

impl CooldownPolicy {
    pub fn validate(&self) -> Result<()> {
        if !(1..=MAX_WINDOW_SECONDS).contains(&self.window_seconds)
            || !(1..=MAX_EXTRA_SECONDS).contains(&self.max_extra_seconds)
            || self.burst == 0 || self.step_seconds == 0
            || self.step_seconds > self.max_extra_seconds
            || self.history_limit()? > MAX_HISTORY_ROWS
        {
            bail!("adaptive cooldown parameters exceed supported bounds");
        }
        Ok(())
    }

    pub fn history_limit(&self) -> Result<u32> {
        if self.step_seconds == 0 || self.burst == 0 {
            bail!("adaptive cooldown burst and step must be positive");
        }
        let steps = self.max_extra_seconds.div_ceil(self.step_seconds);
        self.burst.checked_sub(1).and_then(|n| n.checked_add(steps))
            .ok_or_else(|| anyhow::anyhow!("adaptive cooldown history limit overflow"))
    }

    pub fn extra_seconds(&self, prior: u32) -> Result<u32> {
        self.validate()?;
        let excess = prior.min(self.history_limit()?).saturating_add(1).saturating_sub(self.burst);
        Ok(excess.saturating_mul(self.step_seconds).min(self.max_extra_seconds))
    }

    pub fn deadline(&self, now: i64, legacy: Option<i64>, prior: u32) -> Result<Option<i64>> {
        if now < 0 {
            bail!("adaptive cooldown admission time precedes the Unix epoch");
        }
        let extra = self.extra_seconds(prior)?;
        if extra == 0 {
            return Ok(legacy);
        }
        let until = now.checked_add(i64::from(extra))
            .ok_or_else(|| anyhow::anyhow!("adaptive cooldown deadline overflow"))?;
        Ok(Some(legacy.map_or(until, |old| old.max(until))))
    }
}

/// Supports ordinary ASCII mailboxes after existing b4 author restoration.
/// Malformed or unsupported identities are explicit errors, never shared keys.
pub fn author_key(raw: &str) -> Result<String> {
    if raw.len() > 1024 || raw.contains(['\r', '\n', '\0']) {
        bail!("unsupported adaptive cooldown author");
    }
    let bare = crate::email_policy::extract_bare_email(raw);
    let Some((local, domain)) = bare.split_once('@') else {
        bail!("adaptive cooldown author is not a mailbox");
    };
    if bare.len() > 254 || !bare.is_ascii() || local.is_empty() || domain.is_empty()
        || domain.contains('@') || !domain.contains('.') || local.starts_with('.')
        || local.ends_with('.') || local.contains("..")
        || !local.bytes().all(|b| b.is_ascii_alphanumeric() || b".!#$%&'*+-/=?^_`{|}~".contains(&b))
        || !domain.split('.').all(|label| !label.is_empty() && label.len() <= 63
            && !label.starts_with('-') && !label.ends_with('-')
            && label.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-'))
    {
        bail!("unsupported adaptive cooldown mailbox");
    }
    Ok(bare)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> CooldownPolicy {
        CooldownPolicy { window_seconds: 86400, burst: 2, step_seconds: 3600, max_extra_seconds: 21600 }
    }

    #[test]
    fn hand_checked_linear_thresholds_and_composition() -> Result<()> {
        let p = fixture();
        assert_eq!(p.history_limit()?, 7);
        for (prior, expected) in [(0, 0), (1, 0), (2, 3600), (3, 7200), (7, 21600), (u32::MAX, 21600)] {
            assert_eq!(p.extra_seconds(prior)?, expected);
        }
        assert_eq!(p.deadline(100, None, 0)?, None);
        assert_eq!(p.deadline(100, Some(0), 0)?, Some(0));
        assert_eq!(p.deadline(100, Some(86500), 3)?, Some(86500));
        assert_eq!(p.deadline(100, Some(200), 3)?, Some(7300));
        assert!(p.deadline(i64::MAX, None, 3).is_err());
        assert!(p.deadline(-1, None, 0).is_err());
        Ok(())
    }

    #[test]
    fn explicit_enablement_templates_and_strict_types() -> Result<()> {
        let defaults = CooldownConfig { window_seconds: Some(86400), burst: Some(2), step_seconds: Some(3600), max_extra_seconds: Some(21600), ..Default::default() };
        assert_eq!(CooldownConfig::default().resolve(Some(&defaults))?, None);
        let enabled = CooldownConfig { enabled: true, ..Default::default() };
        assert_eq!(enabled.resolve(Some(&defaults))?, Some(fixture()));
        assert!(enabled.resolve(None).is_err());
        assert!(CooldownConfig { enabled: true, ..defaults.clone() }.resolve(Some(&enabled)).is_err());
        for text in ["enabled = 1", "burst = -1", "burst = 4294967296", "extra = 3"] {
            assert!(toml::from_str::<CooldownConfig>(text).is_err());
        }
        for bad in [CooldownPolicy { window_seconds: MAX_WINDOW_SECONDS + 1, ..fixture() }, CooldownPolicy { burst: u32::MAX, ..fixture() }, CooldownPolicy { step_seconds: 0, ..fixture() }] {
            assert!(bad.validate().is_err());
        }
        Ok(())
    }

    #[test]
    fn identity_normalization_has_no_unknown_bucket() -> Result<()> {
        assert_eq!(author_key("Dev <DEV@Example.TEST>")?, "dev@example.test");
        for bad in ["", "unknown@localhost", "a@@example.test", "a\nb@example.test", "a@-bad.test", "a b@example.test", ".a@example.test"] {
            assert!(author_key(bad).is_err(), "accepted {bad:?}");
        }
        Ok(())
    }
}
