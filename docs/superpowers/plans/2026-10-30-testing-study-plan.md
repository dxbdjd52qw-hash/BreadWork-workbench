# Testing Study Plan Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans in this session. Track steps below.

**Goal:** Add the approved automotive testing plan and remove confirmed demo records safely.
**Architecture:** Keep the current single-file frontend and FastAPI/SQLite deployment. Extend existing progress and note views; run an idempotent, backed-up data migration on the existing server.
**Tech Stack:** Vanilla JavaScript, Python standard library, SQLite.
**Spec:** `docs/superpowers/specs/2026-10-30-testing-study-design.md`

## Global Constraints

- Preserve existing layout, exam categories, real personal records, and Alibaba hosting.
- Dates: 2026-10-31 through 2026-11-27; all imported work starts incomplete.
- Use soft deletion, fixed import IDs, and a database backup before mutation.
- Do not read, publish, or overwrite server credentials.

## Review Focus

- A fresh device must create no sample records or fictional study time.
- Existing device data must survive initialization unchanged.
- Empty exam categories must not dilute automotive testing progress.
- A second import must preserve completed tasks and progress.
- Edited or unrelated personal records must not be removed as demos.

## Task 1: Existing frontend support

Files: `frontend/index.html`, `backend/static/index.html`, `tests/frontend.test.cjs`.
- [ ] Add and run failing tests for fresh initialization, existing record preservation, and progress with an empty exam track.
- [ ] Initialize empty collections; add testing subcategories; calculate overall progress from populated categories; support learning-plan notes without counting them as completed reviews.
- [ ] Mirror the frontend to backend/static and run `node --test tests/frontend.test.cjs`.

## Task 2: Plan and safe migration

Files: `docs/汽车测试开发-四周学习计划.md`, `scripts/import_testing_plan.py`, `tests/test_import_testing_plan.py`.
- [ ] Add failing tests for conservative demo recognition, idempotent import, tombstones, and backup behavior.
- [ ] Add 28 daily tasks, 4 progress milestones, 4 DDLs, and one complete learning-plan note with fixed IDs.
- [ ] Implement a dry-run default; apply transactionally after SQLite backup; never overwrite an existing import ID or chat session.
- [ ] Run Python tests and the full frontend suite.

## Task 3: Review, publish and verify

- [ ] Inspect actual server paths, source version, and record counts without printing credentials.
- [ ] Review the whole change, commit and publish the verified source to GitHub.
- [ ] Back up the actual SQLite database and static HTML, run dry-run then apply, deploy the matching static HTML atomically.
- [ ] Verify online progress, daily tasks, learning-plan note, milestones, and cloud sync. Record backup locations and preserve any unresolved ambiguous records.

## Execution notes

- User explicitly approved direct execution; implement inline without additional workflow confirmations.
- Work is isolated in a newly cloned repository on `codex/testing-study-plan`.
