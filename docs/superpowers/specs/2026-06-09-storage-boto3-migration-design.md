# 对象存储 SDK 迁移：oss2 → boto3

**日期**：2026-06-09  
**状态**：已确认

## 背景

本地开发使用 RustFS（S3 兼容协议），生产环境使用阿里云 OSS。`storage.py` 当前使用 `oss2`（阿里云私有鉴权协议），RustFS 不支持该协议，导致本地上传图片时报 `invalid header: authorization`。

阿里云 OSS 支持 S3 兼容模式，因此可统一使用 `boto3` 对接两套存储。

## 改动范围

仅涉及以下文件，调用方零改动：

| 文件 | 改动内容 |
|------|---------|
| `backend/app/core/storage.py` | 移除 `oss2`，改用 `boto3`；删除 `_build_public_url`；`StoredFileInfo.url` 改返回空字符串 |
| `backend/pyproject.toml` | 移除 `oss2`，添加 `boto3` |
| `backend/app/services/studio/files.py:164` | `thumbnail=info.url` → `thumbnail=""` |
| `backend/app/utils/files.py:124` | `thumbnail=info.url` → `thumbnail=""` |
| 线上环境变量 | 新增 `S3_REGION_NAME=cn-shenzhen` |

## 设计细节

### boto3 客户端构建

```python
from botocore.config import Config

boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url,
    aws_access_key_id=settings.s3_access_key_id,
    aws_secret_access_key=settings.s3_secret_access_key,
    region_name=settings.s3_region_name or "us-east-1",
    config=Config(s3={"addressing_style": "path"}),
)
```

- `addressing_style="path"` 写死：path 格式同时兼容 RustFS（localhost 不支持 virtual-hosted）和阿里云 OSS，无需对外暴露配置
- `region_name` 从 `settings.s3_region_name` 读取，未填时 fallback `us-east-1`（RustFS 不校验此值）

### thumbnail 字段处理

`FileItem.thumbnail` 经确认前端不直接使用（前端通过 `/api/v1/studio/files/{file_id}/download` 接口访问文件）。上传后存空字符串，与资产缩略图（`entity_thumbnails.py`）的行为保持隔离。

`_build_public_url` 函数及 `S3_PUBLIC_BASE_URL` 的拼接逻辑一并删除。`StoredFileInfo.url` 字段保留但改返回空字符串，接口签名不变。

### 对外接口（不变）

```python
upload_file(*, key, data, content_type, extra_args) -> StoredFileInfo
download_file(*, key) -> bytes
get_file_info(*, key) -> StoredFileInfo
list_files(*, prefix) -> list[StoredFileInfo]
delete_file(*, key) -> None
generate_signed_url(*, key, expires) -> str
signed_download_url(*, key, expires) -> str
init_storage() -> None
```

### 环境变量配置对照

| 变量 | 本地（RustFS） | 线上（OSS 内网） |
|------|--------------|----------------|
| `S3_ENDPOINT_URL` | `http://localhost:9000` | `https://oss-cn-shenzhen-internal.aliyuncs.com` |
| `S3_REGION_NAME` | （不填，fallback us-east-1） | `cn-shenzhen` |
| `S3_ACCESS_KEY_ID` | `rustfsadmin` | 阿里云 AccessKey ID |
| `S3_SECRET_ACCESS_KEY` | `rustfsadmin` | 阿里云 AccessKey Secret |
| `S3_BUCKET_NAME` | `jellyfish-assets` | `fzzs-jellyfish` |
| `S3_BASE_PATH` | （空） | `jellyfish/test` |
| `S3_PUBLIC_BASE_URL` | （不再使用） | （不再使用） |

## 不在本次范围内

- `FileItem.thumbnail` 字段的存在意义（冗余字段，后续可单独清理数据库）
- 签名 URL 的业务使用（接口保留，调用时机由业务层决定）
