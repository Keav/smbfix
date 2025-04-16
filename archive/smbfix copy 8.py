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

### **🔹 Helper Functions**
def clean_filename(entry):
    entry = entry.replace("\u00A0", " ")
    entry = INVALID_CHARACTERS.sub('-', entry)
    entry = re.sub(r'\s+', ' ', entry).strip()
    entry = re.sub(r' (\.[a-zA-Z0-9]+)$', r'\1', entry)
    return entry

def should_exclude(path):
    return "iPhoto Library" in path or ".abbu/" in path or path.lower().endswith(".abbu")

def ensure_sudo_session():
    global sudo_session_active
    if not sudo_session_active:
        print("🔑 Establishing sudo session (you will be prompted once)...")
        sys.stdout.flush()  # Ensure message is printed immediately
        result = subprocess.run(["sudo", "-v"], text=True)
        if result.returncode == 0:
            sudo_session_active = True
        else:
            print("❌ Failed to establish sudo session. You may be prompted multiple times.")

### **🔹 Fixing Issues**
def fix_ownership(path, current_user):
    if not os.path.exists(path):
        print(f"⚠️ Skipping ownership fix (file no longer exists): {path}")
        return

    try:
        stat_info = os.stat(path)
        owner_uid = stat_info.st_uid

        if owner_uid != os.getuid():
            print(f"🔄 Fixing ownership: {path}")
            sys.stdout.flush()  # Ensure message appears immediately
            
            ensure_sudo_session()
            subprocess.run(["sudo", "chown", "-R", f"{current_user}:staff", path], check=True)
            print(f"✅ Ownership fixed: {path}")

    except FileNotFoundError:
        print(f"⚠️ Skipping ownership fix (file no longer exists): {path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to change ownership for {path}: {e}")

### **🔹 Ownership Checking Functions**
def find_folders_with_wrong_owner(root_dir, current_user):
    print(f"🔍 Scanning for folders with incorrect ownership in: {root_dir}")
    sys.stdout.flush()
    
    incorrect_folders = []

    result = subprocess.run(["find", root_dir, "-type", "d", "!", "-user", current_user], 
                            capture_output=True, text=True)
    if result.stdout.strip():
        incorrect_folders = result.stdout.strip().split("\n")
    
    return incorrect_folders

def find_files_with_wrong_owner(root_dir, current_user):
    print(f"🔍 Scanning for files with incorrect ownership in: {root_dir}")
    sys.stdout.flush()
    
    incorrect_files = []

    result = subprocess.run(["find", root_dir, "-type", "f", "!", "-user", current_user], 
                            capture_output=True, text=True)
    if result.stdout.strip():
        incorrect_files = result.stdout.strip().split("\n")
    
    return incorrect_files

### **🔹 Ownership Confirmation and Fix**
def confirm_and_fix_ownership(items, item_type, current_user):
    if items:
        print(f"🛠️ Found {len(items)} {item_type} with incorrect ownership:")
        for item in items:
            print(f"  - {item}")
        
        confirm = input(f"\nProceed with fixing ownership for {len(items)} {item_type}? (yes/no): ").strip().lower()
        if confirm == "yes":
            print(f"🔄 Fixing ownership for {len(items)} {item_type}...")
            sys.stdout.flush()
            
            for item in items:
                fix_ownership(item, current_user)
        else:
            print("❌ Ownership fix cancelled.")
    else:
        print(f"✅ No ownership issues found for {item_type}.")

### **🔹 Renaming Function**
def rename_invalid_files_and_folders(root_dir):
    rename_operations = []

    print("\n🔍 Scanning for renaming issues...")
    sys.stdout.flush()  # Force this message to appear before scanning

    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True):
        if should_exclude(dirpath):
            continue

        for dirname in dirnames:
            dirpath_full = os.path.join(dirpath, dirname)
            new_dirname = clean_filename(dirname)

            if new_dirname != dirname:
                new_dirpath = os.path.join(dirpath, new_dirname)
                rename_operations.append((dirpath_full, new_dirpath))

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            new_filename = clean_filename(filename)

            if new_filename != filename:
                new_filepath = os.path.join(dirpath, new_filename)
                rename_operations.append((filepath, new_filepath))

    if rename_operations:
        print("\n🔄 Planned renaming operations:")
        for old, new in rename_operations:
            print(f"  - {old} -> {new}")

        confirm = input("\nProceed with renaming? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Renaming cancelled.")
            return

        for old, new in rename_operations:
            try:
                os.rename(old, new)
                print(f"✅ Renamed: {old} -> {new}")
            except Exception as e:
                print(f"❌ Failed renaming {old}: {e}")
    else:
        print("✅ No renaming issues found.")

### **🔹 Process Function**
def process_files_and_folders(root_dir):
    current_user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()

    incorrect_folders = find_folders_with_wrong_owner(root_dir, current_user)
    incorrect_files = find_files_with_wrong_owner(root_dir, current_user)
    
    confirm_and_fix_ownership(incorrect_folders, "folders", current_user)
    confirm_and_fix_ownership(incorrect_files, "files", current_user)

    rename_invalid_files_and_folders(root_dir)

    print("✅ Process completed.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = '.'

    process_files_and_folders(root_dir)