---
sidebar_position: 7.5
title: 你自己的中继
description: 通过你自己部署的中继（relay），让手机在任何网络都能连上电脑上的 Suzent，也让 GitHub 等服务调用你的 webhook。
---

# 你自己的中继

中继（relay）让你的手机在任何网络下都能连上你电脑上的 Suzent，也让 GitHub
等互联网上的服务能调用你的 [webhook 任务](./automation.md#webhooks)。
不需要 VPN、端口转发，也不需要固定 IP。

**中继由你自己部署。** Suzent 没有官方托管的中继，所以你的对话不会经过任何
Suzent 云端。你只需部署一次 [suzent-relay](https://github.com/cyzus/suzent-relay)，
可以免费放在 Cloudflare Workers 上，也可以用 Docker 跑在任意服务器上，只有你自己的
Suzent 会用它。即使你不在家，你的智能体依然是主权的。

## 工作原理

```
电脑上的 Suzent ──主动连出──▶ 你的中继 ◀── 手机上的 Suzent 应用
                                 ▲
                                 └── GitHub 等 webhook 调用方
```

你的电脑主动连到中继，并保持这条连接。手机和 webhook 调用方把请求发给中继，
中继再沿这条连接转交给电脑。中继不在磁盘上保存任何东西。

- **手机流量端到端加密。** 配对二维码里带着你电脑的密钥，手机在发送任何内容前都会
  先校验，所以中继只能转发它既看不懂、也改不了的数据。
- **只放行手机和 webhook。** Suzent 的其他部分对互联网保持关闭。
- **中继能看到 webhook 的内容**，和任何 webhook 接收方一样。这也是应该自己部署的
  又一个理由。

## 设置

1. 部署 suzent-relay。它的
   [README](https://github.com/cyzus/suzent-relay/blob/main/README.zh-CN.md) 介绍了
   几种方式：Cloudflare Workers（免费，无需服务器）、在任意服务器上用 Docker 并自动
   配置 HTTPS，或者放在你自己的反向代理后面。记下它的 `https://` 地址。建议设置
   注册密钥，这样只有你的 Suzent 能使用这个中继。
2. 在电脑上打开 **设置 → 设备 → 中继**，填入 **中继地址** 和 **注册密钥**，然后
   保存。状态会变成 **已连接**。
3. 开启[后台服务](./automation.md#keep-suzent-running-in-the-background)，
   这样退出桌面应用后 Suzent 仍保持连接。只有电脑上的 Suzent 在运行时，中继才能用。

## 在手机上使用

重新扫描一个新的配对二维码，二维码里就会包含中继。详见移动应用页的
[Through your own relay](./mobile.md#through-your-own-relay)。

手机总是先尝试电脑的直连地址（比如家里的 Wi-Fi），只有都连不上时才走中继。在设置
中继之前就配对过的手机，会在下一次直连电脑时自动得知中继地址。

## 用于 webhook

中继连上之后，每个 webhook 任务都会显示两个地址：一个是本机地址，一个是经过中继的
地址。把中继地址交给 GitHub 或其他服务即可。详见
[Webhooks through a relay](./automation.md#webhooks-through-a-relay)。

## 重置中继地址

中继设置里的 **重置中继地址** 会换一组新地址。如果另一台 Suzent 占用了这个地址，
或者你想让持有旧地址的手机和 webhook 调用方失效，就用它。重置之后，请重新配对手机，
并把新的 webhook 地址发给调用方。

## 中继还是 Tailscale？

两者都可以，也可以同时用：手机会尝试它知道的每一个地址。

- **Tailscale** 把手机和电脑放进同一个私有网络。两台设备都需要装 Tailscale，并且只对
  你加入的设备有效。
- **中继** 在手机上只需要 Suzent 应用，同时还能给 webhook 任务一个互联网地址。只需
  部署一次。
