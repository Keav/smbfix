import os
import re
import sys
import subprocess
import getpass
import re
import unicodedata

# Define invalid SMB characters
#INVALID_CHARACTERS = re.compile(r'[\\/:*?"<>|+\[\]]')

# Extended regex to catch problem characters, including Unicode diacritics and control characters
PROBLEM_CHAR_REGEX = re.compile(r"[\x00-\x1F\x7F\uE000-\uF8FF\u0300-\u036F]")
INVALID_CHARACTERS = re.compile(r'[\\/:*?"<>|+\[\]]')  # Keep existing invalid SMB characters
stored_passwords = {}

# ------------------ FILE & FOLDER CLEANUP FUNCTIONS ------------------ #

#def clean_filename(entry):
#    """Fix filename by replacing invalid characters, spaces, and ensuring proper formatting."""
#    entry = entry.replace("\u00A0", " ")  # Replace non-breaking spaces
#    entry = INVALID_CHARACTERS.sub('-', entry)  # Replace invalid chars
#    entry = re.sub(r'\s+', ' ', entry).strip()  # Remove extra spaces
#    entry = re.sub(r' (\.[a-zA-Z0-9]+)$', r'\1', entry)  # Remove space before file extension
#    return entry

def clean_filename(entry):
    """Fix filename by replacing invalid characters, removing unnecessary spaces, and ensuring proper formatting."""
    entry = entry.replace("\u00A0", " ")  # Replace non-breaking spaces
    entry = INVALID_CHARACTERS.sub('-', entry)  # Replace invalid SMB characters
    entry = PROBLEM_CHAR_REGEX.sub("-", entry)  # Replace problematic Unicode characters with '-'
    entry = re.sub(r'\s+', ' ', entry).strip()  # Remove extra spaces
    entry = re.sub(r' (\.[a-zA-Z0-9]+)$', r'\1', entry)  # Remove space before file extension
    
    # Ensure periods are correctly formatted
    if not entry.startswith("."):  # Skip hidden/system files
        entry = re.sub(r'\.{2,}', '.', entry)  # Replace multiple periods with a single one
        entry = entry.rstrip('.')  # Remove trailing periods
    
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
        # Ensure we prompt for the password only once
        if logged_in_user not in stored_passwords:
            stored_passwords[logged_in_user] = getpass.getpass(f"Password for {current_user} (to unlock folders): ")

        # 🔄 Run the unlock command recursively for every locked folder
        cmd = f'find "{folder}" -flags +uchg'  # Find all locked subfolders
        locked_folders = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, text=True).stdout.strip().split("\n")

        for locked_folder in locked_folders:
            if locked_folder:  # Ensure we don't process empty lines
                print(f"\n🔓 Unlocking folder: {locked_folder}", flush=True)  # ✅ Now prints every folder

                # Run chflags on each folder separately
                unlock_cmd = f'chflags -R nouchg "{locked_folder}"'
                child = subprocess.run(["sudo", "-u", logged_in_user, "sh", "-c", unlock_cmd],
                                       input=stored_passwords[logged_in_user], text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                # ✅ Capture and display subprocess output
                if child.returncode != 0:
                    print(f"❌ Failed to unlock: {locked_folder} - {child.stderr.strip()}")
                else:
                    print(f"✅ Successfully unlocked: {locked_folder}")

    return False  # If nothing was locked, return false

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

    
#def rename_if_needed(path):
#    """Check for invalid characters in file/folder name and rename if needed, ensuring uniqueness."""
#    dirpath, name = os.path.split(path)
#    new_name = clean_filename(name)
#    
#    if new_name != name:
#        new_path = os.path.join(dirpath, new_name)
#        
#        # Ensure the new name does not already exist
#        counter = 1
#        while os.path.exists(new_path):
#            base, ext = os.path.splitext(new_name)  # Separate base name and extension
#            new_path = os.path.join(dirpath, f"{base}_{counter}{ext}")  # Append counter
#            counter += 1
#        
#        print(f"✅ Renamed: {path} -> {new_path}")
#        os.rename(path, new_path)
#        return new_path  # Return new path in case further processing is needed
#
#    return path  # Return original path if no renaming was needed


def rename_if_needed(path):
    """Check for invalid characters in file/folder name, preview changes, and confirm before renaming."""
    dirpath, name = os.path.split(path)
    new_name = clean_filename(name)

    # If no changes are needed, return early
    if new_name == name:
        return path

    new_path = os.path.join(dirpath, new_name)

    # Ensure the new name does not already exist
    counter = 1
    while os.path.exists(new_path):
        base, ext = os.path.splitext(new_name)  # Separate base name and extension
        new_path = os.path.join(dirpath, f"{base}_{counter}{ext}")  # Append counter
        counter += 1

    # Preview the rename
    print(f"\n🔍 Detected issue in filename: {path}")
    print(f"   ➡ Proposed rename: {new_path}")

    # Ask for confirmation
    response = input("Apply this rename? (yes/no): ").strip().lower()
    if response not in ["yes", "y"]:
        print("❌ Rename skipped.")
        return path  # Return original path if skipped

    # Apply rename
    try:
        os.rename(path, new_path)
        print(f"✅ Renamed: {path} → {new_path}")
        return new_path  # Return new path in case further processing is needed
    except Exception as e:
        print(f"❌ Error renaming {path}: {e}")
        return path  # Return original path if renaming fails

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