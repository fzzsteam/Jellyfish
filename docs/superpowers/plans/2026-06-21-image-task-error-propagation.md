# Image Task Error Propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make image generation background tasks persist the provider's real error message instead of the generic "Image generation task returned no result" message.

**Architecture:** Keep the current task execution architecture. `ImageGenerationTask.run()` already captures provider exceptions into `status()["error"]`; `run_image_generation_task()` should read that error when `get_result()` returns `None`, matching the existing video runner behavior.

**Tech Stack:** Python 3.12, FastAPI service layer, async SQLAlchemy task store, pytest.

---

## File Structure

- Modify: `backend/app/services/studio/image_task_runner.py`
  - Responsibility: execute image generation tasks and persist task status/result/error.
  - Change: when `result is None`, read `await task.status()` and raise the detailed error if present.
- Modify: `backend/tests/test_image_task_runner_candidates.py`
  - Responsibility: unit coverage for image task runner candidate persistence and failure behavior.
  - Change: add one regression test that monkeypatches `ImageGenerationTask` to return no result with a real `status()["error"]`, then asserts the stored task error uses the detailed message.

---

### Task 1: Add regression coverage for detailed image task errors

**Files:**
- Modify: `backend/tests/test_image_task_runner_candidates.py`

- [ ] **Step 1: Inspect existing helper patterns**

Read `backend/tests/test_image_task_runner_candidates.py` and reuse its existing fake session/store patterns if present. Do not introduce a new test harness if the file already has one.

- [ ] **Step 2: Add a failing test**

Add a test that patches `app.services.studio.image_task_runner.ImageGenerationTask` with this fake behavior:

```python
class _FailingImageGenerationTask:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def run(self) -> None:
        return None

    async def get_result(self) -> None:
        return None

    async def status(self) -> dict[str, str]:
        return {"error": "[BailianImage] SDK failed: status=400, code=InvalidParameter, message=real provider error"}
```

The test should create a task record with a valid `user_id`, call `run_image_generation_task(task_id, run_args)`, then assert the persisted task is failed and its error equals the detailed provider error, not the generic message.

Expected assertion shape:

```python
assert row.status.value == "failed"
assert row.error == "[BailianImage] SDK failed: status=400, code=InvalidParameter, message=real provider error"
```

- [ ] **Step 3: Run the new test and verify it fails**

Run:

```bash
cd backend
uv run pytest tests/test_image_task_runner_candidates.py::<new_test_name> -q
```

Expected before implementation: FAIL because `row.error` is `"Image generation task returned no result"`.

---

### Task 2: Propagate the detailed image task error

**Files:**
- Modify: `backend/app/services/studio/image_task_runner.py`

- [ ] **Step 1: Replace the generic result-none error path**

Change this code near `run_image_generation_task()`:

```python
result = await task.get_result()
if result is None:
    raise RuntimeError("Image generation task returned no result")
```

To:

```python
result = await task.get_result()
if result is None:
    status_dict = await task.status()
    detailed_error = ""
    if isinstance(status_dict, dict):
        detailed_error = str(status_dict.get("error") or "")
    msg = detailed_error or "Image generation task returned no result"
    raise RuntimeError(msg)
```

- [ ] **Step 2: Run the focused regression test**

Run:

```bash
cd backend
uv run pytest tests/test_image_task_runner_candidates.py::<new_test_name> -q
```

Expected: PASS.

- [ ] **Step 3: Run related image runner tests**

Run:

```bash
cd backend
uv run pytest tests/test_image_task_runner_candidates.py tests/test_image_tasks_api_responses.py -q
```

Expected: PASS. If failures appear, confirm whether they are pre-existing using the same stash method documented in memory before changing unrelated code.

---

### Task 3: Final verification and commit

**Files:**
- Modify: `backend/app/services/studio/image_task_runner.py`
- Modify: `backend/tests/test_image_task_runner_candidates.py`
- Create: `docs/superpowers/plans/2026-06-21-image-task-error-propagation.md`

- [ ] **Step 1: Run frontend typecheck only if frontend changed**

No frontend change is expected. Skip `pnpm run typecheck` unless a frontend file changes.

- [ ] **Step 2: Check git diff**

Run:

```bash
git diff --stat HEAD
git diff HEAD -- backend/app/services/studio/image_task_runner.py backend/tests/test_image_task_runner_candidates.py
```

Expected: only the detailed error propagation and one focused test, plus this plan file.

- [ ] **Step 3: Commit and push**

Run:

```bash
git add backend/app/services/studio/image_task_runner.py backend/tests/test_image_task_runner_candidates.py docs/superpowers/plans/2026-06-21-image-task-error-propagation.md
git commit -m "fix: propagate image generation task errors"
git push
```

Commit body must include:

```text
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

## Self-Review

- Spec coverage: Covers only problem 2, as requested. Video pre-validation is explicitly out of scope.
- Placeholder scan: No TBD/TODO placeholders. All code paths and commands are concrete.
- Type consistency: Uses existing `ImageGenerationTask.status()` dict contract and mirrors video runner logic.
