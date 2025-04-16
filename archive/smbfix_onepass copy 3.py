import os
import re
import sys
import subprocess
import getpass

# Define invalid SMB characters
INVALID_CHARACTERS = re.compile(r'[\\/:*?"<>|+\[\]]')
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
    return "iPhoto Library" in path or ".abbu/" in path or path.lower().endswith(".abbu") or ".photoslibrary/" in path or path.lower().endswith(".photoslibrary")

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
    """Unlock a file only if it is locked, using sudo -u logged_in_user."""
    if is_locked(path):
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
    return False  # File was not locked

def unlock_folder(folder, current_user, logged_in_user):
    """Unlock a folder only if it is locked, using sudo -u logged_in_user."""
    if is_locked(folder):
        print(f"\n🔓 Unlocking folder: {folder}")
        if logged_in_user not in stored_passwords:
            stored_passwords[logged_in_user] = getpass.getpass(f"Password for {current_user} (to unlock folders): ")

        cmd = f'chflags -R nouchg "{folder}"'
        child = subprocess.run(["sudo", "-u", logged_in_user, "sh", "-c", cmd],
                               input=stored_passwords[logged_in_user], text=True)

        if child.returncode != 0:
            print(f"❌ Failed to unlock folder: {folder}")
            return False
        else:
            print(f"✅ Successfully unlocked folder: {folder}")
            return True
    return False  # Folder was not locked

def fix_ownership(path, current_user):
    """Fix ownership of a file or folder only if incorrect."""
    try:
        if get_owner(path) != os.getuid():
            print(f"🛠️ Changing ownership: {path}")
            subprocess.run(["sudo", "chown", "-R", f"{current_user}:staff", path], check=True)
            print(f"✅ Ownership fixed: {path}")
    except Exception as e:
        print(f"⚠️ Failed to change ownership: {path} - {e}")

def fix_permissions(path):
    """Ensure minimum permissions of 600 for files and 700 for folders."""
    try:
        permissions = get_permissions(path)
        if permissions is not None:
            if os.path.isdir(path) and permissions < 700:
                print(f"🛠️ Fixing folder permissions: {path}")
                subprocess.run(["chmod", "700", path], check=True)
                print(f"✅ Folder permissions fixed: {path}")
            elif os.path.isfile(path) and permissions < 600:
                print(f"🛠️ Fixing file permissions: {path}")
                subprocess.run(["chmod", "600", path], check=True)
                print(f"✅ File permissions fixed: {path}")
    except Exception as e:
        print(f"⚠️ Failed to fix permissions: {path} - {e}")

def rename_if_needed(path):
    """Check for invalid characters in file/folder name and rename if needed."""
    dirpath, name = os.path.split(path)
    new_name = clean_filename(name)
    if new_name != name:
        new_path = os.path.join(dirpath, new_name)
        print(f"✅ Renamed: {path} -> {new_path}")
        os.rename(path, new_path)
        return new_path
    return path

# ------------------ MAIN PROCESSING ------------------ #

def process_folder(folder, current_user, logged_in_user):
    """Process a folder: unlock if necessary, fix ownership, permissions, and process its contents."""
    if should_exclude(folder):
        return
    
    # Unlock folder first **only if necessary**
    unlock_folder(folder, current_user, logged_in_user)
    
    # Fix folder ownership
    fix_ownership(folder, current_user)
    
    # Fix folder permissions
    fix_permissions(folder)
    
    # Rename folder if needed
    folder = rename_if_needed(folder)

    # Process all files and subfolders
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                path = entry.path

                if should_exclude(path):
                    continue

                if entry.is_dir():
                    process_folder(path, current_user, logged_in_user)

                elif entry.is_file():
                    process_file(path, current_user, logged_in_user)

    except PermissionError:
        print(f"⚠️ Permission denied: {folder} - Skipping")
    except FileNotFoundError:
        print(f"⚠️ File not found: {folder} - Skipping")
    except Exception as e:
        print(f"⚠️ Unexpected error processing {folder}: {e}")

def process_file(file, current_user, logged_in_user):
    """Process a file: unlock (if locked), fix ownership, permissions, and rename."""
    if should_exclude(file):
        return

    # Unlock if needed
    unlock_file(file, current_user, logged_in_user)

    # Fix ownership
    fix_ownership(file, current_user)

    # Fix permissions
    fix_permissions(file)

    # Rename file if needed
    rename_if_needed(file)

def process_files_and_folders(root_dir):
    """Main function to process all files and folders in the given root directory."""
    current_user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
    logged_in_user = subprocess.run(["stat", "-f%Su", "/dev/console"], capture_output=True, text=True).stdout.strip()

    print(f"\n🔍 Scanning for issues in: {root_dir}")

    try:
        process_folder(root_dir, current_user, logged_in_user)
    except KeyboardInterrupt:
        print("\n🚫 Script interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"⚠️ Unexpected error: {e}")

    print("✅ Processing completed.")

# ------------------ SCRIPT ENTRY POINT ------------------ #

if __name__ == "__main__":
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = '.'

    process_files_and_folders(root_dir)