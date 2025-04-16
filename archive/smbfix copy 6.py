import os
import re
import sys
import subprocess
import getpass

# Define SMB-invalid characters
INVALID_CHARACTERS = re.compile(r'[\\/:*?"<>|+\[\]]')

# Store passwords securely for session
stored_passwords = {}
sudo_session_active = False

# **Helper function to clean filenames**
def clean_filename(entry):
    entry = entry.replace("\u00A0", " ")
    entry = INVALID_CHARACTERS.sub('-', entry)
    entry = re.sub(r'\s+', ' ', entry).strip()
    entry = re.sub(r' (\.[a-zA-Z0-9]+)$', r'\1', entry)
    return entry

# **Helper function to get unique filenames**
def get_unique_name(dirpath, name, is_directory=False):
    base_name, ext = os.path.splitext(name) if not is_directory else (name, "")
    i = 1
    new_name = name
    new_path = os.path.join(dirpath, new_name)

    while os.path.exists(new_path):
        new_name = f"{base_name}_{i}{ext}"
        new_path = os.path.join(dirpath, new_name)
        i += 1

    return new_path

# **Exclusion Criteria**
def should_exclude(path):
    return "iPhoto Library" in path or ".abbu/" in path or path.lower().endswith(".abbu")

# **Check if a file is locked**
def is_locked(path):
    result = subprocess.run(['find', path, '-flags', 'uchg'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return bool(result.stdout.strip())

# **Ensure sudo session stays active to avoid multiple password prompts**
def ensure_sudo_session():
    global sudo_session_active
    if not sudo_session_active:
        print("🔑 Establishing sudo session (you will be prompted once)...")
        result = subprocess.run(["sudo", "-v"], text=True)
        if result.returncode == 0:
            sudo_session_active = True
        else:
            print("❌ Failed to establish sudo session. You may be prompted for password multiple times.")

# **Unlock a locked file (Uses `sudo -u logged_in_user`)**
def unlock_file(path):
    if is_locked(path):
        logged_in_user = subprocess.run(["stat", "-f%Su", "/dev/console"], capture_output=True, text=True).stdout.strip()

        print(f"🔓 Unlocking file: {path}")
        print(f"🔑 Enter **current_user's** password (sudo required):")
        
        ensure_sudo_session()
        cmd = ["sudo", "-u", logged_in_user, "chflags", "-R", "nouchg", path]
        
        result = subprocess.run(cmd, text=True)
        if result.returncode == 0:
            print(f"✅ Unlocked: {path}")
        else:
            print(f"❌ Failed to unlock: {path}")

# **Fix Permissions (Uses `sudo -u logged_in_user`)**
def fix_permissions(path):
    if not os.access(path, os.W_OK):
        print(f"🔧 Fixing permissions for: {path}")
        
        ensure_sudo_session()
        cmd = ["sudo", "-u", subprocess.getoutput("stat -f%Su /dev/console"), "chmod", "-R", "700", path]
        
        result = subprocess.run(cmd, text=True)
        if result.returncode == 0:
            print(f"✅ Permissions fixed: {path}")
        else:
            print(f"❌ Failed to set permissions: {path}")

# **Fix Ownership (Run After Unlocking & Permission Fix)**
def fix_ownership(path, current_user):
    stat_info = os.stat(path)
    owner_uid = stat_info.st_uid

    if owner_uid != os.getuid():
        print(f"🔄 Fixing ownership: {path}")
        
        ensure_sudo_session()
        try:
            subprocess.run(["sudo", "chown", "-R", f"{current_user}:staff", path], check=True)
            print(f"✅ Ownership fixed: {path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to change ownership for {path}: {e}")

# **Find Folders with Wrong Owner**
def find_folders_with_wrong_owner(root_dir, current_user):
    print(f"🔍 Scanning for folders with incorrect ownership in: {root_dir}")
    incorrect_folders = []

    result = subprocess.run(["find", root_dir, "-type", "d", "!", "-user", current_user], 
                            capture_output=True, text=True)
    if result.stdout.strip():
        incorrect_folders = result.stdout.strip().split("\n")
    
    return incorrect_folders

# **Find Files with Wrong Owner**
def find_files_with_wrong_owner(root_dir, current_user):
    print(f"🔍 Scanning for files with incorrect ownership in: {root_dir}")
    incorrect_files = []

    result = subprocess.run(["find", root_dir, "-type", "f", "!", "-user", current_user], 
                            capture_output=True, text=True)
    if result.stdout.strip():
        incorrect_files = result.stdout.strip().split("\n")
    
    return incorrect_files

# **Prompt User for Ownership Fix Confirmation**
def confirm_and_fix_ownership(items, item_type, current_user):
    if items:
        print(f"\n⚠️ The following {len(items)} {item_type} require ownership changes:")
        for item in items:
            print(f"  - {item}")

        confirm = input(f"\nProceed with fixing ownership for {len(items)} {item_type}? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Ownership fixes cancelled.")
            return

        print(f"🛠️ Fixing ownership for {len(items)} {item_type}...")
        for item in items:
            fix_ownership(item, current_user)

    else:
        print(f"✅ All {item_type} have correct ownership.")

# **Process Files & Rename**
def process_files_and_folders(root_dir):
    current_user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()

    # **Find and List Incorrect Ownership Issues**
    incorrect_folders = find_folders_with_wrong_owner(root_dir, current_user)
    incorrect_files = find_files_with_wrong_owner(root_dir, current_user)

    # **Prompt for Fixing Ownership**
    confirm_and_fix_ownership(incorrect_folders, "folders", current_user)
    confirm_and_fix_ownership(incorrect_files, "files", current_user)

    rename_operations = []

    # **Process Files for Renaming**
    print(f"🔍 Scanning directory for rename issues: {root_dir}")
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True):
        if should_exclude(dirpath):
            continue

        for entry in filenames:
            entry_path = os.path.join(dirpath, entry)
            if should_exclude(entry_path):
                continue

            unlock_file(entry_path)  # Unlock before proceeding
            fix_permissions(entry_path)  # Fix permissions before renaming
            fix_ownership(entry_path, current_user)  # **Retry ownership change after unlocking**

            new_entry = clean_filename(entry)
            if new_entry != entry:
                new_entry_path = os.path.join(dirpath, new_entry)
                if os.path.exists(new_entry_path):
                    new_entry_path = get_unique_name(dirpath, new_entry)
                rename_operations.append((entry_path, new_entry_path))

    print("✅ Process completed.")

# **Run script with target directory**
if __name__ == "__main__":
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = '.'

    process_files_and_folders(root_dir)