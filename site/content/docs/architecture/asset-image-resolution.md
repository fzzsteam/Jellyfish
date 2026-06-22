# Asset Image Resolution

## Current Behavior

资产编辑页在模型选择下方提供资产图片分辨率档位选择。

前端提交资产图片生成任务时，会通过 `StudioImageTaskRequest.resolution_profile` 传递当前选择：

- `standard` = `1K`
- `high` = `2K`

## Bailian Mapping

百炼资产图片适配层当前将资产图片任务的分辨率档位映射为：

- `standard` -> `1024*1024`
- `high` -> `2048*2048`

该映射覆盖当前资产编辑页使用的 `qwen-image-2.0-pro` 与 `wan2.7-image-pro`。

`wan2.7-image-pro` 在纯文生图场景可支持 4K，但资产编辑页经常会携带参考图；参考图、编辑和组图场景最高按 2K 处理。因此当前 UI 不暴露 4K 档位。
