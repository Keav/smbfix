import os
import re
import sys

# Define SMB-forbidden characters
INVALID_CHARACTERS = re.compile(r'[\\/:*?"<>|+\[\]]')

def clean_filename(entry):
    """Fix filename by replacing invalid characters, removing extra spaces, and ensuring no space before extensions."""
    entry = entry.replace("\u00A0", " ")  # Convert non-breaking spaces to normal spaces
    entry = INVALID_CHARACTERS.sub('-', entry)  # Replace SMB-invalid characters
    entry = re.sub(r'\s+', ' ', entry).strip()  # Remove leading/trailing spaces and collapse multiple spaces
    
    # Remove space before file extensions (matches 'filename .ext')
    entry = re.sub(r' (\.[a-zA-Z0-9]+)$', r'\1', entry)

    return entry

def get_unique_filename(dirpath, filename, ext):
    """Generate a unique filename if one already exists."""
    i = 1
    new_filename = filename
    while os.path.exists(os.path.join(dirpath, f"{new_filename}{ext}")):
        new_filename = f"{filename}_{i}"
        i += 1
    return f"{new_filename}{ext}"

def should_exclude(path):
    """Check if a path should be excluded from processing (e.g., 'iPhoto Library')."""
    return "iPhoto Library" in path

def process_files_and_folders(root_dir):
    rename_operations = []  # Store renaming operations for review

    # First pass: Rename files inside directories before renaming directories
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        if should_exclude(dirpath):
            continue  # Skip directories that match the exclusion rule

        # Rename files first
        for entry in filenames:
            new_entry = clean_filename(entry)

            if new_entry != entry:  # Ensure all issues are fixed at once
                entry_path = os.path.join(dirpath, entry)
                new_entry_path = os.path.join(dirpath, new_entry)

                # Ensure we are not overwriting an existing file
                if os.path.exists(new_entry_path):
                    new_entry_path = get_unique_filename(dirpath, os.path.splitext(new_entry)[0], os.path.splitext(new_entry)[1])

                rename_operations.append((entry_path, new_entry_path))

        # Rename directories after processing files
        for entry in dirnames:
            if should_exclude(os.path.join(dirpath, entry)):
                continue  # Skip 'iPhoto Library' directories

            new_entry = clean_filename(entry)

            if new_entry != entry:  # Ensure all issues are fixed at once
                entry_path = os.path.join(dirpath, entry)
                new_entry_path = os.path.join(dirpath, new_entry)

                # Ensure new directory name doesn't conflict with existing names
                if os.path.exists(new_entry_path):
                    new_entry_path = get_unique_filename(dirpath, new_entry, "")

                rename_operations.append((entry_path, new_entry_path))

    # Display planned renames before execution
    if rename_operations:
        print("\nPlanned renaming operations:")
        for old, new in rename_operations:
            print(f"{old} -> {new}")

        # Ask for confirmation before applying renames
        confirm = input("\nProceed with renaming? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("Operation cancelled.")
            return

        # Perform renaming after confirmation
        for old, new in rename_operations:
            try:
                # Store original timestamps
                original_timestamps = os.stat(old)

                # Rename entry and preserve timestamps
                os.rename(old, new)
                os.utime(new, (original_timestamps.st_atime, original_timestamps.st_mtime))

                print(f"Renamed: {old} -> {new}")

            except Exception as e:
                print(f"Error renaming {old}: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = '.'  # Default to current directory

    process_files_and_folders(root_dir)
