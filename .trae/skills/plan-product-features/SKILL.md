---
name: plan-product-features
description: "Analyze project ideas from a product manager perspective, identify target users and essential features, define an MVP and release roadmap, evaluate newly proposed features, and prevent feature creep. Use when planning a new product, organizing a messy project idea, deciding what users truly need, prioritizing a backlog, or determining whether a temporary feature idea belongs in the current version."
---

# Plan Product Features

Turn a project topic into a focused product plan before implementation. Optimize for a complete user outcome, not the largest feature list.

## Core Rules

- Start with the user problem, target user, and desired outcome.
- Treat features as hypotheses that solve user problems.
- Protect one complete end-to-end journey in the MVP.
- Separate `must have`, `should have`, `later`, and `reject`.
- Do not add a feature to the current version only because it sounds useful.
- State reasonable assumptions when information is missing. Ask questions only when an answer would materially change the product direction.
- Distinguish product requirements from implementation details.
- Do not begin coding unless the user explicitly asks for implementation.

## Workflow

### 1. Frame the Product

Extract or infer:

- Project topic and product type
- Target users and usage context
- User's core job to be done
- Main pain point
- Product promise
- Platform and delivery constraints
- Business or personal objective
- Current stage: idea, prototype, active development, or existing product

Write a one-sentence product definition:

> For [target user], this product helps [core outcome] by [primary mechanism], unlike [current alternative].

List assumptions separately. Do not present assumptions as confirmed facts.

### 2. Identify Real User Needs

Describe at most three primary user groups. For each group, identify:

- Situation that triggers use
- Goal they are trying to achieve
- Current workaround
- Main frustration or risk
- Evidence that would validate the need

Prefer a narrow primary user over a product that vaguely serves everyone.

### 3. Map the Core Journey

Describe the shortest path from first contact to successful outcome:

1. Entry
2. Setup or input
3. Core action
4. Result
5. Return, retention, or export

Mark any step that lacks enough functionality to let the user finish the journey.

### 4. Derive Essential Features

Include a feature in the MVP only when at least one condition is true:

- It directly enables the core user outcome.
- The end-to-end journey cannot work without it.
- It protects security, privacy, legal compliance, or data integrity.
- It is a dependency for another must-have feature.
- Removing it would make the product promise misleading.

For every proposed feature, record:

- User problem
- User story
- Why it is necessary
- Smallest useful scope
- Acceptance criteria
- Dependencies
- Main edge cases

Avoid vague feature names such as "user system" or "AI capability." Describe what users can actually accomplish.

### 5. Prioritize

Classify every feature:

- `Must`: required for the first useful end-to-end outcome
- `Should`: meaningfully improves adoption or repeated use but does not block the outcome
- `Later`: valuable after the core behavior is validated
- `Reject`: unrelated, duplicative, speculative, or too expensive for its value

When priorities are close, compare:

- Severity of the user problem
- Frequency of use
- Number of users affected
- Confidence in the need
- Product differentiation
- Delivery effort and ongoing maintenance
- Risk reduction

Do not hide uncertainty behind a numerical score. Explain the decisive tradeoff.

### 6. Build the Release Plan

Define:

- `MVP`: smallest version that delivers and measures the product promise
- `V1`: quality, trust, and retention improvements after MVP validation
- `V2+`: expansion, automation, collaboration, integrations, or scale

For the MVP, identify the next smallest development slice that can be built and tested independently.

### 7. Control New Feature Ideas

When the user introduces a new feature during development, do not merge it into the plan automatically. Evaluate it with this gate:

1. Which user and verified problem does it serve?
2. Which core journey step does it improve?
3. What evidence makes it urgent now?
4. What existing work will it delay?
5. Can a smaller experiment validate it?
6. Does it belong in `Must`, `Should`, `Later`, or `Reject`?

Change the current MVP only when the feature:

- Unblocks the core journey
- Fixes a severe security, privacy, legal, or data-loss risk
- Represents validated high-priority user demand
- Is a newly discovered dependency of a must-have feature

Otherwise, place it in the backlog with a review trigger.

### 8. Define Validation

Specify:

- One primary success metric
- Two to four supporting metrics
- Important failure or guardrail metrics
- Cheapest validation method
- What result means continue, revise, or stop

Prefer observable user behavior over opinions alone.

## Output

Use the structure in [references/product-plan-template.md](references/product-plan-template.md).

Keep the response decision-oriented. Lead with the recommended product scope, then show reasoning and deferred ideas.

For a small idea, use a compact version of the template. For an existing or complex product, include the full feature matrix and roadmap.

When reviewing a newly proposed feature, output a concise decision:

- Decision: add now, reduce scope, defer, or reject
- User problem served
- Reasoning
- Effect on current scope
- Smallest validation experiment
- Backlog review trigger

