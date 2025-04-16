import os
import re
import sys
import time
import subprocess
import getpass
import pexpect

# Define SMB-forbidden characters
INVALID_CHARACTERS = re.compile(r'[\\/:*?"<>|+\[\]]')

def clean_filename(entry):
    """Fix filename by replacing invalid characters, removing extra spaces, and ensuring no space before extensions."""
    entry = entry.replace("\u00A0", " ")  # Convert non-breaking spaces to normal spaces
    entry = INVALID_CHARACTERS.sub('-', entry)  # Replace SMB-invalid characters
    entry = re.sub(r'\s+', ' ', entry).strip()  # Remove leading/trailing spaces and collapse multiple spaces
    entry = re.sub(r' (\.[a-zA-Z0-9]+)$', r'\1', entry)  # Remove space before extensions
    return entry

def get_unique_name(dirpath, name, is_directory=False):
    """Generate a unique name in the same directory if one already exists."""
    base_name, ext = os.path.splitext(name) if not is_directory else (name, "")
    i = 1
    new_name = name
    new_path = os.path.join(dirpath, new_name)

    while os.path.exists(new_path):
        new_name = f"{base_name}_{i}{ext}"
        new_path = os.path.join(dirpath, new_name)
        i += 1

    return new_path

def request_password():
    """Prompt for the logged-in user's password only when needed."""
    global stored_password
    if stored_password is None:
        stored_password = getpass.getpass(f"Enter password for {logged_in_user}: ")

def run_su_command(command):
    """Run a command as logged_in_user using su, only requesting the password if needed."""
    request_password()  # Ask for password only on first use

    try:
        child = pexpect.spawn(f"su - {logged_in_user}", encoding='utf-8', timeout=10)
        child.expect("Password:")
        child.sendline(stored_password)
        child.expect(["$", "#"])
        child.sendline(command)
        child.expect(["$", "#"])
        output = child.before.strip()
        child.sendline("exit")
        child.expect(pexpect.EOF)
        return output
    except Exception as e:
        print(f"⚠️ Failed to execute command: {command}\nError: {e}")
        return None

def fix_permissions_and_unlock(path):
    """Unlock and fix permissions as `logged_in_user`, then apply `chown` as session user."""
    try:
        abs_path = os.path.abspath(path)
        current_user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()

        print(f"\n🔑 Checking permissions for: {abs_path}")

        # Check if the file is locked
        locked_status = subprocess.run(["ls", "-ldO", abs_path], capture_output=True, text=True).stdout
        if "uchg" not in locked_status:
            print(f"✅ {abs_path} is not locked. No unlock needed.")
        else:
            # Unlock file & apply chmod as `logged_in_user`
            print(f"🔓 Unlocking and setting permissions for {abs_path}...")
            command = f'chflags -R nouchg "{abs_path}" && chmod 700 "{abs_path}"'
            output = run_su_command(command)

            # Print debug output
            print(f"🔍 Debug output from `su` command:\n{output}")

            # Verify if `chflags` actually worked
            locked_status = subprocess.run(["ls", "-ldO", abs_path], capture_output=True, text=True).stdout
            if "uchg" in locked_status:
                print(f"⚠️ Failed to unlock {abs_path}. It may still be locked.")
                return
            print(f"✅ Unlocked and applied chmod 700")

        # Check current ownership before attempting chown
        ownership_status = subprocess.run(["ls", "-l", abs_path], capture_output=True, text=True).stdout
        print(f"🔍 Ownership before `chown`:\n{ownership_status}")

        # Extract current file owner
        file_owner = subprocess.run(["stat", "-f%Su", abs_path], capture_output=True, text=True).stdout.strip()

        if file_owner == current_user:
            print(f"✅ Ownership is already correct: {file_owner}")
            return  # Skip `chown` if ownership is already correct

        # Run `chown` as the current terminal session user (User A)
        chown_result = subprocess.run(["chown", f"{current_user}:staff", abs_path], capture_output=True, text=True)

        if chown_result.returncode != 0:
            print(f"⚠️ Failed to change ownership for {abs_path}: {chown_result.stderr}")
        else:
            print(f"✅ Set ownership to {current_user}:staff")

    except subprocess.CalledProcessError as e:
        print(f"⚠️ Failed to apply permissions or unlock {abs_path}: {e}")

def process_files_and_folders(root_dir):
    folder_name = os.path.basename(os.path.abspath(root_dir))
    log_file_name = f"rename_log - {folder_name}.txt"
    log_file_path = os.path.join(os.getcwd(), log_file_name)

    rename_operations = []

    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"Rename operations in '{root_dir}':\n\n")
        log_file.flush()

        for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
            for entry in filenames:
                entry_path = os.path.join(dirpath, entry)
                new_entry = clean_filename(entry)

                if new_entry != entry:
                    new_entry_path = os.path.join(dirpath, new_entry)

                    if os.path.exists(new_entry_path):
                        new_entry_path = get_unique_name(dirpath, new_entry)

                    rename_operations.append((entry_path, new_entry_path))
                    log_file.write(f"{entry_path} -> {new_entry_path}\n")
                    log_file.flush()
                    print(f"Found issue: {entry_path} -> {new_entry_path}")

        if rename_operations:
            print("\nPlanned renaming operations:")
            for old, new in rename_operations:
                print(f"{old} -> {new}")

            confirm = input("\nProceed with renaming? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Operation cancelled. Log file remains available.")
                return

            for old, new in rename_operations:
                while True:
                    try:
                        os.rename(old, new)
                        print(f"Renamed: {old} -> {new}")
                        break

                    except PermissionError:
                        print(f"\n❌ Permission error: Cannot rename {old}.")
                        print(f"Attempting to fix permissions and unlock {old}...")

                        fix_permissions_and_unlock(old)
                        print("Retrying...")
                        time.sleep(2)
                        continue  # Retry rename

        print(f"\nLog saved to: {log_file_path}")

if __name__ == "__main__":
    global stored_password
    stored_password = None  # Store password securely after first request

    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = '.'

    # Get the logged-in user once at the start
    logged_in_user = subprocess.run(["stat", "-f%Su", "/dev/console"], capture_output=True, text=True).stdout.strip()

    process_files_and_folders(root_dir)