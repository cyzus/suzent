# Suzent 社交配对（Pairing）系统重构方案：Token 令牌验证机制

这份重构指南由 OpenClaw (suzclaw 🦑) 亲自设计。
旨在将当前强依赖本地 CLI 终端的配对流程，升级为支持移动端/Web端远程批准的现代化 Token 验证流。

## 当前状态速览 (Current State)

| 层级 | 文件 | 现状 |
|------|------|------|
| 核心逻辑 | `src/suzent/core/social_brain.py` | `_pending_pairings` 以 `platform:sender_id` 为 Key；两步握手（greeting → intro → 管理员批准）|
| HTTP 接口 | `src/suzent/server.py:587` | `POST /social/pairing/{sender_id}/approve`，sender_id 暴露在 URL 路径中 |
| CLI | `src/suzent/cli/pair.py` | `suzent pair approve/deny <sender_id>`，须登录服务器 |
| 前端 UI | `frontend/src/components/settings/SocialTab.tsx` | 展示待审核列表，含 Approve/Deny 按钮 |
| API 客户端 | `frontend/src/lib/api.ts:432` | `approvePairing(senderId)` / `denyPairing(senderId)` |

## 当前痛点 (The Problem)

目前 `SocialBrain` 拦截到陌生人请求后，管理员必须通过服务器终端执行 `suzent pair approve <sender_id>` 才能放行。
这种设计**严重依赖物理机终端或 SSH**，在移动场景下极度不便。同时，URL 中直接暴露 `sender_id` 也存在枚举攻击面。

## 新版架构设计 (The Token-Based Approach)

采用 **"服务端生成 Token → 用户带外传递 → 管理员 Web 端核销"** 的闭环逻辑。

### 核心流转过程（与现有两步握手集成）：

```
陌生用户首次联系
    │
    ▼
SocialBrain 发送问候语（HANDSHAKE_WAITING，行为不变）
    │
    ▼
用户回复自我介绍
    │
    ▼
生成带过期时间的 Token，存入 _pending_tokens
回复用户："请将此验证码提供给管理员：[A8F3B9]"
状态变为 HANDSHAKE_PENDING
    │
    ▼
用户通过现实渠道（面对面/微信/电话）将 Token 告知管理员
    │
    ▼
管理员在 Web 后台的 SocialTab 输入 Token
    │
    ▼
POST /social/pairing/approve  { "token": "A8F3B9" }
系统校验有效性 + 未过期 → 写入白名单 → 销毁 Token → 通知用户 ✅
```

---

## 实施路径 (Implementation Steps)

### 1. 核心大脑 (`src/suzent/core/social_brain.py`) 重构

将 `_pending_pairings` 的 Key 从 `sender_key` 改为 `token`，并集成到现有握手流程的第二步：

```python
import secrets
import string
import time

_TOKEN_CHARS = string.ascii_uppercase + string.digits  # 0-9 A-Z，共36种，非纯hex

class SocialBrain(BaseBrain):
    def __init__(self, ...):
        # 结构: { "A8F3B9": {"sender_id": "...", "sender_name": "...", "platform": "...", "intro": "...", "requested_at": 0, "expires_at": 0} }
        self._pending_tokens: Dict[str, dict] = {}

    def _generate_token(self) -> str:
        """生成 6 位大写字母数字验证码（36^6 ≈ 21亿种组合）"""
        return "".join(secrets.choice(_TOKEN_CHARS) for _ in range(6))

    def _cleanup_expired_tokens(self):
        """清理已过期的 Token，防止内存泄漏。"""
        now = time.time()
        expired = [t for t, e in self._pending_tokens.items() if e["expires_at"] < now]
        for t in expired:
            self._pending_tokens.pop(t, None)

    def _find_token_for_sender(self, sender_key: str) -> Optional[str]:
        """查找该 sender 是否已有未过期的 Token，避免重复生成。"""
        now = time.time()
        return next(
            (t for t, e in self._pending_tokens.items()
             if e["sender_key"] == sender_key and e["expires_at"] > now),
            None,
        )

    async def _handle_handshake(self, message: UnifiedMessage):
        """
        两步握手流程（行为与现在一致，仅在第二步改为生成 Token）：
          1. 首次联系 → 发问候语，state=waiting
          2. 用户回复自介 → 生成 Token，state=pending；Token 回传给用户
        """
        key = self._sender_key(message)
        # 注意：改用 _pending_tokens 后需用 sender_key 反查
        existing_token = self._find_token_for_sender(key)
        if existing_token:
            # 已有未过期 Token，提示等待，不重复生成
            await self.channel_manager.send_message(
                message.platform,
                message.sender_id,
                f"⏳ 你的申请仍在审核中。请将验证码提供给管理员：**{existing_token}**",
            )
            return

        # 检查是否处于 waiting 状态（旧逻辑沿用 _pending_pairings 临时标记，
        # 或直接用内存 dict 区分两步，可按实际重构方式统一）
        ...

    async def approve_by_token(self, token: str) -> bool:
        """通过 Token 批准配对（由 REST 和 CLI 调用）。"""
        self._cleanup_expired_tokens()
        token = token.upper().strip()
        entry = self._pending_tokens.pop(token, None)
        if entry is None:
            return False

        sender_id = entry["sender_id"]
        self.allowed_users.add(sender_id)
        self.allowed_users.add(entry["sender_name"])
        await self._persist_approved_user(sender_id)  # 写入数据库，勿遗漏！

        try:
            await self.channel_manager.send_message(
                entry["platform"],
                sender_id,
                "✅ 你的申请已通过！现在可以正常使用了。",
            )
        except Exception:
            pass
        logger.info(f"Pairing approved via token: {sender_id} on {entry['platform']}")
        return True

    async def deny_by_token(self, token: str) -> bool:
        """通过 Token 拒绝配对（可选，直接过期也有同等效果）。"""
        self._cleanup_expired_tokens()
        token = token.upper().strip()
        entry = self._pending_tokens.pop(token, None)
        if entry is None:
            return False
        try:
            await self.channel_manager.send_message(
                entry["platform"], entry["sender_id"], "❌ 你的申请未通过。"
            )
        except Exception:
            pass
        return True

    def list_pairings(self) -> list[dict]:
        """返回所有未过期的 pending Token 列表（供 REST + CLI 使用）。"""
        self._cleanup_expired_tokens()
        return [
            {
                "token": t,
                "sender_id": e["sender_id"],
                "sender_name": e["sender_name"],
                "platform": e["platform"],
                "intro": e["intro"],
                "requested_at": e["requested_at"],
                "expires_at": e["expires_at"],
            }
            for t, e in self._pending_tokens.items()
        ]
```

**注意事项：**
- `_generate_token` 使用 `string.ascii_uppercase + string.digits`（A-Z + 0-9），而非 `secrets.token_hex`（hex 仅 A-F + 0-9，会被误认为"纯数字码"）。
- `_persist_approved_user` 是现有方法，**必须保留调用**，否则重启后白名单丢失。
- 过期时间建议 10 分钟（600s），可通过配置项暴露。

### 2. HTTP 接口层 (`src/suzent/server.py`) 重构

废弃 `{sender_id}` 路径参数路由，改为统一 Token 核销入口：

```python
# 废弃（保留兼容期，或直接删除）:
# Route("/social/pairing/{sender_id}/approve", approve_pairing, methods=["POST"])
# Route("/social/pairing/{sender_id}/deny",    deny_pairing,    methods=["POST"])

# 新增:
from pydantic import BaseModel

class TokenActionRequest(BaseModel):
    token: str

async def approve_pairing_by_token(request: Request) -> JSONResponse:
    """POST /social/pairing/approve"""
    brain = get_active_social_brain()
    if brain is None:
        return JSONResponse({"error": "SocialBrain not running"}, status_code=503)
    try:
        data = await request.json()
        req = TokenActionRequest(**data)
    except Exception:
        return JSONResponse({"error": "Invalid payload"}, status_code=400)

    ok = await brain.approve_by_token(req.token)
    if not ok:
        return JSONResponse({"error": "Invalid or expired token"}, status_code=403)
    return JSONResponse({"status": "success"})

async def deny_pairing_by_token(request: Request) -> JSONResponse:
    """POST /social/pairing/deny"""
    brain = get_active_social_brain()
    if brain is None:
        return JSONResponse({"error": "SocialBrain not running"}, status_code=503)
    try:
        data = await request.json()
        req = TokenActionRequest(**data)
    except Exception:
        return JSONResponse({"error": "Invalid payload"}, status_code=400)

    ok = await brain.deny_by_token(req.token)
    if not ok:
        return JSONResponse({"error": "Invalid or expired token"}, status_code=403)
    return JSONResponse({"status": "success"})

# 路由注册（替换旧的两条）:
# Route("/social/pairing/approve", approve_pairing_by_token, methods=["POST"]),
# Route("/social/pairing/deny",    deny_pairing_by_token,    methods=["POST"]),
```

### 3. API 客户端 (`frontend/src/lib/api.ts`) 更新

```typescript
// 更新 PairingRequest 接口，增加 token 字段
export interface PairingRequest {
  token: string;          // 新增
  sender_id: string;
  sender_name: string;
  platform: string;
  intro: string;
  state: string;
  requested_at: number;
  expires_at: number;     // 新增，前端可据此显示倒计时
}

// 废弃（删除）:
// export async function approvePairing(senderId: string)
// export async function denyPairing(senderId: string)

// 替换为:
export async function approvePairingByToken(token: string): Promise<boolean> {
  const res = await fetch(`${getApiBase()}/social/pairing/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  return res.ok;
}

export async function denyPairingByToken(token: string): Promise<boolean> {
  const res = await fetch(`${getApiBase()}/social/pairing/deny`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  return res.ok;
}
```

### 4. 前端 UI (`frontend/src/components/settings/SocialTab.tsx`) 适配

在现有 "Pending Pairings" 卡片中：

- 每行展示 Token（大字体、可复制）、平台、名称、自我介绍、剩余有效时间
- Approve/Deny 按钮改为传 `token` 而非 `senderId`
- 可选：顶部新增一个 "Enter Token to Approve" 快捷输入框，方便管理员在手机上输入用户报来的 Token，无需找到对应列表项

```tsx
// SocialTab 核心变更
const handleApprove = async (token: string) => {
  await approvePairingByToken(token);
  await refreshPairings();
};

const handleDeny = async (token: string) => {
  await denyPairingByToken(token);
  await refreshPairings();
};

// 列表渲染中，每行显示 token
{pairings.map((p) => (
  <div key={p.token}>
    <span className="font-mono text-lg font-bold">{p.token}</span>
    {/* ... sender_name, platform, intro ... */}
    <button onClick={() => handleApprove(p.token)}>Approve</button>
    <button onClick={() => handleDeny(p.token)}>Deny</button>
  </div>
))}
```

### 5. CLI 命令行 (`src/suzent/cli/pair.py`) 同步更新

```python
# 同时保留 sender_id 命令（兼容旧习惯）+ 新增 token 命令
@pair_app.command("approve-token")
def pair_approve_token(token: str = typer.Argument(..., help="Pairing token")):
    """Approve a pending pairing request by token."""
    async def _run():
        client = get_client()
        await client.social.approve_pairing_by_token(token)
        console.print(f"[green]✅ Approved token:[/green] {token}")
    asyncio.run(_run())

# suzent pair list 的输出也需增加 Token 列
```

---

## 安全考量

| 风险点 | 当前方案 | Token 方案 |
|--------|----------|-----------|
| URL 枚举 sender_id | ❌ 暴露于路径参数 | ✅ Token 完全不含身份信息 |
| 穷举攻击 | ❌ sender_id 可预测 | ✅ 36^6 ≈ 21亿种组合 + 10分钟TTL |
| 重放攻击 | ❌ 无一次性保证 | ✅ 使用即销毁（`pop`） |
| 内存泄漏 | ⚠️ 无过期清理 | ✅ `_cleanup_expired_tokens` + `expires_at` |

## 预期效果

通过这套机制，Suzent 的认证流程将彻底摆脱 SSH 的束缚。管理员可以在任意设备的浏览器上完成授权，安全性与便利性同步提升。
