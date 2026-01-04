#!/usr/bin/env python3
"""Investigate the pattern of which byte contains the length."""

from hexmap.core.io import PagedReader

reader = PagedReader("data/AA.FTM")
data = reader.read(0, reader.size)

print("="*70)
print("INVESTIGATING LENGTH BYTE PATTERN")
print("="*70)

# Let's look at the first few records and try BOTH interpretations
print("\nFirst 50 bytes of file:")
print(data[:50].hex(' '))

print("\n" + "="*70)
print("COMPARING TWO INTERPRETATIONS")
print("="*70)

# Try parsing first 30 records with BOTH methods
offset = 0
record_num = 0

print("\nFirst 30 records - comparing both interpretations:")
print()

while offset < len(data) and record_num < 30:
    if offset + 5 > len(data):
        break

    type_bytes = data[offset:offset+3]
    byte3 = data[offset+3]
    byte4 = data[offset+4]

    print(f"Record {record_num} at {offset:#06x}:")
    print(f"  Type: {type_bytes.hex()}")
    print(f"  Byte 3: {byte3:3d} (0x{byte3:02x})")
    print(f"  Byte 4: {byte4:3d} (0x{byte4:02x})")

    # Interpretation A: byte3=length, byte4=unknown
    len_a = byte3
    payload_end_a = offset + 5 + len_a

    # Interpretation B: byte3=unknown, byte4=length
    len_b = byte4
    payload_end_b = offset + 5 + len_b

    print(f"  If length in byte 3: len={len_a:3d}, payload ends at {payload_end_a:#06x}")
    print(f"  If length in byte 4: len={len_b:3d}, payload ends at {payload_end_b:#06x}")

    # Check which interpretation leads to a valid next record
    # A valid record would have recognizable patterns
    if payload_end_a + 5 <= len(data):
        next_type_a = data[payload_end_a:payload_end_a+3]
        next_b3_a = data[payload_end_a+3]
        next_b4_a = data[payload_end_a+4]
        print(f"  Next (if A): type={next_type_a.hex()}, byte3={next_b3_a:02x}, byte4={next_b4_a:02x}")

    if payload_end_b + 5 <= len(data):
        next_type_b = data[payload_end_b:payload_end_b+3]
        next_b3_b = data[payload_end_b+3]
        next_b4_b = data[payload_end_b+4]
        print(f"  Next (if B): type={next_type_b.hex()}, byte3={next_b3_b:02x}, byte4={next_b4_b:02x}")

    # Let's see if there's a pattern: maybe if byte3==0x00, then use byte4?
    if byte3 == 0x00:
        print(f"  → Byte 3 is 0x00, probably use byte 4 for length")
        offset = payload_end_b
    elif byte4 == 0x00:
        print(f"  → Byte 4 is 0x00, probably use byte 3 for length")
        offset = payload_end_a
    else:
        # Try to determine which makes more sense
        # Use the one that gives a smaller length (more conservative)
        if len_a < len_b:
            print(f"  → Using byte 3 (smaller length)")
            offset = payload_end_a
        else:
            print(f"  → Using byte 4 (smaller length)")
            offset = payload_end_b

    print()
    record_num += 1

print("\n" + "="*70)
print("PATTERN HYPOTHESIS")
print("="*70)

# Hypothesis: If byte 3 is 0x00, the length is in byte 4
# Otherwise, the length is in byte 3

print("\nHypothesis: If byte[3] == 0x00, then length is in byte[4]")
print("           Otherwise, length is in byte[3]")

# Test this hypothesis by parsing the whole file
offset = 0
records = []
errors = 0

while offset < len(data) and len(records) < 100:
    if offset + 5 > len(data):
        break

    type_bytes = data[offset:offset+3]
    byte3 = data[offset+3]
    byte4 = data[offset+4]

    # Apply hypothesis
    if byte3 == 0x00:
        length = byte4
        length_byte = 4
    else:
        length = byte3
        length_byte = 3

    payload_offset = offset + 5
    payload_end = payload_offset + length

    if payload_end > len(data):
        errors += 1
        break

    records.append({
        'offset': offset,
        'type': type_bytes.hex(),
        'byte3': byte3,
        'byte4': byte4,
        'length': length,
        'length_byte': length_byte,
    })

    offset = payload_end

print(f"\nParsed {len(records)} records with {errors} errors")

if len(records) > 0:
    print(f"\nFirst 20 records:")
    for i, rec in enumerate(records[:20]):
        lb = f"byte{rec['length_byte']}"
        print(f"  {i:3d}: {rec['offset']:#06x} type={rec['type']} len={rec['length']:3d} ({lb}) b3={rec['byte3']:02x} b4={rec['byte4']:02x}")

    # Show distribution of length byte choice
    byte3_count = sum(1 for r in records if r['length_byte'] == 3)
    byte4_count = sum(1 for r in records if r['length_byte'] == 4)
    print(f"\nLength byte distribution:")
    print(f"  Byte 3: {byte3_count}× ({byte3_count/len(records)*100:.1f}%)")
    print(f"  Byte 4: {byte4_count}× ({byte4_count/len(records)*100:.1f}%)")
