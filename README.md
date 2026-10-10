# Headscale 节点静态 IP 修改工具 (headscale-set-ip)

Headscale 官方原生 CLI 暂未提供直接指定/修改节点 IPv4 的命令（默认按加入顺序递增分配）。  
本工具 `headscale-set-ip` 用于快速、安全地将指定节点修改为所期望的固定 IP，并具备冲突检测、自动备份与服务原子切换能力。

---

## 基本功能

1. 支持通过 **节点 ID**（如 `15`）或 **节点名称**（如 `vps-01`, `server-01`）直接定位机器。
2. 修改前自动扫描全库活跃节点，若目标 IP 已被占用会立即拦截并告警。
3. 校验 IPv4 地址合法性；若超出 Tailscale 默认 CGNAT 范围（`100.64.0.0/10`）会主动发出提示。
4. 写入前自动备份 `/var/lib/headscale/db.sqlite` 到带时间戳的 `.bak` 文件。
5. 自动暂停 `headscale` 服务并在数据库变更后（或遇到异常时）通过 `finally` 机制确保自动拉起，避免服务中断。
6. 修改生效后，运行中的各 Tailscale 客户端会在数秒内通过控制面自动拉取并刷新节点 IP，无需重启客户端节点。

---

## 安装方式

直接下载脚本到系统 PATH 路径并赋予执行权限：

```bash
# 通过 curl 下载并安装
sudo curl -fsSL https://raw.githubusercontent.com/cfm019/headscale-set-ip/main/headscale-set-ip.py -o /usr/local/bin/headscale-set-ip
sudo chmod +x /usr/local/bin/headscale-set-ip

# 或通过 wget 下载并安装
sudo wget -qO /usr/local/bin/headscale-set-ip https://raw.githubusercontent.com/cfm019/headscale-set-ip/main/headscale-set-ip.py
sudo chmod +x /usr/local/bin/headscale-set-ip
```

---

## 常用操作指南

> **注意**：脚本涉及操作 SQLite 数据库和重启服务，需使用 `root` 权限或 `sudo` 执行。

### 操作 1：查看所有节点与当前 IP

列出当前网络中所有有效节点的 ID、别名、主机名及内网 IP：

```bash
headscale-set-ip -l
# 或
headscale-set-ip --list
```

**输出示例**：
```text
ID    Name                         Hostname                 IPv4             IPv6
-----------------------------------------------------------------------------------------------
1     server-01                    server-01                100.64.0.1       fd7a:115c:a1e0::1
10    nas                          nas-device               100.64.0.10      fd7a:115c:a1e0::a
15    vps-01                       vps-tokyo                100.64.0.14      fd7a:115c:a1e0::e
```

---

### 操作 2：通过「节点 ID」修改 IP

例如将 ID 为 `15` 的节点 IP 修改为 `100.64.0.88`：

```bash
headscale-set-ip 15 100.64.0.88
```

---

### 操作 3：通过「节点名称」修改 IP

也可以直接输入节点名称（Given Name 或 Hostname），例如：

```bash
headscale-set-ip vps-01 100.64.0.88
# 或
headscale-set-ip server-01 100.64.0.100
```

**执行过程示例**：
```text
准备修改节点:
  • 节点 ID:   15
  • 节点名称: vps-01
  • 原 IPv4:  100.64.0.14
  • 新 IPv4:  100.64.0.88

[INFO] 正在停止 headscale 服务...
[INFO] 数据库已自动安全备份至: /var/lib/headscale/db.sqlite.bak.20261010_123000
[SUCCESS] 数据库 IP 修改成功！
[INFO] 正在启动 headscale 服务...
[SUCCESS] 完成！节点 [vps-01] 的 IP 已成功更改为: 100.64.0.88

[提示] 该节点的 Tailscale 客户端在几秒内会自动刷新并生效新 IP。
```

---

### 操作 4：应急回滚（可选）

每次执行成功修改前，脚本均会在 `/var/lib/headscale/` 目录下生成带时间戳的备份文件，如：
`/var/lib/headscale/db.sqlite.bak.20261010_123000`

若遇特殊情况需要回退：

```bash
systemctl stop headscale
cp /var/lib/headscale/db.sqlite.bak.20261010_123000 /var/lib/headscale/db.sqlite
systemctl start headscale
```

---

## 注意事项

1. **IP 分配规划建议**：
   - 建议为重要核心节点规划固定网段或易记后缀，例如：
     - 服务器 / 网关：`100.64.0.1` ~ `100.64.0.20`
     - 软路由 / Subnet Router：`100.64.0.80` ~ `100.64.0.99`
     - 个人电脑 / 手机：`100.64.0.100` 以上
2. **客户端缓存刷新**：
   - 修改后，通常无需在客户端执行任何操作，控制面会推送更新通知。
   - 若个别客户端未立即生效，可在客户端执行 `tailscale status` 验证当前分配到的 IP，或通过 `tailscale down && tailscale up` 强制重新握手。
