"""Debug switch discrimination."""

from pathlib import Path

from hexmap.core.io import PagedReader
from hexmap.core.yaml_grammar import parse_yaml_grammar
from hexmap.core.yaml_parser import RecordParser

# Simplified YAML
YAML = """format: record_stream

framing:
  repeat: until_eof

record:
  switch:
    expr: Header.type_raw
    cases:
      "0x4E54": NTRecord
    default: GenericRecord

types:
  Header:
    fields:
      - { name: type_raw, type: u16, endian: little }
      - { name: entity_id, type: u16, endian: little }

  GenericRecord:
    fields:
      - { name: header, type: Header }
      - { name: payload_len, type: u8 }
      - { name: payload, type: bytes, length_field: payload_len }

  NTRecord:
    fields:
      - { name: header, type: Header }
      - { name: data, type: bytes, length: 10 }
"""

reader = PagedReader("data/AA.FTM")
grammar = parse_yaml_grammar(YAML)
parser = RecordParser(grammar)

# Test first few records
for i in range(10):
    offset = 0

    # Calculate offset by parsing sequentially
    current_offset = 0
    for j in range(i + 1):
        rec = parser.parse_record(reader, current_offset)
        if j == i:
            # This is the record we want to examine
            print(f"\nRecord {i} at offset {rec.offset:#08x}:")
            print(f"  Type: {rec.type_name}")
            print(f"  Size: {rec.size}")

            if "header" in rec.fields:
                header = rec.fields["header"].value
                if isinstance(header, dict):
                    type_raw = header.get("type_raw")
                    entity_id = header.get("entity_id")
                    print(f"  Header: type_raw={type_raw:#06x}, entity_id={entity_id}")

                    # Check if this should be NT
                    if type_raw == 0x4E54:
                        print(f"  ⚠️  This is an NT record (0x4E54) but was parsed as {rec.type_name}!")

            if rec.error:
                print(f"  Error: {rec.error}")
                break

        current_offset += rec.size
        if rec.error:
            break

print("\n" + "="*60)

# Now find the first NT record in the file
print("\nSearching for first NT record (0x4E 0x54)...")
data = reader.read(0, reader.size)

# Search for NT pattern
offset = 0
count = 0
while offset < len(data) - 4:
    if data[offset] == 0x4E and data[offset+1] == 0x54:
        entity_id = int.from_bytes(data[offset+2:offset+4], 'little')
        print(f"  Found NT at offset {offset:#08x}, entity_id={entity_id}")

        # Try parsing at this offset
        rec = parser.parse_record(reader, offset)
        print(f"    Parsed as: {rec.type_name}")
        print(f"    Size: {rec.size}")
        if rec.error:
            print(f"    Error: {rec.error}")

        count += 1
        if count >= 3:
            break
        offset += rec.size if not rec.error else 1
    else:
        offset += 1

print(f"\nTotal NT signatures found: {count}")
