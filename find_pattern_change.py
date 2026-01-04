#!/usr/bin/env python3
"""Find where the length byte pattern changes."""

from hexmap.core.io import PagedReader

reader = PagedReader("data/AA.FTM")
data = reader.read(0, reader.size)

print("="*70)
print("FINDING WHERE PATTERN CHANGES")
print("="*70)

# Parse with the hypothesis: if byte3==0x00, use byte4, else use byte3
offset = 0
records = []

while offset < len(data):
    if offset + 5 > len(data):
        break

    type_bytes = data[offset:offset+3]
    byte3 = data[offset+3]
    byte4 = data[offset+4]

    # Apply hypothesis
    if byte3 == 0x00:
        length = byte4
        length_source = "byte4"
    else:
        length = byte3
        length_source = "byte3"

    payload_offset = offset + 5
    payload_end = payload_offset + length

    if payload_end > len(data):
        print(f"\n⚠️  Record at {offset:#08x} would extend beyond EOF")
        break

    records.append({
        'offset': offset,
        'type': type_bytes.hex(),
        'byte3': byte3,
        'byte4': byte4,
        'length': length,
        'source': length_source,
    })

    offset = payload_end

print(f"\nParsed {len(records)} records")

# Find where the pattern changes
byte3_records = [r for r in records if r['source'] == 'byte3']
byte4_records = [r for r in records if r['source'] == 'byte4']

print(f"\nLength from byte 3: {len(byte3_records)}× ({len(byte3_records)/len(records)*100:.1f}%)")
print(f"Length from byte 4: {len(byte4_records)}× ({len(byte4_records)/len(records)*100:.1f}%)")

if byte3_records:
    print(f"\nFirst record using byte 3 for length:")
    first = byte3_records[0]
    print(f"  Offset: {first['offset']:#08x}")
    print(f"  Type: {first['type']}")
    print(f"  Byte 3: {first['byte3']:3d} (0x{first['byte3']:02x}) ← length")
    print(f"  Byte 4: {first['byte4']:3d} (0x{first['byte4']:02x})")
    print(f"  Length: {first['length']}")

    # Show context around this transition
    first_idx = records.index(first)
    print(f"\n  Records around the transition (record #{first_idx}):")
    for i in range(max(0, first_idx-3), min(len(records), first_idx+5)):
        rec = records[i]
        marker = " ← FIRST byte3" if i == first_idx else ""
        print(f"    {i:4d}: {rec['offset']:#08x} type={rec['type']} b3={rec['byte3']:02x} b4={rec['byte4']:02x} len={rec['length']:3d} ({rec['source']}){marker}")

# Look for 000000 type records with both patterns
type_000000 = [r for r in records if r['type'] == '000000']
print(f"\n" + "="*70)
print(f"TYPE 000000 ANALYSIS")
print("="*70)
print(f"\nFound {len(type_000000)} records with type 000000")

if type_000000:
    byte3_000000 = [r for r in type_000000 if r['source'] == 'byte3']
    byte4_000000 = [r for r in type_000000 if r['source'] == 'byte4']

    print(f"  Using byte 3: {len(byte3_000000)}")
    print(f"  Using byte 4: {len(byte4_000000)}")

    if byte3_000000:
        print(f"\n  First 000000 using byte 3:")
        for rec in byte3_000000[:5]:
            print(f"    {rec['offset']:#08x}: b3={rec['byte3']:02x} b4={rec['byte4']:02x} len={rec['length']}")

    if byte4_000000:
        print(f"\n  First 000000 using byte 4:")
        for rec in byte4_000000[:5]:
            print(f"    {rec['offset']:#08x}: b3={rec['byte3']:02x} b4={rec['byte4']:02x} len={rec['length']}")

# Actually, maybe the "type" field isn't 3 bytes when byte3 != 0x00?
# What if the format is variable?
print(f"\n" + "="*70)
print("ALTERNATIVE HYPOTHESIS")
print("="*70)
print("\nWhat if when byte3 != 0x00, the structure changes?")
print("Maybe it's a different record format entirely?")

if byte3_records:
    print("\nExamining records where byte3 != 0x00:")
    for rec in byte3_records[:10]:
        idx = records.index(rec)
        offset = rec['offset']

        # Show raw bytes
        raw = data[offset:offset+20]
        print(f"\n  {offset:#08x}: {raw.hex(' ')}")
        print(f"    Type: {rec['type']}")
        print(f"    Byte 3: 0x{rec['byte3']:02x} (NOT 0x00!) ← Used as length")
        print(f"    Byte 4: 0x{rec['byte4']:02x}")
        print(f"    Length: {rec['length']}")

        # What's in the payload?
        payload = data[offset+5:offset+5+rec['length']]
        if len(payload) > 0:
            print(f"    Payload: {payload.hex(' ')[:50]}")
