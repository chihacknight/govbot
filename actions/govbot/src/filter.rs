use serde_json::Value;

/// Filter alias type
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FilterAlias {
    Default,
    None,
}

impl From<&str> for FilterAlias {
    fn from(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "default" => FilterAlias::Default,
            "none" => FilterAlias::None,
            _ => FilterAlias::Default, // Default fallback
        }
    }
}

/// Filter result indicating whether an entry should be kept
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FilterResult {
    Keep,
    FilterOut,
}

/// Filter trait for filtering log entries
pub trait LogFilter {
    fn should_keep(&self, entry: &Value, repo_name: &str) -> FilterResult;
}

/// Filter manager that handles different filter aliases
pub struct FilterManager {
    alias: FilterAlias,
}

impl FilterManager {
    pub fn new(alias: FilterAlias) -> Self {
        Self { alias }
    }

    /// Check if an entry should be kept
    pub fn should_keep(&self, entry: &Value, repo_name: &str) -> FilterResult {
        match self.alias {
            FilterAlias::Default => {
                // Load repo-specific filter if available
                Self::apply_repo_filter(entry, repo_name)
            }
            FilterAlias::None => {
                // No filtering - keep all entries
                FilterResult::Keep
            }
        }
    }

    /// Apply repo-specific filter if it exists
    fn apply_repo_filter(entry: &Value, repo_name: &str) -> FilterResult {
        // Map repo names to their filter modules
        match repo_name {
            "ak-legislation" => ak_legislation::default::should_keep(entry),
            "al-legislation" => al_legislation::default::should_keep(entry),
            "ar-legislation" => ar_legislation::default::should_keep(entry),
            "az-legislation" => az_legislation::default::should_keep(entry),
            "ca-legislation" => ca_legislation::default::should_keep(entry),
            "co-legislation" => co_legislation::default::should_keep(entry),
            "ct-legislation" => ct_legislation::default::should_keep(entry),
            "de-legislation" => de_legislation::default::should_keep(entry),
            "fl-legislation" => fl_legislation::default::should_keep(entry),
            "ga-legislation" => ga_legislation::default::should_keep(entry),
            "gu-legislation" => gu_legislation::default::should_keep(entry),
            "hi-legislation" => hi_legislation::default::should_keep(entry),
            "ia-legislation" => ia_legislation::default::should_keep(entry),
            "id-legislation" => id_legislation::default::should_keep(entry),
            "il-legislation" => il_legislation::default::should_keep(entry),
            "in-legislation" => in_legislation::default::should_keep(entry),
            "ks-legislation" => ks_legislation::default::should_keep(entry),
            "ky-legislation" => ky_legislation::default::should_keep(entry),
            "la-legislation" => la_legislation::default::should_keep(entry),
            "ma-legislation" => ma_legislation::default::should_keep(entry),
            "md-legislation" => md_legislation::default::should_keep(entry),
            "me-legislation" => me_legislation::default::should_keep(entry),
            "mi-legislation" => mi_legislation::default::should_keep(entry),
            "mn-legislation" => mn_legislation::default::should_keep(entry),
            "mo-legislation" => mo_legislation::default::should_keep(entry),
            "mp-legislation" => mp_legislation::default::should_keep(entry),
            "ms-legislation" => ms_legislation::default::should_keep(entry),
            "mt-legislation" => mt_legislation::default::should_keep(entry),
            "nc-legislation" => nc_legislation::default::should_keep(entry),
            "nd-legislation" => nd_legislation::default::should_keep(entry),
            "ne-legislation" => ne_legislation::default::should_keep(entry),
            "nh-legislation" => nh_legislation::default::should_keep(entry),
            "nj-legislation" => nj_legislation::default::should_keep(entry),
            "nm-legislation" => nm_legislation::default::should_keep(entry),
            "nv-legislation" => nv_legislation::default::should_keep(entry),
            "ny-legislation" => ny_legislation::default::should_keep(entry),
            "oh-legislation" => oh_legislation::default::should_keep(entry),
            "ok-legislation" => ok_legislation::default::should_keep(entry),
            "or-legislation" => or_legislation::default::should_keep(entry),
            "pa-legislation" => pa_legislation::default::should_keep(entry),
            "pr-legislation" => pr_legislation::default::should_keep(entry),
            "ri-legislation" => ri_legislation::default::should_keep(entry),
            "sc-legislation" => sc_legislation::default::should_keep(entry),
            "sd-legislation" => sd_legislation::default::should_keep(entry),
            "tn-legislation" => tn_legislation::default::should_keep(entry),
            "tx-legislation" => tx_legislation::default::should_keep(entry),
            "usa-legislation" => usa_legislation::default::should_keep(entry),
            "ut-legislation" => ut_legislation::default::should_keep(entry),
            "va-legislation" => va_legislation::default::should_keep(entry),
            "vi-legislation" => vi_legislation::default::should_keep(entry),
            "vt-legislation" => vt_legislation::default::should_keep(entry),
            "wa-legislation" => wa_legislation::default::should_keep(entry),
            "wi-legislation" => wi_legislation::default::should_keep(entry),
            "wv-legislation" => wv_legislation::default::should_keep(entry),
            "wy-legislation" => wy_legislation::default::should_keep(entry),
            _ => FilterResult::Keep, // No filter for this repo yet
        }
    }
}

// Include filter modules using include! macro
// Paths are relative to src/filter.rs, so filters/ is at src/filters/
mod ak_legislation {
    pub mod default {
        include!("filters/ak-legislation/default.rs");
    }
}
mod al_legislation {
    pub mod default {
        include!("filters/al-legislation/default.rs");
    }
}
mod ar_legislation {
    pub mod default {
        include!("filters/ar-legislation/default.rs");
    }
}
mod az_legislation {
    pub mod default {
        include!("filters/az-legislation/default.rs");
    }
}
mod ca_legislation {
    pub mod default {
        include!("filters/ca-legislation/default.rs");
    }
}
mod co_legislation {
    pub mod default {
        include!("filters/co-legislation/default.rs");
    }
}
mod ct_legislation {
    pub mod default {
        include!("filters/ct-legislation/default.rs");
    }
}
mod de_legislation {
    pub mod default {
        include!("filters/de-legislation/default.rs");
    }
}
mod fl_legislation {
    pub mod default {
        include!("filters/fl-legislation/default.rs");
    }
}
mod ga_legislation {
    pub mod default {
        include!("filters/ga-legislation/default.rs");
    }
}
mod gu_legislation {
    pub mod default {
        include!("filters/gu-legislation/default.rs");
    }
}
mod hi_legislation {
    pub mod default {
        include!("filters/hi-legislation/default.rs");
    }
}
mod ia_legislation {
    pub mod default {
        include!("filters/ia-legislation/default.rs");
    }
}
mod id_legislation {
    pub mod default {
        include!("filters/id-legislation/default.rs");
    }
}
mod il_legislation {
    pub mod default {
        include!("filters/il-legislation/default.rs");
    }
}
mod in_legislation {
    pub mod default {
        include!("filters/in-legislation/default.rs");
    }
}
mod ks_legislation {
    pub mod default {
        include!("filters/ks-legislation/default.rs");
    }
}
mod ky_legislation {
    pub mod default {
        include!("filters/ky-legislation/default.rs");
    }
}
mod la_legislation {
    pub mod default {
        include!("filters/la-legislation/default.rs");
    }
}
mod ma_legislation {
    pub mod default {
        include!("filters/ma-legislation/default.rs");
    }
}
mod md_legislation {
    pub mod default {
        include!("filters/md-legislation/default.rs");
    }
}
mod me_legislation {
    pub mod default {
        include!("filters/me-legislation/default.rs");
    }
}
mod mi_legislation {
    pub mod default {
        include!("filters/mi-legislation/default.rs");
    }
}
mod mn_legislation {
    pub mod default {
        include!("filters/mn-legislation/default.rs");
    }
}
mod mo_legislation {
    pub mod default {
        include!("filters/mo-legislation/default.rs");
    }
}
mod mp_legislation {
    pub mod default {
        include!("filters/mp-legislation/default.rs");
    }
}
mod ms_legislation {
    pub mod default {
        include!("filters/ms-legislation/default.rs");
    }
}
mod mt_legislation {
    pub mod default {
        include!("filters/mt-legislation/default.rs");
    }
}
mod nc_legislation {
    pub mod default {
        include!("filters/nc-legislation/default.rs");
    }
}
mod nd_legislation {
    pub mod default {
        include!("filters/nd-legislation/default.rs");
    }
}
mod ne_legislation {
    pub mod default {
        include!("filters/ne-legislation/default.rs");
    }
}
mod nh_legislation {
    pub mod default {
        include!("filters/nh-legislation/default.rs");
    }
}
mod nj_legislation {
    pub mod default {
        include!("filters/nj-legislation/default.rs");
    }
}
mod nm_legislation {
    pub mod default {
        include!("filters/nm-legislation/default.rs");
    }
}
mod nv_legislation {
    pub mod default {
        include!("filters/nv-legislation/default.rs");
    }
}
mod ny_legislation {
    pub mod default {
        include!("filters/ny-legislation/default.rs");
    }
}
mod oh_legislation {
    pub mod default {
        include!("filters/oh-legislation/default.rs");
    }
}
mod ok_legislation {
    pub mod default {
        include!("filters/ok-legislation/default.rs");
    }
}
mod or_legislation {
    pub mod default {
        include!("filters/or-legislation/default.rs");
    }
}
mod pa_legislation {
    pub mod default {
        include!("filters/pa-legislation/default.rs");
    }
}
mod pr_legislation {
    pub mod default {
        include!("filters/pr-legislation/default.rs");
    }
}
mod ri_legislation {
    pub mod default {
        include!("filters/ri-legislation/default.rs");
    }
}
mod sc_legislation {
    pub mod default {
        include!("filters/sc-legislation/default.rs");
    }
}
mod sd_legislation {
    pub mod default {
        include!("filters/sd-legislation/default.rs");
    }
}
mod tn_legislation {
    pub mod default {
        include!("filters/tn-legislation/default.rs");
    }
}
mod tx_legislation {
    pub mod default {
        include!("filters/tx-legislation/default.rs");
    }
}
mod usa_legislation {
    pub mod default {
        include!("filters/usa-legislation/default.rs");
    }
}
mod ut_legislation {
    pub mod default {
        include!("filters/ut-legislation/default.rs");
    }
}
mod va_legislation {
    pub mod default {
        include!("filters/va-legislation/default.rs");
    }
}
mod vi_legislation {
    pub mod default {
        include!("filters/vi-legislation/default.rs");
    }
}
mod vt_legislation {
    pub mod default {
        include!("filters/vt-legislation/default.rs");
    }
}
mod wa_legislation {
    pub mod default {
        include!("filters/wa-legislation/default.rs");
    }
}
mod wi_legislation {
    pub mod default {
        include!("filters/wi-legislation/default.rs");
    }
}
mod wv_legislation {
    pub mod default {
        include!("filters/wv-legislation/default.rs");
    }
}
mod wy_legislation {
    pub mod default {
        include!("filters/wy-legislation/default.rs");
    }
}
