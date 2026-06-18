# 🚀 阿里云百炼模型集成完整指南

> **适用场景**: Jellyfish 已部署在 SAE，需要使用阿里云百炼的 AI 模型
> **支持模型**: Qwen 3.7 Pro (文本) / wan2.7-image-pro (图片) / HappyHorse-1.0-t2v (视频)
> **预计时间**: 30 分钟完成全部配置

---

## ✅ 前置条件

### 1. 已有资源确认

- [x] Jellyfish 已部署在阿里云 SAE
- [x] OSS 对象存储已开通
- [ ] 阿里云百炼 (DashScope) 账号已开通

### 2. 开通百炼平台（如果还没有）

```bash
# 访问：https://bailian.console.aliyun.com/
# 登录后 → 开通服务（通常需要实名认证）
# 开通后获取 API Key
```

---

## 🔧 Phase 1: 文本模型配置 (Qwen 3.7 Pro)

**耗时**: 5 分钟 | **难度**: ⭐ 简单

文本模型通过 **DashScope OpenAI 兼容模式** 直接调用，无需额外开发！

### Step 1: 获取 DashScope API Key

```
1. 打开: https://bailian.console.aliyun.com/#/api-key
2. 点击「创建 API Key」
3. 复制生成的 Key（格式: sk-xxxxxxxxxxxx）
4. 妥善保存，不要泄露！
```

### Step 2: 配置 SAE 环境变量

在 **SAE 控制台** → 应用详情 → 环境变量管理：

```ini
# 添加环境变量：
OPENAI_API_KEY = sk-你的DashScope-API-Key
```

> 💡 **为什么叫 OPENAI_API_KEY？**
> 因为 DashScope 提供了 OpenAI 兼容模式的 API，你的代码使用 `langchain-openai` 的 `ChatOpenAI` 类调用，所以直接复用这个变量名。

### Step 3: 通过 API 创建 Provider 和 Model

部署完成后，执行以下命令（或通过 Swagger UI 操作）：

```bash
# 你的 SAE 应用地址
BASE_URL="https://your-app-id.cn-shenzhen.appserver.aliyuncs.com/api/v1"

# ===== 1. 创建阿里百炼 Provider =====
curl -X POST "${BASE_URL}/llm/providers" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "dashscope-provider",
    "name": "阿里百炼",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "sk-你的真实API-Key",
    "description": "阿里云百炼 DashScope 平台 - 支持 Qwen/WanX/HappyHorse",
    "status": "active",
    "created_by": "admin"
  }'

# ===== 2. 创建 Qwen 3.7 Pro 文本模型 =====
curl -X POST "${BASE_URL}/llm/models" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "qwen-3.7-pro",
    "name": "qwen-plus",
    "category": "text",
    "provider_id": "dashscope-provider",
    "params": {
      "temperature": 0.7,
      "max_tokens": 2048
    },
    "description": "通义千问 Qwen 3.7 Pro - 文本理解与生成",
    "created_by": "admin"
  }'

# ===== 3. 设置为默认文本模型 =====
curl -X PUT "${BASE_URL}/llm/model-settings" \
  -H "Content-Type: application/json" \
  -d '{
    "default_text_model_id": "qwen-3.7-pro"
  }'
```

### Step 4: 验证文本模型

```
1. 打开 Jellyfish 应用
2. 创建新项目 → 新建章节
3. 输入剧本内容或上传文件
4. 点击「AI 分析」或「提取分镜」
5. 如果看到分析结果 → 🎉 成功！Qwen 模型已接入
```

**可选的其他 Qwen 模型**:

| 模型名称 | 用途 | 在 create model 时填写的 name |
|---------|------|------------------------------|
| `qwen-turbo` | 快速响应、低成本 | `"name": "qwen-turbo"` |
| `qwen-plus` | 均衡性能与成本 | `"name": "qwen-plus"` |
| `qwen-max` | 最强性能 | `"name": "qwen-max"` |
| `qwen-coder` | 代码生成 | `"name": "qwen-coder-plus"` |
| `qwen-vl` | 视觉理解 | `"name": "qwen-vl-plus-latest"` |

---

## 🖼️ Phase 2: 图片模型配置 (wan2.7-image-pro)

**耗时**: 10 分钟 | **难度**: ⭐⭐ 中等

图片生成功能需要使用我们新开发的百炼适配器（代码已包含在此次更新中）。

### Step 1: 通过 API 创建图片模型

```bash
BASE_URL="https://your-app-id.cn-shenzhen.appserver.aliyuncs.com/api/v1"

# 使用同一个 Provider (dashscope-provider)，创建图片模型

# ===== 创建 wan2.7-image-pro 图片模型 =====
curl -X POST "${BASE_URL}/llm/models" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "wan2.7-image-pro",
    "name": "wan2.7-image-pro",
    "category": "image",
    "provider_id": "dashscope-provider",
    "params": {
      "size": "1024x1024",
      "n": 1
    },
    "description": "通义万相 wan2.7-image-pro - 高质量图像生成",
    "created_by": "admin"
  }'

# ===== 设置为默认图片模型 =====
curl -X PUT "${BASE_URL}/llm/model-settings" \
  -H "Content-Type: application/json" \
  -d '{
    "default_image_model_id": "wan2.7-image-pro"
  }'
```

### Step 2: 支持的其他图片模型

如果还想尝试其他图片模型，可以用同样的方式创建：

| 模型 ID (建议) | name 参数 | 特点 |
|--------------|----------|------|
| `wanx-v1` | `wanx-v1` | 通义万相 v1（稳定版）|
| `wanx2.1-t2i-turbo` | `wanx2.1-t2i-turbo` | 快速生成（便宜）|
| `wanx2.1-t2i-plus` | `wanx2.1-t2i-plus` | 高质量（推荐）|
| `wan2.7-image-pro` | `wan2.7-image-pro` | 最新最强（默认）|

### Step 3: 验证图片生成

```
1. 进入项目的某个镜头（Shot）
2. 找到「关键帧」或「参考图」区域
3. 输入提示词（Prompt），如：「一位穿着古装的女性站在樱花树下」
4. 点击「生成图片」
5. 等待几秒到十几秒
6. 如果看到生成的图片 → 🎉 成功！
```

**支持的图片尺寸**:

| 比例 | 标准分辨率 | 高清分辨率 |
|-----|----------|-----------|
| 1:1 | 1024×1024 | 1536×1536 |
| 4:3 | 1152×864 | 1536×1152 |
| 3:4 | 864×1152 | 1152×1536 |
| 16:9 | 1344×768 | - |
| 9:16 | 768×1344 | - |

---

## 🎬 Phase 3: 视频模型配置 (HappyHorse-1.0-t2v)

**耗时**: 10 分钟 | **难度**: ⭐⭐ 中等

视频生成是异步任务模式（提交任务 → 轮询等待 → 获取结果），可能需要较长时间（1-5分钟）。

### Step 1: 通过 API 创建视频模型

```bash
BASE_URL="https://your-app-id.cn-shenzhen.appserver.aliyuncs.com/api/v1"

# ===== 创建 HappyHorse 视频模型 =====
curl -X POST "${BASE_URL}/llm/models" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "happyhorse-1.0-t2v",
    "name": "happyhorse-1.0-t2v",
    "category": "video",
    "provider_id": "dashscope-provider",
    "params": {
      "duration": 5,
      "ratio": "16:9"
    },
    "description": "HappyHorse 1.0 - 文本转视频生成模型",
    "created_by": "admin"
  }'

# ===== 设置为默认视频模型 =====
curl -X PUT "${BASE_URL}/llm/model-settings" \
  -H "Content-Type: application/json" \
  -d '{
    "default_video_model_id": "happyhorse-1.0-t2v"
  }'
```

### Step 2: 验证视频生成

```
1. 进入分镜工作室 (Chapter Studio)
2. 选择一个已准备好的镜头
3. 找到「视频生成」区域
4. 输入视频描述（Prompt），如：
   「镜头从左向右平移，展示古代街道的全景，人群熙攘攘，
     街道两旁是古色古香的建筑，阳光明媚」
5. 点击「生成视频」
6. 等待 1-5 分钟（查看任务中心进度）
7. 如果看到生成的视频 → 🎉 成功！HappyHorse 已接入
```

**视频参数说明**:

| 参数 | 默认值 | 说明 | 可选值 |
|------|-------|------|--------|
| duration | 5 秒 | 视频时长 | 2-10 秒（取决于模型）|
| ratio | 16:9 | 画面比例 | 16:9, 9:16, 1:1, 4:3, 3:4 |

> ⚠️ **注意**: 视频生成是**异步任务**，需要 Celery Worker 支持。如果你的 SAE 部署跳过了 Worker（SKIP_CELERY_WORKER=true），则视频生成可能不可用。需要确保：
> 1. Redis 服务可用
> 2. Celery Worker 正常运行
> 或将 SKIP_CELERY_WORKER 设为 false

---

## 🔍 故障排查

### 问题 1: 文本模型报错 "503 Service Unavailable"

**原因**: API Key 无效或网络不通

**解决**:
```bash
# 1. 检查环境变量是否正确设置
SAE 控制台 → 环境变量 → 确认 OPENAI_API_KEY 存在且正确

# 2. 测试 API Key 是否有效
curl https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
  -H "Authorization: Bearer sk-你的Key" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-plus","messages":[{"role":"user","content":"hello"}]}'

# 3. 检查 Provider 的 base_url 是否正确
# 应该是: https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 问题 2: 图片生成失败

**错误信息**: `Unsupported provider key: aliyun_bailian`

**原因**: 代码未更新或注册表未加载

**解决**:
```bash
# 1. 确认已推送最新代码到 test 分支
git log --oneline -5
# 应该包含: "feat(sae): Add SAE deployment support..."

# 2. 重新部署 SAE
GitHub Actions → deploy-test workflow → 手动触发

# 3. 查看启动日志是否包含:
# [INFO] bootstrap_all_registries called
```

### 问题 3: 视频生成一直处于 pending 状态

**原因**: Celery Worker 未运行或 Redis 连接失败

**解决**:
```bash
# 1. 检查 Redis 配置
SAE 环境变量中是否有 REDIS_HOST？

# 2. 检查 Celery Worker 日志
# （如果有独立 Worker 实例的话）

# 3. 如果确实没有 Worker，可以暂时用同步模式测试:
# 在 config.py 中临时添加同步执行逻辑（不推荐生产使用）
```

### 问题 4: 生成结果为空

**原因**: API 返回数据解析失败

**解决**:
```bash
# 查看 SAE 应用日志
SAE 控制台 → 日志管理 → 实时日志

# 搜索关键词:
# - "[BailianImage]" - 图片相关日志
# - "[BailianVideo]" - 视频相关日志
# - "Error" 或 "Exception" - 错误信息

# 根据具体错误调整参数或检查 API Key 权限
```

### 问题 5: 百炼控制台显示"额度不足"

**原因**: 免费额度用完或未开通付费

**解决**:
```
1. 打开百炼控制台: https://bailian.console.aliyun.com/
2. 查看账户余额和用量统计
3. 开通按量付费或购买资源包
4. 不同模型的计费不同:
   - Qwen 文本: 较便宜（~0.008元/千tokens）
   - WanX 图片: ~0.08-0.5元/张
   - HappyHorse 视频: ~1-5元/个视频（取决于时长）
```

---

## 📊 完整配置速查表

### 一键复制版（所有模型一次性配齐）

```bash
#!/bin/bash
# ============================================================
#  Jellyfish + 阿里云百炼 一键配置脚本
# ============================================================

BASE_URL="https://your-app-id.cn-shenzhen.appserver.aliyuncs.com/api/v1"
API_KEY="sk-你的真实API-Key"

echo "=== 1. 创建 Provider ==="
curl -s -X POST "${BASE_URL}/llm/providers" \
  -H "Content-Type: application/json" \
  -d "{
    \"id\": \"dashscope\",
    \"name\": \"阿里百炼\",
    \"base_url\": \"https://dashscope.aliyuncs.com/compatible-mode/v1\",
    \"image_base_url\": \"https://dashscope.aliyuncs.com/compatible-mode/v1\",
    \"video_base_url\": \"https://dashscope.aliyuncs.com\",
    \"api_key\": \"${API_KEY}\",
    \"description\": \"阿里云百炼 DashScope 全能力\",
    \"status\": \"active\",
    \"created_by\": \"admin\"
  }" | jq .

echo ""
echo "=== 2. 创建文本模型 (Qwen 3.7 Pro) ==="
curl -s -X POST "${BASE_URL}/llm/models" \
  -H "Content-Type: application/json" \
  -d "{
    \"id\": \"qwen-3.7-pro\",
    \"name\": \"qwen-plus\",
    \"category\": \"text\",
    \"provider_id\": \"dashscope\",
    \"params\": {\"temperature\": 0.7, \"max_tokens\": 2048},
    \"description\": \"通义千问 Qwen 3.7 Pro\",
    \"created_by\": \"admin\"
  }" | jq .

echo ""
echo "=== 3. 创建图片模型 (wan2.7-image-pro) ==="
curl -s -X POST "${BASE_URL}/llm/models" \
  -H "Content-Type: application/json" \
  -d "{
    \"id\": \"wan2.7-image-pro\",
    \"name\": \"wan2.7-image-pro\",
    \"category\": \"image\",
    \"provider_id\": \"dashscope\",
    \"params\": {\"size\": \"1024x1024\", \"n\": 1},
    \"description\": \"通义万相 wan2.7-image-pro\",
    \"created_by\": \"admin\"
  }" | jq .

echo ""
echo "=== 4. 创建视频模型 (HappyHorse) ==="
curl -s -X POST "${BASE_URL}/llm/models" \
  -H "Content-Type: application/json" \
  -d "{
    \"id\": \"happyhorse-1.0-t2v\",
    \"name\": \"happyhorse-1.0-t2v\",
    \"category\": \"video\",
    \"provider_id\": \"dashscope\",
    \"params\": {\"duration\": 5, \"ratio\": \"16:9\"},
    \"description\": \"HappyHorse 1.0 文本转视频\",
    \"created_by\": \"admin\"
  }" | jq .

echo ""
echo "=== 5. 设置全局默认模型 ==="
curl -s -X PUT "${BASE_URL}/llm/model-settings" \
  -H "Content-Type: application/json" \
  -d "{
    \"default_text_model_id\": \"qwen-3.7-pro\",
    \"default_image_model_id\": \"wan2.7-image-pro\",
    \"default_video_model_id\": \"happyhorse-1.0-t2v\"
  }" | jq .

echo ""
echo "✅ 所有模型配置完成！"
echo ""
echo "下一步:"
echo "1. 打开 Jellyfish 应用"
echo "2. 创建项目并测试 AI 分析功能（验证 Qwen）"
echo "3. 进入镜头页面测试图片生成（验证 wan2.7）"
echo "4. 进入工作室测试视频生成（验证 HappyHorse）"
```

---

## 📝 代码变更总结

本次新增/修改的文件：

```
backend/app/core/integrations/bailian/           ← 新增目录
├── __init__.py                                   # 包导出
├── images.py                                     # 图片生成适配器 (~120行)
├── video.py                                       # 视频生成适配器 (~180行)
├── image_capabilities.py                         # 图片能力约束定义
└── video_capabilities.py                         # 视频能力约束定义

backend/app/core/integrations/
├── image_capabilities.py                          # [修改] 增加百炼调度
└── video_capabilities.py                          # [修改] 增加百炼调度

backend/app/core/tasks/
├── image_generation_tasks.py                      # [修改] 增加 BailianTask
├── video_generation_tasks.py                      # [修改] 增加 BailianTask
└── bootstrap.py                                   # [修改] 注册百炼适配器
```

**关键设计点**:

1. **兼容 OpenAI 格式** - DashScope 的 compatible-mode 让文本模型零改动即可使用
2. **异步任务模式** - 视频/图片生成都采用 Task 架构，支持轮询和取消
3. **统一接口抽象** - 通过 `ProviderConfig` 统一不同供应商的调用方式
4. **可扩展能力系统** - 每个模型可以自定义支持的尺寸、比例等约束

---

## 🎯 下一步建议

### 立即可以做的

1. ✅ **按照本文档配置三个模型**（预计 20 分钟）
2. ✅ **端到端验证**：创建项目 → 分析剧本 → 生成图片 → 生成视频
3. ✅ **记录消耗的百炼额度**，评估成本

### 本周可以优化的

1. **调参优化**：根据实际效果调整 temperature、size 等参数
2. **多模型对比**：同时配置多个模型版本，对比效果
3. **成本监控**：建立用量统计和预算预警
4. **错误重试**：增加自动重试机制应对偶尔的 API 错误

### 后续进阶方向

1. **模型路由策略**：根据任务复杂度自动选择不同模型（简单→turbo，复杂→max）
2. **缓存机制**：相同 Prompt 缓存结果，避免重复调用
3. **批量处理**：支持一次提交多个图片/视频生成任务
4. **进度回调**：WebSocket 实时推送到前端（替代当前轮询模式）

---

## 💡 最佳实践建议

### 1. Prompt 工程

**好 Prompt 示例（图片）**:
```
正向: "一位穿着唐代华服的年轻女子，手持折扇，
       站在盛开的樱花树下回眸一笑，春光明媚，
       古风摄影风格，高清细节，柔和光线"

负向（negative_prompt）: "模糊，低质量，变形，多余肢体，
                       文字，水印，暗角过重"
```

**好 Prompt 示例（视频）**:
```
"镜头缓慢推进，展示一座被云雾环绕的古刹，
 钟声悠扬传来，红墙金瓦若隐若现，
 清晨的阳光穿透云层洒下神圣的光束，
 电影质感，航拍视角转近景"
```

### 2. 成本控制

| 操作 | 预计单次成本 | 日均次数(小团队) | 月成本估算 |
|------|------------|----------------|-----------|
| 剧本分析 (Qwen turbo) | ¥0.01 | 20次 | ¥6 |
| 图片生成 (WanX) | ¥0.1-0.5 | 50次 | ¥150-750 |
| 视频生成 (HappyHorse) | ¥1-5 | 10次 | ¥300-1500 |
| **合计** | | | **¥456-2256** |

**省钱技巧**:
- 文本分析用 `qwen-turbo`（比 plus 便宜 60%）
- 图片先用低分辨率预览，满意后再出高清版
- 视频先用短片段（2-3秒），确认效果再生成完整版
- 启用 Prompt 缓存避免重复生成

### 3. 性能优化

```yaml
# 建议的并发配置:

图片生成:
  workers: 2
  timeout: 120s
  并发数: 3-5 个同时进行
  
视频生成:
  workers: 1-2 (视频更耗资源)
  timeout: 600s (最长等10分钟)
  并发数: 1-2 个同时进行
  
文本推理:
  workers: 2-4
  timeout: 60s
  并发数: 10+ (轻量级)
```

---

## 📞 技术支持

### 官方文档
- **百炼平台文档**: https://help.aliyun.com/zh/model-studio/
- **DashScope API 参考**: https://help.aliyun.com/zh/model-studio/getting-started/first-api-call-to-qwen
- **Qwen 模型列表**: https://help.aliyun.com/zh/model-studio/getting-started/models
- **WanX 图像模型**: https://help.aliyun.com/zh/model-studio/wanxiang-image-generation
- **HappyHorse 视频**: https://help.aliyun.com/zh/model-studio/video-generation

### 项目内部文档
- `AGENTS.md` - 项目规范和架构设计
- `deploy/sae/QUICKSTART.md` - SAE 部署指南
- `README.md` - 项目整体说明

---

## 🔧 代码修正历史

### v1.1 (2026-05-29) - HappyHorse 视频生成 API 修正

**修正原因**: 根据官方 API 示例代码重新校验并修正视频适配器实现。

#### 修改的文件

| 文件 | 修改内容 |
|------|---------|
| `bailian/video.py` | **4项关键修正**（见下方详情） |
| `bailian/video_capabilities.py` | 更新参数格式为 resolution (480P/720P) |

#### 关键修正点对比

| 维度 | ❌ 修改前 (推测) | ✅ **修改后 (官方确认)** |
|------|-----------------|------------------------|
| **API 端点** | `/api/v1/services/aigc/text2video/video-synthesis` | `/api/v1/services/aigc/**video-generation**/video-synthesis` |
| **请求头** | 缺少异步标识 | **必须包含: `X-DashScope-Async: enable`** |
| **分辨率参数** | `size: "1280x720"` | **`resolution: "720P"`** (或 "480P") |
| **比例支持** | 5种 (含4:3,3:4) | **仅3种: 16:9, 9:16, 1:1** |

#### 官方 API 示例（参考）

```bash
curl --location 'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis' \
    -H 'X-DashScope-Async: enable' \                    # ← 必须的头
    -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
    -H 'Content-Type: application/json' \
    -d '{
        "model": "happyhorse-1.0-t2v",
        "input": {
            "prompt": "一座由硬纸板和瓶盖搭建的微型城市，在夜晚焕发出生机..."
        },
        "parameters": {
            "resolution": "720P",     # ← 分辨率字段名
            "ratio": "16:9",          # ← 比例
            "duration": 5              # ← 时长
        }
    }'
```

#### 支持的完整参数列表

| 参数 | 类型 | 可选值 | 默认值 | 说明 |
|------|------|-------|-------|------|
| `model` | string | `happyhorse-1.0-t2v` 等 | - | 模型名称 |
| `input.prompt` | string | 文本描述 | - | 视频内容描述（必填） |
| `parameters.resolution` | string | `"480P"`, `"720P"` | `"720P"` | 输出分辨率 |
| `parameters.ratio` | string | `"16:9"`, `"9:16"`, `"1:1"` | `"16:9"` | 宽高比 |
| `parameters.duration` | int | `2`, `3`, `5`, `10` | `5` | 视频时长(秒) |

#### 响应格式

**提交任务响应**:
```json
{
  "output": {
    "task_id": "task-xxxx"
  },
  "request_id": "xxx",
  "code": "200"
}
```

**查询结果响应 (SUCCEEDED)**:
```json
{
  "output": {
    "task_status": "SUCCEEDED",
    "task_progress": 100,
    "results": [
      {"video_url": "https://xxx.mp4"}
    ]
  },
  "request_id": "xxx",
  "code": "200"
}
```

---

**最后更新时间**: 2026-05-29 (v1.1 修正版)
**适用版本**: Jellyfish v0.1.0+
**维护者**: Jellyfish Team

---

> 🎊 恭喜！现在你的 Jellyfish 已经完全接入了阿里云百炼的三大核心模型！（已按官方示例校验）
> 从文本理解到图像生成再到视频创作，全链路 AI 能力已就绪。  
> 开始创作属于你的 AI 短剧吧！🚀
