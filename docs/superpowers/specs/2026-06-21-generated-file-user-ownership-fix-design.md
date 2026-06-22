# Generated File User Ownership Fix

## Problem

After applying the user-isolation migration, image generation fails while inserting a `FileItem` because `create_file_from_url_or_b64()` does not assign the required `user_id`. Video generation uses the same helper and has the same latent defect.

The async business runner catches the persistence error and marks the generation task as failed, but returns normally. `AbstractAsyncDelegatingExecutor` therefore logs the same execution as succeeded, so Celery completion and the persisted task status disagree.

## Design

Generated files must inherit ownership from `GenerationTask.user_id`, not from request payload data. Image and video runners will load the task record from their task store, require a non-empty owner, and pass that owner through persistence helpers to `create_file_from_url_or_b64()`.

`create_file_from_url_or_b64()` will require a `user_id` keyword argument and always assign it to the new `FileItem`. Making the argument mandatory prevents future callers from silently creating unowned files. Both current callers—image persistence and generated-video persistence—will be updated.

The async delegating executor will inspect the persisted task status after the runner returns. It will log success only for `succeeded`, cancellation only for `cancelled`, and raise for `failed` or any non-terminal status. This preserves the business runner's detailed error handling while ensuring Celery and task-event logs reflect the stored outcome.

## Error Handling

- A missing task owner is a runtime invariant violation and fails the task with a clear error.
- A runner-persisted failure is surfaced by the outer executor so the Celery task fails instead of logging success.
- Cancellation remains a normal terminal outcome and is not converted into failure.

## Testing

Regression tests will first demonstrate that generated image and video files receive the task owner. Executor tests will demonstrate that a persisted failed status cannot produce a succeeded event and that cancellation remains non-failing. Relevant backend suites and Python import/compile validation will run after the fix.

## Scope

This changes internal backend behavior only. It does not change HTTP API schemas or OpenAPI generated clients. Existing user-isolation architecture documentation already defines generated data as user-owned, so no architecture contract change is required.
