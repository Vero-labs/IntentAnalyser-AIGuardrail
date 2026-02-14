// ---------------------------------------------------------------------------------
// Intent Analyzer - High Assurance Policies
// ---------------------------------------------------------------------------------

// 1. GLOBAL SAFETY NET (Highest Priority)
// Block ANY action if the risk score is too high or the intent is critical (P0).
forbid (
    principal,
    action,
    resource
)
when {
    context.risk_score > 60 ||
    context.tier == "P0_Critical" ||
    context.tier == "P1_High" ||
    context.has_critical_signal == true
};

// 2. ROLE-BASED ACCESS CONTROL (RBAC)

// --- Recruiter ---
// Can only access recruitment and general knowledge.
permit (
    principal == Role::"recruiter",
    action in [Action::"query", Action::"summarize", Action::"generate", Action::"greet"],
    resource
)
when {
    context.domain in ["recruitment", "general_knowledge"]
};

// --- Financial Advisor ---
// Can access finance, legal, and general knowledge.
permit (
    principal == Role::"financial_advisor",
    action in [Action::"query", Action::"summarize", Action::"generate", Action::"greet"],
    resource
)
when {
    context.domain in ["finance", "general_knowledge", "legal"]
};

// --- Developer ---
// Can access technical and general knowledge. Can also modify.
permit (
    principal == Role::"developer",
    action,
    resource
)
when {
    context.domain in ["technical", "general_knowledge"]
};

// --- General ---
// Open scope (fallback role, still subject to global safety net)
permit (
    principal == Role::"general",
    action,
    resource
);
