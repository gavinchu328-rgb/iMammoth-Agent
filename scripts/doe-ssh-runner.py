#!/usr/bin/env python3
"""SSH helper for doe-service.sh when sshpass is unavailable."""
from __future__ import annotations

import argparse
import os
import sys

import paramiko


def connect() -> paramiko.SSHClient:
    host = os.environ.get("DOE_SSH_HOST", "192.168.9.116")
    user = os.environ.get("DOE_SSH_USER", "admin")
    password = os.environ.get("DOE_SSH_PASSWORD", "")
    key_path = os.environ.get("DOE_SSH_KEY", "")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict = {"hostname": host, "username": user, "timeout": 15}
    if key_path:
        kwargs["key_filename"] = key_path
    elif password:
        kwargs["password"] = password
    else:
        kwargs["allow_agent"] = True
        kwargs["look_for_keys"] = True
    ssh.connect(**kwargs)
    return ssh


def cmd_exec(command: str) -> int:
    ssh = connect()
    try:
        stdin, stdout, stderr = ssh.exec_command(command, timeout=120)
        out = stdout.read().decode()
        err = stderr.read().decode()
        if out:
            sys.stdout.write(out)
        if err:
            sys.stderr.write(err)
        return stdout.channel.recv_exit_status()
    finally:
        ssh.close()


def cmd_scp(local: str, remote: str) -> int:
    ssh = connect()
    try:
        sftp = ssh.open_sftp()
        sftp.put(local, remote)
        sftp.close()
        return 0
    finally:
        ssh.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)

    p_exec = sub.add_parser("exec")
    p_exec.add_argument("command")

    p_scp = sub.add_parser("scp")
    p_scp.add_argument("local")
    p_scp.add_argument("remote")

    args = parser.parse_args()
    if args.action == "exec":
        return cmd_exec(args.command)
    if args.action == "scp":
        return cmd_scp(args.local, args.remote)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
