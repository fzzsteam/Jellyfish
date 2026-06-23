---
title: Task Notification Runtime
description: "Current runtime behavior for task center and transient task notifications."
---

# Task Notification Runtime

## Task Center

The task center is the durable task surface. It merges recent server tasks with local optimistic tasks and remains available for viewing, navigation, and cancellation.

Closing or collapsing the task center only changes the panel visibility. It does not cancel tasks and does not remove task records.

## Top-Right Notifications

Top-right notifications are transient progress hints for the current page workflow.

When a user manually closes an active task notification, the same active task is not reopened by later status refreshes or unrelated page interactions. The task still remains visible in the task center.

When the task reaches a terminal status (`succeeded`, `failed`, or `cancelled`), the page may show one settled notification for the final result.

## Video Generation Polling

Storyboard Studio video generation polling continues until the backend reports a terminal task status or the component is replaced by a new task/page lifecycle. The frontend does not impose the old 120-second polling ceiling, because provider-side video generation can exceed two minutes.
