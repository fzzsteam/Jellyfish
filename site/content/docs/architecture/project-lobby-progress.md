---
title: Project Lobby Progress
description: "Current stage-progress rules for project cards on the lobby page."
---

# Project Lobby Progress

Project cards on the lobby page use four equal workflow stages instead of a single numeric percentage. The card progress header does not show a percentage value; completion is communicated by the four labeled stage bars.

## Stages

- Script: green when the project has chapters and the current project-stage summary is no longer waiting for raw script text.
- Storyboard: green when at least one storyboard shot has been extracted.
- Assets: green when every storyboard shot has completed preparation, represented by `shot.status = ready`.
- Video: green when every storyboard shot has a generated video file and there is no active video task for those shots.

The lobby derives these values from chapter data, shot list data, and shot runtime summaries. It does not store a separate persistent progress value for the four-stage bar.
