"""Upload and deploy Voice Flow License Server to remote host"""
import os
import sys
import paramiko

HOST = "39.105.108.173"
USER = "root"
PASSWORD = "Meiweilin520"
DEPLOY_DIR = os.path.dirname(os.path.abspath(__file__))
REMOTE_DIR = "/opt/voice-flow-server"

# Files to upload (relative to this script's directory)
FILES = [
    "main.py", "api.py", "admin.py", "database.py", "license.py",
    "models.py", "requirements.txt", "voiceflow-server.service", "deploy.sh",
    "admin.html",
]
DIRS = ["keys", "data"]


def upload_dir(sftp, local_dir, remote_dir):
    """Recursively upload a directory"""
    for item in os.listdir(local_dir):
        local_path = os.path.join(local_dir, item)
        remote_path = f"{remote_dir}/{item}"
        if os.path.isfile(local_path):
            print(f"  Upload: {item} -> {remote_path}")
            sftp.put(local_path, remote_path)
        elif os.path.isdir(local_path):
            try:
                sftp.mkdir(remote_path)
            except IOError:
                pass
            upload_dir(sftp, local_path, remote_path)


def main():
    print(f"=== Voice Flow License Server Deploy ===")
    print(f"Target: {HOST}")

    # 1. Connect
    print("\n[1/5] Connecting...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    sftp = ssh.open_sftp()
    print("  Connected.")

    # 2. Create remote directory
    print("\n[2/5] Creating remote directories...")
    ssh.exec_command(f"mkdir -p {REMOTE_DIR}/keys {REMOTE_DIR}/data")
    print("  Done.")

    # 3. Upload files
    print("\n[3/5] Uploading files...")
    for f in FILES:
        local = os.path.join(DEPLOY_DIR, f)
        remote = f"{REMOTE_DIR}/{f}"
        print(f"  {f}")
        sftp.put(local, remote)

    for d in DIRS:
        local_d = os.path.join(DEPLOY_DIR, d)
        upload_dir(sftp, local_d, f"{REMOTE_DIR}/{d}")

    sftp.close()
    print("  Upload complete.")

    # 4. Run deploy
    print("\n[4/5] Running deploy script...")
    commands = [
        "apt-get update -qq",
        "apt-get install -y -qq python3 python3-pip python3-venv",
        "pip3 install --break-system-packages -r /opt/voice-flow-server/requirements.txt",
        "cp /opt/voice-flow-server/voiceflow-server.service /etc/systemd/system/",
        "systemctl daemon-reload",
    ]

    for cmd in commands:
        print(f"  $ {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode()
        err = stderr.read().decode()
        if err and "WARNING" not in err:
            print(f"    stderr: {err[:200]}")

    # 5. Start service
    print("\n[5/5] Starting service...")
    ssh.exec_command("systemctl enable voiceflow-server")
    stdin, stdout, stderr = ssh.exec_command("systemctl restart voiceflow-server")
    out = stdout.read().decode()
    err = stderr.read().decode()

    # Verify
    stdin, stdout, stderr = ssh.exec_command("sleep 2 && systemctl status voiceflow-server --no-pager")
    print(stdout.read().decode())

    stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8000/api/ping")
    ping_result = stdout.read().decode()
    print(f"\n  /api/ping → {ping_result}")

    ssh.close()

    if '"status":"ok"' in ping_result:
        print("\n=== Deploy successful! ===")
        print(f"Server: http://{HOST}:8000")
        print(f"Ping:   http://{HOST}:8000/api/ping")
    else:
        print("\n=== Deploy may have issues, check above ===")


if __name__ == "__main__":
    main()
