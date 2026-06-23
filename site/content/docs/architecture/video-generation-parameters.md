---
title: Video Generation Parameters
description: "Current parameter flow for storyboard studio video generation."
---

# Video Generation Parameters

## Scope

Storyboard Studio owns video generation parameters. The preparation page may extract or suggest camera language, but the final video generation request reads the current values from `ShotDetail`.

## Camera Language

The Studio camera language panel writes these fields directly to `ShotDetail`:

- `camera_shot`
- `angle`
- `movement`
- `duration`

The video prompt pack exposes the same fields through `pack.camera` and flat template variables. Default video prompts include camera language and duration, so changes made in Studio participate in prompt preview and task submission.

## Duration

The current Studio duration range is 3 to 15 seconds, integer seconds only.

Before a video task is created, backend service code normalizes `ShotDetail.duration` into the same 3-15 second range. This keeps old records, imported data, or direct API writes from bypassing the UI range.

For Aliyun Bailian HappyHorse video models (`happyhorse-1.0-t2v`, `happyhorse-1.0-i2v`, `happyhorse-1.0-r2v`), the adapter sends the normalized value as `parameters.duration`. HappyHorse duration is not mapped to the old discrete set of `2 / 3 / 5 / 10`; it follows the official 3-15 second integer range.

## Ratio And Resolution

The Studio sends the effective video ratio explicitly with each video task request. Video resolution is submitted as a profile:

- `standard` maps to 720p style output where supported.
- `high` maps to 1080p style output where supported.

Provider adapters are responsible for translating these normalized business parameters into provider-specific payload fields.
