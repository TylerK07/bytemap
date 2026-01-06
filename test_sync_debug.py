#!/usr/bin/env python3
"""Debug script to test YAML synchronization between tabs."""

from hexmap.core.spec_version import SpecStore

# Simulate the sync workflow
store = SpecStore()

# Step 1: App initialization with default schema
default_yaml = """format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  use: DataRecord
types:
  DataRecord:
    fields:
      - { name: magic, type: u32 }
"""
store.set_working_text(default_yaml)
print(f"1. After init: {len(store.get_working_text())} chars")
print(f"   Text starts with: {store.get_working_text()[:50]}")

# Step 2: Explore tab loads from spec_store
explore_text = store.get_working_text()
print(f"\n2. Explore tab loaded: {len(explore_text)} chars")
assert explore_text == default_yaml

# Step 3: User edits in Explore tab
edited_yaml = """format: record_stream
endian: little
framing:
  repeat: until_eof
record:
  use: DataRecord
types:
  DataRecord:
    fields:
      - { name: magic, type: u16 }  # CHANGED from u32
"""
print(f"\n3. User edits in Explore tab: {len(edited_yaml)} chars")
print(f"   Change: u32 -> u16")

# Step 4: User presses '3' to switch tabs
# This should trigger: _sync_to_spec_store() from SchemaEditor
store.set_working_text(edited_yaml)
print(f"\n4. Synced to spec_store: {len(store.get_working_text())} chars")

# Step 5: Chunking tab loads from spec_store
chunking_text = store.get_working_text()
print(f"\n5. Chunking tab loads: {len(chunking_text)} chars")
print(f"   Text starts with: {chunking_text[:50]}")

# Step 6: Verify sync
if "u16" in chunking_text:
    print("\n✅ SUCCESS: Chunking tab received the edited YAML")
else:
    print("\n❌ FAIL: Chunking tab did NOT receive the edited YAML")
    print(f"   Expected 'u16' in text, but got: {chunking_text[200:250]}")

assert chunking_text == edited_yaml, "Sync failed!"
print("\n✅ All sync tests passed!")
