import os
import sys

# Define the problematic character
PROBLEM_CHAR = "\x05"  # ASCII ENQ (0x05)

# Get directory to scan (default: current directory)
search_path = sys.argv[1] if len(sys.argv) > 1 else "."

# Find all files and directories with the problematic character
problem_files = []
for root, dirs, files in os.walk(search_path):
    for name in dirs + files:  # Check both files and folders
        if PROBLEM_CHAR in name:
            problem_files.append(os.path.join(root, name))

# If no problematic files are found, exit
if not problem_files:
    print(f"✅ No problematic filenames found in '{search_path}'.")
    exit(0)

# Display problem files before renaming
print("\n⚠️  Problematic filenames detected:\n")
for f in problem_files:
    print(f"  - {f}")

# Prompt user for confirmation
response = input("\n🔄 Do you want to rename these files? (yes/no): ").strip().lower()

if response not in ["yes", "y"]:
    print("❌ No changes were made.")
    exit(0)

# Rename each problematic file
print("\n🔄 Renaming files...\n")
for old_path in problem_files:
    new_name = os.path.basename(old_path).replace(PROBLEM_CHAR, "")
    new_path = os.path.join(os.path.dirname(old_path), new_name)

    try:
        os.rename(old_path, new_path)
        print(f"✅ Renamed: {old_path} → {new_path}")
    except Exception as e:
        print(f"❌ Error renaming {old_path}: {e}")

print("\n🎉 Done! Check your files.")