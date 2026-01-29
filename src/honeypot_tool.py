#!/usr/bin/env python3
import os
import subprocess
import re
import sys
from datetime import datetime

# ===========================
# 路徑設定（正確 bind mount）
# ===========================

PROJECT_ROOT = "/home/seed/tpot-project"
OUTPUT_DIR = f"{PROJECT_ROOT}/output"

# T-Pot bind mount 的真正有效設定檔
COWRIE_REAL = "/home/seed/tpotce/docker/cowrie/dist/cowrie.cfg"
DIONAEA_REAL = "/home/seed/tpotce/docker/dionaea/dist/etc/dionaea.cfg"
HONEYTRAP_REAL = "/home/seed/tpotce/data/honeytrap/config/honeytrap.conf"

DOCKER_COMPOSE_PATH = "/home/seed/tpotce"


# ===========================
# Shell helper
# ===========================
def run(cmd):
    print(f"\n$ {cmd}")
    p = subprocess.run(cmd, shell=True)
    if p.returncode != 0:
        print("Failed to execute command")
        sys.exit(1)


# ===========================
# 寫入 output + deploy
# ===========================

def save_and_deploy(filename, content, real_path, container):
    """
    1. 寫到 output/（歷史備份）
    2. 寫到 T-Pot bind mount 路徑
    3. 重啟 container
    """

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")

    # 1️⃣ 寫入備份
    output_file = f"{OUTPUT_DIR}/{filename}-{stamp}"
    print(f"\nWriting backup to {output_file}")
    with open(output_file, "w") as f:
        f.write(content)
    print("Backup Completed")

    # 2️⃣ 寫入 bind mount 路徑（這個會直接影響容器）
    print(f"\nWriting to T-Pot bind mount：{real_path}")
    with open(real_path, "w") as f:
        f.write(content)
    print("bind mount configuration has been updated")

    # 3️⃣ 重啟 container
    print(f"\nrestarting {container} ...")
    run(f"cd {DOCKER_COMPOSE_PATH} && docker compose restart {container}")
    print(f"{container} has been restarted.\n")

# ===========================
# User input
# ===========================
def ask_cowrie_params():
    print("\n=== Cowrie Configuration Update ===")
    return {
        "port": input("SSH port (leave blank to skip)：").strip(),
        "banner": input("Banner (leave blank to skip)：").strip(),
        "creds": input("auth_class (leave blank to skip)：").strip(),
        "timeout": input("session timeout (leave blank to skip)：").strip(),
        "hostname": input("hostname (leave blank to skip)：").strip(),
        "kernel_version": input("kernel_version (leave blank to skip)：").strip(),
        "kernel_build": input("kernel_build_string (leave blank to skip)：").strip(),
        "operating_system": input("operating_system (leave blank to skip)：").strip(),
        "ssh_version": input("ssh_version (leave blank to skip)：").strip(),
    }


def ask_dionaea_params():
    print("\n=== 🦠 Dionaea 設定 ===")
    return {"services": input("啟用的 services（空白＝不改）：").strip()}


def ask_honeytrap_params():
    print("\n=== 🍯 Honeytrap 設定修改 ===")
    print("插件格式： pluginName:yes 或 pluginName:no，用逗號隔開")
    print("可用插件： ftpDownload, tftpDownload, b64Decode, deUnicode, vncDownload")

    plugins = input("插件開關：").strip()

    return {
        "plugins": plugins,
        "attacks": input("attacks_dir（空白＝不改）： ").strip(),
        "downloads": input("downloads_dir（空白＝不改）： ").strip(),
        "log_attacker": input("logAttacker logfile（空白＝不改）： ").strip(),
        "log_json": input("logJSON logfile（空白＝不改）： ").strip(),
    }


# ===========================
# Config generators
# ===========================
def generate_cowrie_cfg(p):
    """
    只修改 [ssh] block，不動 [telnet]、[honeypot] 等其他區段
    """

    # 讀原始 config
    with open(COWRIE_REAL, "r") as f:
        cfg = f.read()


    if p["hostname"]:
        cfg = re.sub(r"hostname\s*=.*", f"hostname = {p['hostname']}", cfg)

    if p["kernel_version"]:
        cfg = re.sub(r"kernel_version\s*=.*", f"kernel_version = {p['kernel_version']}", cfg)

    if p["kernel_build"]:
        cfg = re.sub(r"kernel_build_string\s*=.*", f"kernel_build_string = {p['kernel_build']}", cfg)

    if p["operating_system"]:
        cfg = re.sub(r"operating_system\s*=.*", f"operating_system = {p['operating_system']}", cfg)

    if p["ssh_version"]:
        cfg = re.sub(r"ssh_version\s*=.*", f"ssh_version = {p['ssh_version']}", cfg)



    # -----------------------------
    # 找出 [ssh] 區段的開始
    # -----------------------------
    ssh_start = cfg.find("[ssh]")
    if ssh_start == -1:
        print("[ssh] section not found")
        return cfg

    # 找出下一個區段（下一個以 "[" 開頭的位置）
    next_section = cfg.find("\n[", ssh_start + 1)
    if next_section == -1:
        ssh_block = cfg[ssh_start:]
    else:
        ssh_block = cfg[ssh_start:next_section]

    original_ssh = ssh_block  # 用來最後替換整段

    # -----------------------------
    # 修改 SSH listen_endpoints
    # -----------------------------
    if p["port"]:
        ssh_block = re.sub(
            r"listen_endpoints\s*=.*",
            f"listen_endpoints = tcp:{p['port']}:interface=0.0.0.0",
            ssh_block
        )

    # -----------------------------
    # 修改 SSH banner/version
    # -----------------------------
    if p["banner"]:
        ssh_block = re.sub(
            r"version\s*=.*",
            f"version = SSH-2.0-{p['banner']}",
            ssh_block
        )

    # -----------------------------
    # 修改 auth_class
    # -----------------------------
    if p["creds"]:
        ssh_block = re.sub(
            r"auth_class\s*=.*",
            f"auth_class = {p['creds']}",
            ssh_block
        )

    # -----------------------------
    # 修改 timeout（不在 [ssh] block）
    # -----------------------------
    if p["timeout"]:
        cfg = re.sub(
            r"interactive_timeout\s*=.*",
            f"interactive_timeout = {p['timeout']}",
            cfg
        )

    # -----------------------------
    # 把修改後的 ssh_block 替換回 config
    # -----------------------------
    cfg = cfg.replace(original_ssh, ssh_block)

    return cfg



def generate_dionaea_cfg(p):
    cfg = "[services]\n"
    if p["services"]:
        cfg += f"enable = {p['services']}\n"
    return cfg


def generate_honeytrap_cfg(p):
    # 讀原始設定
    with open(HONEYTRAP_REAL, "r") as f:
        cfg = f.read()

    # ----------------------------------------
    # 1. 處理插件 on/off
    #    格式：plugin-ftpDownload = ""
    # ----------------------------------------
    if p["plugins"]:
        entries = [x.strip() for x in p["plugins"].split(",")]
        for entry in entries:
            if ":" not in entry:
                continue

            name, status = entry.split(":")
            name = name.strip()
            status = status.strip().lower()

            pattern = rf"(plugin-{name}\s*=\s*\".*?\")"

            if status == "yes":
                # 啟用 = 不加註解
                replacement = f'plugin-{name} = ""'
            else:
                # 關閉 = 註解掉（Honeytrap 使用 // 註解）
                replacement = f'// plugin-{name} = ""'

            cfg = re.sub(pattern, replacement, cfg)

    # ----------------------------------------
    # 2. 修改 attacks_dir
    # ----------------------------------------
    if p["attacks"]:
        cfg = re.sub(
            r'attacks_dir\s*=\s*".*?"',
            f'attacks_dir = "{p["attacks"]}"',
            cfg
        )

    # ----------------------------------------
    # 3. 修改 downloads_dir
    # ----------------------------------------
    if p["downloads"]:
        cfg = re.sub(
            r'downloads_dir\s*=\s*".*?"',
            f'downloads_dir = "{p["downloads"]}"',
            cfg
        )

    # ----------------------------------------
    # 4. 修改 logAttacker logfile
    # ----------------------------------------
    if p["log_attacker"]:
        cfg = re.sub(
            r'plugin-logAttacker\s*=\s*{[^}]*}',
            f'plugin-logAttacker = {{ logfile = "{p["log_attacker"]}" }}',
            cfg,
            flags=re.DOTALL
        )

    # ----------------------------------------
    # 5. 修改 plugin-logJSON logfile
    # ----------------------------------------
    if p["log_json"]:
        cfg = re.sub(
            r'plugin-logJSON\s*=\s*{[^}]*}',
            f'plugin-logJSON = {{ logfile = "{p["log_json"]}" }}',
            cfg,
            flags=re.DOTALL
        )

    return cfg



# ===========================
# Main
# ===========================
def main():
    print("=== Honeypot Parameter Modifier ===")
    print("1. Cowrie")
    print("2. Dionaea")
    print("3. Honeytrap")

    c = input("Choose（1/2/3）： ").strip()

    if c == "1":
        params = ask_cowrie_params()
        cfg = generate_cowrie_cfg(params)
        save_and_deploy("cowrie.cfg", cfg, COWRIE_REAL, "cowrie")

    elif c == "2":
        params = ask_dionaea_params()
        cfg = generate_dionaea_cfg(params)
        save_and_deploy("dionaea.cfg", cfg, DIONAEA_REAL, "dionaea")

    elif c == "3":
        params = ask_honeytrap_params()
        cfg = generate_honeytrap_cfg(params)
        save_and_deploy("honeytrap.conf", cfg, HONEYTRAP_REAL, "honeytrap")

    else:
        print("Invalid option")
        sys.exit(1)


if __name__ == "__main__":
    main()
