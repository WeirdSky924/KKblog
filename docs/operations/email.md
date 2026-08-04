# 通用 SMTP 投递

应用只依赖标准 SMTP，不绑定具体邮件服务商。验证码与运维告警都使用 Django
SMTP backend；开发和测试固定进入隔离 Mailpit，生产从服务器环境读取同一组
SMTP 参数。

## 生产配置

以下值只保存在服务器侧秘密环境中，不进入 Git、日志或截图：

```text
KAJ_ADMIN_EMAIL=<接收运维告警的邮箱>
DEFAULT_FROM_EMAIL=<已认证域名下的发件地址>
EMAIL_HOST=<SMTP 主机>
EMAIL_PORT=<1..65535>
EMAIL_HOST_USER=<可选；与密码同时提供>
EMAIL_HOST_PASSWORD=<可选；与用户名同时提供>
EMAIL_USE_TLS=<true|false>
EMAIL_USE_SSL=<true|false>
```

`EMAIL_USE_TLS` 表示明文连接后升级 STARTTLS；`EMAIL_USE_SSL` 表示连接建立时
立即使用 TLS，两者不能同时为 `true`。常见的 465 submission 使用
`EMAIL_USE_SSL=true`，587 submission 通常使用 `EMAIL_USE_TLS=true`。

## SMTP 中继

```text
Django web/worker -> SMTP 中继 465/587 -> 收件域
```

中继负责后续公网投递、队列重试和发信 IP 信誉。应用服务器不直接连接收件方
MX，因此不需要为应用服务器公网 IP 配置 PTR，也不需要开放出站 25。发件域仍需
按中继服务要求完成身份验证、SPF、DKIM 和 DMARC 配置。

应用返回成功只表示中继接受了邮件，不等于最终送达。验收需要同时读取应用结果、
中继投递状态、退信状态和目标邮箱。

## 自建直投

```text
Django web/worker -> 受控本机 MTA -> 收件域 MX:25
```

选择自建 MTA 直投时，必须额外满足：

1. 云厂商允许出站 TCP 25，并能连接多个外部 MX。
2. 使用稳定公网 IP，PTR、EHLO 和正向 A/AAAA 解析一致。
3. 发件域发布与实际发信 IP 一致的 SPF、DKIM 和 DMARC。
4. MTA 只信任 loopback 或明确应用网段，并拒绝开放中继。
5. 配置队列重试、最大队列时长、磁盘告警、退信地址和日志保留。

缺少 PTR 不影响应用连接 SMTP 中继，但会显著影响自建 MTA 直投的信誉和送达率。

## 验收顺序

1. 使用隔离 Mailpit 验证验证码和运维邮件都经过通用 SMTP 配置。
2. 在生产候选环境只读核对主机、端口、TLS 模式和发件身份，不输出密码。
3. 经当前回合明确授权后，向指定地址发送一封最小验证邮件。
4. 读回中继或 MTA 队列、投递日志、退信状态和收件箱结果。
