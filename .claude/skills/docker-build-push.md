# Docker Build & Push — Jellyfish

构建 Jellyfish 合并镜像（前端 + 后端 + Celery Worker）并推送到 ACR。

## 固定配置

- **ACR（公网）**: `crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish`
- **ACR（VPC 内网，SAE 使用）**: `crpi-7ajeyduewy90avu4-vpc.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish`
- **Dockerfile**: `deploy/docker/combined.Dockerfile`
- **平台**: `linux/amd64`

## 执行步骤

### 1. 确认版本号

```bash
git tag --sort=-version:refname | head -5
```

当前最新 tag 即为版本号（如 `v0.3.2`）。

### 2. 初始化 ACR 认证

每次新 terminal session 执行一次：

```bash
mkdir -p /tmp/docker-acr-config
echo '{"auths":{"crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com":{"auth":"'$(echo -n "$ACR_USERNAME:$ACR_PASSWORD" | base64)'"}}}' \
  > /tmp/docker-acr-config/config.json
```

### 3. 构建镜像

在仓库根目录执行：

```bash
VERSION=v0.3.2   # 替换为实际版本号
ACR="crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish"

docker buildx build \
  --platform linux/amd64 \
  -f deploy/docker/combined.Dockerfile \
  -t "$ACR:$VERSION" \
  -t "$ACR:latest" \
  --load \
  .
```

构建测试镜像（test tag）：

```bash
ACR="crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish"

docker buildx build \
  --platform linux/amd64 \
  -f deploy/docker/combined.Dockerfile \
  -t "$ACR:test" \
  --load \
  .
```

### 4. 推送到 ACR

```bash
VERSION=v0.3.2
ACR="crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish"

DOCKER_CONFIG=/tmp/docker-acr-config docker push "$ACR:$VERSION"
DOCKER_CONFIG=/tmp/docker-acr-config docker push "$ACR:latest"
```

推送测试镜像：

```bash
ACR="crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish"
DOCKER_CONFIG=/tmp/docker-acr-config docker push "$ACR:test"
```

### 5. 用已有镜像打新 tag（无需重新构建）

```bash
ACR="crpi-7ajeyduewy90avu4.cn-shenzhen.personal.cr.aliyuncs.com/fzzs/jellyfish"
docker tag "$ACR:v0.3.2" "$ACR:test"
DOCKER_CONFIG=/tmp/docker-acr-config docker push "$ACR:test"
```

## 常见问题

| 错误 | 原因 | 解决 |
|------|------|------|
| `denied: requested access to the resource is denied` | ACR 认证未初始化或 env 变量未加载 | 按步骤 2 重新生成 `/tmp/docker-acr-config/config.json` |
| `--platform` 警告 | Apple Silicon 本地架构为 arm64 | 正常，`--platform linux/amd64` 会用 QEMU 模拟，构建较慢 |
| push 时走 docker.io | `$ACR` 变量在 `&&` 链中未继承 | 不要用 `&&` 串联赋值和 push，分行执行或用完整镜像名字符串 |
