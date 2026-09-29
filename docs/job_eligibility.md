# Job eligibility screening

`JobEligibilityGate` runs after company, duplicate, role, seniority, location,
and blocked-company checks. It runs before fit scoring and resume assignment.
This prevents a strong skills match from overriding an explicit eligibility
mismatch.

The gate currently recognizes narrow, deterministic signals for:

- postings that prohibit current or future sponsorship;
- explicit month-and-year graduation windows;
- current-student requirements;
- active clearance requirements;
- work authorization, citizenship, U.S.-person, export-control, and
  clearance-eligibility language that requires independent review.

An explicit mismatch becomes `FILTERED_OUT`. Missing candidate facts,
ambiguous seasons, alternative qualifications, and legal-status questions
become `NEEDS_REVIEW`. Preferences and clearly negated requirements do not
block a job. A `CLEAR` result means that this limited screen found no supported
unresolved requirement; it is not a comprehensive legal eligibility decision.

## Private candidate facts

The ignored `config/candidate.yaml` may contain:

```yaml
candidate:
  eligibility:
    requires_sponsorship: true  # true, false, or null
    currently_enrolled: null    # true, false, or null
    active_clearance: null      # null, none, secret, top_secret, or ts_sci
```

Immigration classification and EAD dates may be retained in the private file
for future review, but this gate does not infer enrollment, sponsorship, or
citizenship from those values. Application questions about these topics remain
behind the existing manual-review policy.
