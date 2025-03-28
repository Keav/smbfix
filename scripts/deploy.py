import os
import yaml
import paramiko
import subprocess
from pathlib import Path

def load_config():
    """Load server configuration from YAML file."""
    config_path = Path(__file__).parent.parent / 'config' / 'servers.yaml'
    with open(config_path) as f:
        return yaml.safe_load(f)

def mount_smb(server):
    """Mount SMB share if not already mounted."""
    if not os.path.ismount(server['local_mount']):
        cmd = f"osascript -e 'mount volume \"smb://{server['user']}@{server['host']}/Share\"'"
        subprocess.run(cmd, shell=True, check=True)

def copy_script(server):
    """Copy the script to the SMB share."""
    script_path = Path(__file__).parent.parent / 'src' / 'smbfix_onepass.py'
    dest_path = Path(server['local_mount']) / 'smbfix_onepass.py'
    subprocess.run(['cp', str(script_path), str(dest_path)], check=True)

def run_remote_script(server):
    """Execute the script on the remote Mac mini via SSH."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(server['host'], username=server['user'])
        cmd = f'python3 {server["script_dest"]}/smbfix_onepass.py {server["smb_share"]}'
        stdin, stdout, stderr = ssh.exec_command(cmd)
        print(f"Output from {server['name']}:")
        print(stdout.read().decode())
        print(stderr.read().decode())
    finally:
        ssh.close()

def main():
    config = load_config()
    
    for server in config['servers']:
        print(f"\nDeploying to {server['name']}...")
        try:
            mount_smb(server)
            copy_script(server)
            run_remote_script(server)
            print(f"✅ Deployment to {server['name']} completed successfully")
        except Exception as e:
            print(f"❌ Error deploying to {server['name']}: {e}")

if __name__ == '__main__':
    main()