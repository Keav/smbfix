import os
import re
import sys
import subprocess
import getpass

# Define invalid SMB characters
INVALID_CHARACTERS = re.compile(r'[\/:*?"<>|+\[\]]')
stored_passwords = {}

# ------------------ FILE & FOLDER CLEANUP FUNCTIONS ------------------ #

def clean_filename(entry):
    """Fix filename by replacing invalid characters, spaces, and ensuring proper formatting."""
    entry = entry.replace("\u00A0", " ")  # Replace non-breaking spaces
    entry = INVALID_CHARACTERS.sub('-', entry)  # Replace invalid chars
    entry = re.sub(r'\s+', ' ', entry).strip()  # Remove extra spaces
    entry = re.sub(r' (\.[a-zA-Z0-9]+)$', r'\1', entry)  # Remove space before file extension
    return entry

# ------------------ FILE & FOLDER CHECKS ------------------ #

def should_exclude(path):
    """Exclude iPhoto Library and .abbu files/folders."""
    return "iPhoto Library" in path or ".abbu/" in path or path.lower().endswith(".abbu")

def is_locked(path):
    """Check if a file or folder is locked."""
    result = subprocess.run(['find', path, '-flags', 'uchg'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return bool(result.stdout.strip())

def get_permissions(path):
    """Retrieve file/folder permissions (e.g., 644, 755)."""
    try:
        mode = oct(os.stat(path).st_mode)[-3:]  # Get last 3 digits of permission
        return int(mode)
    except Exception:
        return None

def get_owner(path):
    """Retrieve file owner UID."""
    try:
        return os.stat(path).st_uid
    except Exception:
        return None

# ------------------ FIX FUNCTIONS ------------------ #

def unlock_file(path, current_user, logged_in_user):
    """Unlock the file using sudo -u logged_in_user."""
    print(f"\n🔓 Unlocking file: {path}")
    if logged_in_user not in stored_passwords:
        stored_passwords[logged_in_user] = getpass.getpass(f"Password for {current_user} (to unlock files): ")

    cmd = f'chflags -R nouchg "{path}"'
    child = subprocess.run(["sudo", "-u", logged_in_user, "sh", "-c", cmd],
                           input=stored_passwords[logged_in_user], text=True)

    if child.returncode != 0:
        print(f"❌ Failed to unlock: {path}")
        return False
    else:
        print(f"✅ Successfully unlocked: {path}")
        return True

def fix_ownership(path, current_user):
    """Fix ownership of a file or folder if incorrect."""
    try:
        if get_owner(path) != os.getuid():
            print(f"🛠️ Changing ownership: {path}")
            subprocess.run(["sudo", "chown", "-R", f"{current_user}:staff", path], check=True)
            print(f"✅ Ownership fixed: {path}")
    except Exception as e:
        print(f"⚠️ Failed to change ownership: {path} - {e}")

def fix_permissions(path):
    """Ensure minimum permissions of 600 (owner read/write only)."""
    try:
        permissions = get_permissions(path)
        if permissions is not None and permissions < 600:
            print(f"🛠️ Fixing permissions: {path}")
            subprocess.run(["chmod", "600", path], check=True)
            print(f"✅ Permissions fixed: {path}")
    except Exception as e:
        print(f"⚠️ Failed to fix permissions: {path} - {e}")

# ------------------ MAIN PROCESSING ------------------ #

def process_files_and_folders(root_dir):
    """Process ownership, unlock files, set permissions, and rename files in a single pass."""
    current_user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
    logged_in_user = subprocess.run(["stat", "-f%Su", "/dev/console"], capture_output=True, text=True).stdout.strip()

    print(f"\n🔍 Scanning for issues in: {root_dir}")

    try:
        with os.scandir(root_dir) as entries:
            for entry in entries:
                path = entry.path
                if should_exclude(path):
                    continue

                if entry.is_dir():
                    fix_ownership(path, current_user)
                    new_name = clean_filename(entry.name)
                    if new_name != entry.name:
                        new_path = os.path.join(os.path.dirname(path), new_name)
                        os.rename(path, new_path)
                        print(f"✅ Renamed folder: {path} -> {new_path}")
                        path = new_path  # Update path to renamed folder
                    process_files_and_folders(path)  # Recursively process subdirectories
                
                if entry.is_file():
                    if is_locked(path):
                        unlock_file(path, current_user, logged_in_user)
                    fix_ownership(path, current_user)
                    fix_permissions(path)
                    new_name = clean_filename(entry.name)
                    if new_name != entry.name:
                        new_path = os.path.join(os.path.dirname(path), new_name)
                        os.rename(path, new_path)
                        print(f"✅ Renamed file: {path} -> {new_path}")
    except PermissionError:
        print(f"⚠️ Permission denied: {root_dir} - Skipping")
    except FileNotFoundError:
        print(f"⚠️ File not found: {root_dir} - Skipping")
    except Exception as e:
        print(f"⚠️ Unexpected error processing {root_dir}: {e}")

    print("✅ Processing completed.")

# ------------------ SCRIPT ENTRY POINT ------------------ #

if __name__ == "__main__":
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = '.'

    process_files_and_folders(root_dir)
