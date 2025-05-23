import os
import re
import sys
import subprocess
import getpass
import platform

# Add the keyring import for secure password storage
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# Define invalid SMB characters
PROBLEM_CHAR_REGEX = re.compile(r"[\x00-\x1F\x7F\uE000-\uF8FF\u0300-\u036F]")
INVALID_CHARACTERS = re.compile(r'[\\/:*?"<>|+\[\]]')  # Keep existing invalid SMB characters
# Windows reserved names (case-insensitive)
RESERVED_NAMES = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)]
stored_passwords = {}
sudo_timestamp_refreshed = False  # Track if we've refreshed the sudo timestamp

# Platform detection
IS_MACOS = platform.system() == "Darwin"  
IS_SYNOLOGY = os.path.exists("/etc/synoinfo.conf")

# ------------------ CREDENTIAL MANAGEMENT ------------------ #

def get_stored_password(username):
    """Get password from keyring if available, otherwise return None."""
    if KEYRING_AVAILABLE:
        try:
            password = keyring.get_password("smbfix", username)
            if password:
                print(f"✅ Found stored credentials for {username}")
                return password
        except Exception as e:
            print(f"⚠️ Could not retrieve stored password: {e}")
    return None

def store_password(username, password):
    """Store password in keyring if available."""
    if KEYRING_AVAILABLE:
        try:
            keyring.set_password("smbfix", username, password)
            print(f"✅ Stored credentials for {username}")
            return True
        except Exception as e:
            print(f"⚠️ Could not store password: {e}")
    return False

def get_password(username, prompt_message=None):
    """Get password from storage or prompt user if not stored."""
    global stored_passwords
    
    # Check if already in memory for this session
    if username in stored_passwords:
        return stored_passwords[username]
    
    # Try to get from keyring
    password = get_stored_password(username)
    
    # If not in keyring, prompt user
    if not password:
        prompt_message = prompt_message or f"Password for {username} (will be securely stored): "
        password = getpass.getpass(prompt_message)
        
        # Store in keyring for future use
        if password and KEYRING_AVAILABLE:
            store_password(username, password)
    
    # Store in memory for this session
    stored_passwords[username] = password
    return password

def refresh_sudo_timestamp(password):
    """Initialize sudo session to avoid repeated password prompts during script execution."""
    global sudo_timestamp_refreshed
    
    if sudo_timestamp_refreshed:
        return True
    
    print("🔑 Initializing sudo session...")
    cmd = 'echo "Initializing sudo session"'
    result = subprocess.run(
        ["sudo", "-S", "sh", "-c", cmd],
        input=password + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    if result.returncode == 0:
        sudo_timestamp_refreshed = True
        return True
    else:
        print(f"⚠️ Failed to initialize sudo session: {result.stderr}")
        return False

# ------------------ ENVIRONMENT CHECK ------------------ #

def check_environment():
    """Check if all required modules are available and the environment is correctly set up."""
    required_modules = {
        'os': 'Core functionality for file operations',
        're': 'Regular expressions for pattern matching',
        'sys': 'System-specific parameters and functions',
        'subprocess': 'Subprocess management',
        'getpass': 'Secure password input',
        'platform': 'Platform identification'
    }
    
    optional_modules = {
        'keyring': 'Secure credential storage'
    }
    
    print("\n🔍 Checking Python environment...\n")
    print(f"Python version: {platform.python_version()}")
    print(f"Platform: {platform.platform()}")
    print(f"System: {platform.system()} {platform.release()}")
    
    # Check for required modules
    missing = []
    for module, description in required_modules.items():
        try:
            __import__(module)
            print(f"✅ {module}: Found - {description}")
        except ImportError:
            print(f"❌ {module}: Missing - {description}")
            missing.append(module)
    
    # Check for optional modules
    for module, description in optional_modules.items():
        try:
            __import__(module)
            print(f"✅ {module}: Found - {description}")
        except ImportError:
            print(f"⚠️ {module}: Not found - {description}")
            print(f"  To enable secure credential storage: pip install {module}")

    print("\n🔍 Checking Python environment...\n")
    print(f"Python version: {platform.python_version()}")
    print(f"Platform: {platform.platform()}")
    print(f"System: {platform.system()} {platform.release()}")
    
    # Check for required modules
    missing = []
    for module, description in required_modules.items():
        try:
            __import__(module)
            print(f"✅ {module}: Found - {description}")
        except ImportError:
            print(f"❌ {module}: Missing - {description}")
            missing.append(module)
    
    # Check for administrative permissions on macOS
    if platform.system() == "Darwin":
        try:
            # Try a simple sudo command to check if sudo access works
            with open(os.devnull, 'w') as DEVNULL:
                subprocess.check_call(["sudo", "-n", "echo", "Testing sudo"], 
                                     stdout=DEVNULL, stderr=DEVNULL)
            print("✅ sudo access: Available - Can execute administrative commands")
        except subprocess.CalledProcessError:
            print("⚠️ sudo access: Requires password - Will prompt during execution")
        except Exception:
            print("⚠️ sudo access: Unknown - May have issues with permission operations")
    
    if missing:
        print("\n❌ Environment check failed. Missing required modules.")
        print("Install missing modules with: pip install " + " ".join(missing))
        return False
    else:
        print("\n✅ Environment check passed. All required modules are available.")
        return True

# ------------------ FILE & FOLDER CLEANUP FUNCTIONS ------------------ #

def is_reserved_name(name):
    """Check if a name is a Windows reserved name (ignoring extension)."""
    basename = os.path.splitext(name)[0]
    return basename.upper() in RESERVED_NAMES

def clean_filename(entry):
    """Fix filename by replacing invalid characters, removing unnecessary spaces, and ensuring proper formatting."""
    # Log problematic filenames when debugging is needed
    original_entry = entry
    
    if not entry:
        print(f"⚠️ Warning: Empty filename detected, using 'unnamed_file' instead")
        return "unnamed_file"  # Handle empty filenames
    
    # Check if the name actually needs to be cleaned
    has_invalid_chars = (INVALID_CHARACTERS.search(entry) or 
                         PROBLEM_CHAR_REGEX.search(entry) or 
                         "\u00A0" in entry or
                         is_reserved_name(entry) or
                         re.search(r'\.{2,}', entry) or
                         entry.endswith('.') or  # This check catches trailing periods
                         entry.endswith(' ') or  # Check for trailing spaces
                         entry.startswith(' ') or # Check for leading spaces
                         re.search(r'\s{2,}', entry) or  # Check for multiple consecutive spaces
                         ' .' in entry)
    
    if not has_invalid_chars:
        return entry  # Return unchanged if already valid
    
    # Initial replacements for invalid characters
    entry = entry.replace("\u00A0", " ")  # Replace non-breaking spaces
    entry = INVALID_CHARACTERS.sub('-', entry)  # Replace invalid SMB characters
    entry = PROBLEM_CHAR_REGEX.sub("-", entry)  # Replace problematic Unicode characters with '-'
    
    # Handle file extension separately to ensure proper cleanup
    base_name, ext = os.path.splitext(entry)
    
    # Special handling for files like "April ....doc" to avoid "April .doc"
    # First normalize spaces
    base_name = re.sub(r'\s+', ' ', base_name).strip()
    
    # SPECIAL HANDLING: Check for trailing periods in base_name regardless of hidden status
    if base_name.endswith('.'):
        # Replace trailing period with dash for ALL files including hidden ones
        base_name = base_name[:-1] + '-'
    
    # General period handling for non-hidden files
    if not base_name.startswith('.'):  # Skip some period handling for hidden files
        # Replace sequences of periods with single period
        base_name = re.sub(r'\.{2,}', '.', base_name)
        # Remove spaces before periods
        base_name = re.sub(r' \.$', '.', base_name)
        base_name = re.sub(r' \.', '.', base_name)
    
    # Handle empty name after cleaning
    if not base_name and ext:
        print(f"⚠️ Warning: Filename '{original_entry}' became empty after cleaning, using 'file' as base name")
        base_name = "file"
    elif not base_name:
        print(f"⚠️ Warning: Filename '{original_entry}' became empty after cleaning, using 'unnamed_file' instead")
        return "unnamed_file"
    
    # Ensure no spaces before extension
    entry = base_name + ext
    
    # Final SMB-compatibility check
    # Remove any remaining spaces before extension that might have been missed
    entry = re.sub(r' (\.[a-zA-Z0-9]+)$', r'\1', entry)
    
    # Final cleanup pass
    entry = entry.strip()  # No leading/trailing spaces in final result
    
    # Trailing period check as final step (catches any trailing periods added during processing)
    if entry.endswith('.') and not entry == '.':
        entry = entry[:-1] + '-'
    
    # Handle Windows reserved names by appending an underscore
    if is_reserved_name(entry):
        entry = entry + "_"
    
    # Make sure we've fixed ALL issues by recursively cleaning
    # if the name has changed and might still have issues
    if entry != original_entry:
        # Check if there are still issues to fix
        still_has_issues = (INVALID_CHARACTERS.search(entry) or 
                           PROBLEM_CHAR_REGEX.search(entry) or 
                           "\u00A0" in entry or
                           is_reserved_name(entry) or
                           re.search(r'\.{2,}', entry) or
                           entry.endswith('.') or
                           ' .' in entry)
        
        if still_has_issues:
            print(f"🔄 Multiple issues detected in '{original_entry}', performing additional cleaning")
            entry = clean_filename(entry)  # Recursive call to fix remaining issues
    
    return entry

# ------------------ FILE & FOLDER CHECKS ------------------ #

def should_exclude(path):
    """Exclude iPhoto Library and .abbu files/folders."""
    return "iPhoto Library" in path or ".abbu/" in path or path.lower().endswith(".abbu") or ".photoslibrary/" in path or path.lower().endswith(".photoslibrary")

def is_locked(path):
    """Check if a file or folder is locked. Only applicable for macOS."""
    if not IS_MACOS:
        return False
        
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
    """Unlock a file only if it is locked, using sudo."""
    global sudo_timestamp_refreshed
    
    if not IS_MACOS:
        return False  # Skip for non-macOS systems
        
    if is_locked(path):
        print(f"\n🔓 Unlocking file: {path}")
        
        # Get the password (from keyring or prompt)
        password = get_password(current_user)
            
        # Initialize sudo session if needed
        if not sudo_timestamp_refreshed:
            refresh_sudo_timestamp(password)

        cmd = f'chflags -R nouchg "{path}"'
        child = subprocess.run(["sudo", "sh", "-c", cmd],
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if child.returncode != 0:
            print(f"❌ Failed to unlock: {path}")
            return False
        else:
            print(f"✅ Successfully unlocked: {path}")
            return True
    return False  # File was not locked

def fix_ownership(path, current_user):
    """Fix ownership of a file or folder only if incorrect."""
    global sudo_timestamp_refreshed
    
    if not IS_MACOS:  # Skip for non-macOS systems
        return
        
    try:
        if get_owner(path) != os.getuid():
            print(f"🛠️ Changing ownership: {path}")
            
            # Get the password (from keyring or prompt)
            password = get_password(current_user)
                
            # Initialize sudo session if needed
            if not sudo_timestamp_refreshed:
                refresh_sudo_timestamp(password)
                
            subprocess.run(["sudo", "chown", "-R", f"{current_user}:staff", path], check=True)
            print(f"✅ Ownership fixed: {path}")
    except Exception as e:
        print(f"⚠️ Failed to change ownership: {path} - {e}")

def fix_permissions(path):
    """Ensure minimum permissions of 600 for files and 700 for folders."""
    if not IS_MACOS:  # Skip for non-macOS systems
        return
        
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

def rename_if_needed(path, rename_list):
    """Check for invalid characters in file/folder name and store changes for bulk confirmation."""
    dirpath, name = os.path.split(path)
    
    # Skip empty names (shouldn't happen but just in case)
    if not name:
        print(f"⚠️ Warning: Empty filename detected at path: {path}")
        return path
        
    new_name = clean_filename(name)

    if new_name == name:
        return path  # No changes needed

    # Log what's being changed for debugging
    print(f"🔍 Debug: Cleaning '{name}' to '{new_name}' in '{dirpath}'")
    
    new_path = os.path.join(dirpath, new_name)

    # Ensure the new name does not already exist
    counter = 1
    while os.path.exists(new_path):
        base, ext = os.path.splitext(new_name)
        new_path = os.path.join(dirpath, f"{base}_{counter}{ext}")
        counter += 1

    rename_list.append((path, new_path))
    return new_path

# ------------------ MAIN PROCESSING ------------------ #

def process_folder(folder, current_user, logged_in_user, rename_list):
    """Process a folder: unlock if necessary, fix ownership, permissions, and process its contents."""
    if should_exclude(folder):
        return
    
    if IS_MACOS:
        unlock_file(folder, current_user, logged_in_user)
        fix_ownership(folder, current_user)
        fix_permissions(folder)

    # Store the original path before any potential renaming for directory scanning
    original_folder = folder
    
    # Add the folder to rename list if needed, but keep using original path for scanning
    new_folder = rename_if_needed(folder, rename_list)

    try:
        # Use the original folder path for scanning, as the rename hasn't happened yet
        with os.scandir(original_folder) as entries:
            for entry in entries:
                path = entry.path
                if should_exclude(path):
                    continue
                if entry.is_dir():
                    process_folder(path, current_user, logged_in_user, rename_list)
                elif entry.is_file():
                    process_file(path, current_user, logged_in_user, rename_list)
    except Exception as e:
        print(f"⚠️ Error processing {folder}: {e}")

def process_file(file, current_user, logged_in_user, rename_list):
    """Process a file: unlock (if locked), fix ownership, permissions, and rename."""
    if should_exclude(file):
        return

    if IS_MACOS:
        unlock_file(file, current_user, logged_in_user)
        fix_ownership(file, current_user)
        fix_permissions(file)

    rename_if_needed(file, rename_list)

def process_files_and_folders(root_dir):
    """Main function to process all files and folders, preview changes, and apply them in bulk."""
    global sudo_timestamp_refreshed
    
    current_user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
    logged_in_user = ""
    
    # Get absolute path of root directory for consistent handling
    root_dir = os.path.abspath(root_dir)
    
    if IS_MACOS:
        logged_in_user = subprocess.run(["stat", "-f%Su", "/dev/console"], capture_output=True, text=True).stdout.strip()
        print(f"🍎 Running on macOS - Full fixes including permissions, ownership and locks")
        
        if not KEYRING_AVAILABLE:
            print("⚠️ Keyring package not available. Passwords will only be stored for this session.")
            print("   Install keyring for persistent password storage: pip install keyring")
        else:
            print("✅ Using keyring for secure password storage")
            
    elif IS_SYNOLOGY:
        print(f"📦 Running on Synology NAS - Limited to filename fixes only")
    else:
        print(f"🖥️ Running on {platform.system()} - Limited to filename fixes only")

    print(f"\n🔍 Scanning for issues in: {root_dir}")

    rename_list = []
    
    try:
        # Apply permissions/ownership fixes to root directory if needed, but don't rename it
        if IS_MACOS:
            unlock_file(root_dir, current_user, logged_in_user)
            fix_ownership(root_dir, current_user)
            fix_permissions(root_dir)
            
        # Process contents of root directory
        try:
            with os.scandir(root_dir) as entries:
                for entry in entries:
                    path = entry.path
                    if should_exclude(path):
                        continue
                    if entry.is_dir():
                        process_folder(path, current_user, logged_in_user, rename_list)
                    elif entry.is_file():
                        process_file(path, current_user, logged_in_user, rename_list)
        except Exception as e:
            print(f"⚠️ Error processing root directory {root_dir}: {e}")
                
    except KeyboardInterrupt:
        print("\n🚫 Script interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"⚠️ Unexpected error: {e}")

    if not rename_list:
        print("✅ No problematic filenames found.")
        return

    # Sort the rename list by path depth (descending) to process deepest paths first
    # This ensures we rename child items before their parent folders
    rename_list.sort(key=lambda x: x[0].count(os.sep), reverse=True)

    print("\n⚠️ The following files/folders will be renamed:\n")
    for old_path, new_path in rename_list:
        # Using colorful output and bold arrow for better visibility
        print(f"  - \033[33m{old_path}\033[0m \033[1;36m==>\033[0m \033[32m{new_path}\033[0m")

    response = input("\n🔄 Apply all renames? (yes/no): ").strip().lower()
    if response not in ["yes", "y"]:
        print("❌ No changes were made.")
        return

    # Perform renames in the sorted order (deepest paths first)
    for old_path, new_path in rename_list:
        try:
            os.rename(old_path, new_path)
            print(f"✅ Renamed: \033[33m{old_path}\033[0m \033[1;36m==>\033[0m \033[32m{new_path}\033[0m")
        except Exception as e:
            print(f"❌ Error renaming {old_path}: {e}")

    print("\n🎉 Done! Check your files.")

if __name__ == "__main__":
    # Check if we're being asked to verify the environment
    if len(sys.argv) > 1 and sys.argv[1] == "--check-env":
        check_environment()
        sys.exit(0)
    
    # Check if we're being asked to forget stored credentials
    if len(sys.argv) > 1 and sys.argv[1] == "--forget-credentials":
        if KEYRING_AVAILABLE:
            current_user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
            try:
                keyring.delete_password("smbfix", current_user)
                print(f"✅ Removed stored credentials for {current_user}")
            except:
                print(f"⚠️ No stored credentials found for {current_user}")
        else:
            print("⚠️ Keyring package not available. Cannot manage stored credentials.")
            print("   Install keyring for credential management: pip install keyring")
        sys.exit(0)
        
    root_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    process_files_and_folders(root_dir)