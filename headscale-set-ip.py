#!/usr/bin/env python3
"""
Headscale Node IP Modification Utility
Author: Antigravity
Usage:
  headscale-set-ip -l / --list
  headscale-set-ip <node_id_or_name> <new_ipv4>
"""
import sys
import os
import shutil
import sqlite3
import ipaddress
import subprocess
from datetime import datetime

DB_PATH = "/var/lib/headscale/db.sqlite"
SERVICE_NAME = "headscale"

def error(msg):
    print(f"\033[31m[ERROR]\033[0m {msg}", file=sys.stderr)
    sys.exit(1)

def success(msg):
    print(f"\033[32m[SUCCESS]\033[0m {msg}")

def info(msg):
    print(f"\033[36m[INFO]\033[0m {msg}")

def warn(msg):
    print(f"\033[33m[WARN]\033[0m {msg}")

def check_root():
    if os.geteuid() != 0:
        error("请使用 root 权限或 sudo 运行此脚本！")

def get_db():
    if not os.path.exists(DB_PATH):
        error(f"找不到数据库文件: {DB_PATH}")
    return sqlite3.connect(DB_PATH)

def list_nodes():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, COALESCE(given_name, hostname, 'unknown') as name, hostname, ipv4, ipv6
        FROM nodes
        WHERE deleted_at IS NULL
        ORDER BY id ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    print(f"{'ID':<5} {'Name':<28} {'Hostname':<24} {'IPv4':<16} {'IPv6'}")
    print("-" * 95)
    for row in rows:
        nid, name, host, v4, v6 = row
        print(f"{nid:<5} {str(name):<28} {str(host):<24} {str(v4):<16} {str(v6)}")

def change_ip(target, new_ip_str):
    check_root()
    # 1. 校验 IP 合法性
    try:
        new_ip = ipaddress.IPv4Address(new_ip_str)
    except ValueError:
        error(f"'{new_ip_str}' 不是合法的 IPv4 地址！")

    prefix = ipaddress.IPv4Network("100.64.0.0/10")
    if new_ip not in prefix:
        warn(f"提示: {new_ip} 不在默认的 Tailscale CGNAT 范围 (100.64.0.0/10) 内。")

    conn = get_db()
    cursor = conn.cursor()

    # 2. 检查新 IP 是否已被其他节点占用
    cursor.execute("""
        SELECT id, COALESCE(given_name, hostname) 
        FROM nodes 
        WHERE ipv4 = ? AND deleted_at IS NULL
    """, (str(new_ip),))
    existing = cursor.fetchone()
    if existing:
        error(f"IP {new_ip} 已被节点 ID: {existing[0]} ({existing[1]}) 占用，请选择其它 IP！")

    # 3. 查找目标节点 (支持通过 ID 或 Name 查找)
    if target.isdigit():
        cursor.execute("SELECT id, given_name, hostname, ipv4 FROM nodes WHERE id = ? AND deleted_at IS NULL", (int(target),))
    else:
        cursor.execute("SELECT id, given_name, hostname, ipv4 FROM nodes WHERE (given_name = ? OR hostname = ?) AND deleted_at IS NULL", (target, target))
    
    node = cursor.fetchone()
    if not node:
        error(f"未找到活跃节点: '{target}'。可通过 headscale-set-ip -l 查看所有节点。")

    node_id, given_name, hostname, old_ip = node
    display_name = given_name or hostname

    if str(old_ip) == str(new_ip):
        warn(f"节点 {display_name} (ID: {node_id}) 当前 IP 已经是 {new_ip}，无需更改。")
        conn.close()
        return

    conn.close()

    print(f"\n准备修改节点:")
    print(f"  • 节点 ID:   {node_id}")
    print(f"  • 节点名称: {display_name}")
    print(f"  • 原 IPv4:  {old_ip}")
    print(f"  • 新 IPv4:  \033[32m{new_ip}\033[0m\n")

    # 4. 自动停止服务
    info(f"正在停止 {SERVICE_NAME} 服务...")
    subprocess.run(["systemctl", "stop", SERVICE_NAME], check=True)

    # 5. 自动备份数据库
    bak_path = f"{DB_PATH}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(DB_PATH, bak_path)
    info(f"数据库已自动安全备份至: {bak_path}")

    # 6. 执行更新
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE nodes SET ipv4 = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (str(new_ip), node_id))
        conn.commit()
        conn.close()
        success("数据库 IP 修改成功！")
    except Exception as e:
        error(f"数据库写入异常: {e}")
    finally:
        # 7. 无论如何恢复服务
        info(f"正在启动 {SERVICE_NAME} 服务...")
        subprocess.run(["systemctl", "start", SERVICE_NAME], check=True)

    success(f"完成！节点 [{display_name}] 的 IP 已成功更改为: {new_ip}")
    print("\n\033[33m[提示]\033[0m 该节点的 Tailscale 客户端在几秒内会自动刷新并生效新 IP。")

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in ("-l", "--list", "list"):
        list_nodes()
    elif len(sys.argv) == 3:
        change_ip(sys.argv[1], sys.argv[2])
    else:
        print("Headscale 节点固定 IP 修改小工具")
        print("\n用法:")
        print("  headscale-set-ip -l                       # 查看所有节点与当前 IP")
        print("  headscale-set-ip <节点ID或名称> <新IP>    # 修改指定节点的 IP")
        print("\n示例:")
        print("  headscale-set-ip 15 100.64.0.88")
        print("  headscale-set-ip server-01 100.64.0.100")
