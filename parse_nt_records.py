#!/usr/bin/env python3
"""Parse NT-type records (4E 54 XX pattern)."""

from hexmap.core.io import PagedReader

reader = PagedReader("data/AA.FTM")
data = reader.read(0, reader.size)

print("="*70)
print("PARSING NT-TYPE RECORDS (4E 54 XX pattern)")
print("="*70)

# Start from where the first format ends
start_offset = 0x13B10
search_region = data[start_offset:]

print(f"\nSearching for 4E 54 XX pattern from {start_offset:#06x}...")

# Find all occurrences of 4E 54
nt_records = []
offset = 0
while offset < len(search_region) - 30:
    if search_region[offset:offset+2] == bytes([0x4E, 0x54]):
        # Found NT pattern
        abs_offset = start_offset + offset

        # Extract according to user's pattern:
        # Type: 4E 54 XX (3 bytes)
        type_bytes = search_region[offset:offset+3]

        # 4 bytes after type
        four_bytes = search_region[offset+3:offset+7]

        # Check for 10 bytes of 00
        ten_bytes = search_region[offset+7:offset+17]

        # Look for 1C 00 pattern (or 00 1C 00)
        # The user said "00 1C 00" but let me check both
        marker_offset = offset + 17

        # Check for the 1C marker in the next few bytes
        marker_found = False
        marker_pos = None
        for i in range(marker_offset, marker_offset + 5):
            if i + 1 < len(search_region) and search_region[i] == 0x1C and search_region[i+1] == 0x00:
                marker_found = True
                marker_pos = i
                break

        if marker_found:
            # Find the string between 1C 00 and 0D 00
            string_start = marker_pos + 2

            # Search for 0D 00 terminator
            string_end = None
            for i in range(string_start, min(string_start + 200, len(search_region))):
                if i + 1 < len(search_region) and search_region[i] == 0x0D and search_region[i+1] == 0x00:
                    string_end = i
                    break

            if string_end:
                string_bytes = search_region[string_start:string_end]

                # Try to decode as ASCII
                try:
                    decoded = string_bytes.decode('ascii', errors='replace')
                    decoded = decoded.strip()
                except:
                    decoded = ""

                # Check if ten_bytes are actually all zeros
                all_zeros = all(b == 0x00 for b in ten_bytes)

                record = {
                    'offset': abs_offset,
                    'type': type_bytes.hex(),
                    'type_byte3': type_bytes[2],
                    'four_bytes': four_bytes.hex(' '),
                    'ten_zeros': all_zeros,
                    'string': decoded,
                    'record_length': string_end + 2 - offset,
                }

                nt_records.append(record)

                # Skip past this record
                offset = string_end + 2
                continue

    offset += 1

print(f"\nFound {len(nt_records)} NT-type records")

# Show all records
print(f"\n" + "="*70)
print("NT RECORDS")
print("="*70)

for i, rec in enumerate(nt_records[:30]):  # Show first 30
    zeros_check = "✓" if rec['ten_zeros'] else "✗"
    print(f"\n{i+1}. Offset {rec['offset']:#06x}, Length {rec['record_length']} bytes")
    print(f"   Type: {rec['type']} (byte3={rec['type_byte3']:02x}={rec['type_byte3']})")
    print(f"   4-byte field: {rec['four_bytes']}")
    print(f"   10 zeros: {zeros_check}")
    print(f"   String: \"{rec['string']}\"")

# Analyze the structure
print(f"\n" + "="*70)
print("PATTERN ANALYSIS")
print("="*70)

if nt_records:
    # Check third byte distribution
    type_byte3_values = {}
    for rec in nt_records:
        b3 = rec['type_byte3']
        type_byte3_values[b3] = type_byte3_values.get(b3, 0) + 1

    print(f"\nThird byte of type field distribution:")
    for b3, count in sorted(type_byte3_values.items()):
        char = chr(b3) if 32 <= b3 < 127 else '.'
        print(f"  0x{b3:02x} ('{char}'): {count}×")

    # Check four_bytes patterns
    print(f"\nFour-byte field patterns (first 10):")
    four_byte_patterns = {}
    for rec in nt_records:
        fb = rec['four_bytes']
        if fb not in four_byte_patterns:
            four_byte_patterns[fb] = []
        four_byte_patterns[fb].append(rec['offset'])

    for i, (pattern, offsets) in enumerate(list(four_byte_patterns.items())[:10]):
        print(f"  {pattern}: {len(offsets)}× (e.g., {offsets[0]:#06x})")

    # Check if all have 10 zeros
    all_zeros_count = sum(1 for r in nt_records if r['ten_zeros'])
    print(f"\nRecords with 10 zeros: {all_zeros_count}/{len(nt_records)} ({all_zeros_count/len(nt_records)*100:.1f}%)")

    # Show non-zero examples
    non_zero = [r for r in nt_records if not r['ten_zeros']]
    if non_zero:
        print(f"\nRecords WITHOUT 10 zeros (showing first 3):")
        for rec in non_zero[:3]:
            print(f"  {rec['offset']:#06x}: type={rec['type']}, 4bytes={rec['four_bytes']}")

# Now check: can we parse the ENTIRE second format?
print(f"\n" + "="*70)
print("ATTEMPTING TO PARSE ENTIRE SECOND FORMAT")
print("="*70)

# Parse from 0x13B16 (after first format) to end
second_format_start = 0x13B16
offset = second_format_start
parsed_records = []

while offset < len(data):
    remaining = len(data) - offset
    if remaining < 10:
        print(f"\nReached end with {remaining} bytes unparsed")
        break

    # Check for NT pattern
    if data[offset:offset+2] == bytes([0x4E, 0x54]):
        # Try to parse as NT record using the pattern
        type_bytes = data[offset:offset+3]

        # Look for 1C in next 20 bytes
        marker_pos = None
        for i in range(offset + 3, min(offset + 25, len(data))):
            if data[i] == 0x1C:
                marker_pos = i
                break

        if marker_pos:
            # Find 0D 00 terminator
            string_start = marker_pos + 2
            string_end = None
            for i in range(string_start, min(string_start + 200, len(data))):
                if i + 1 < len(data) and data[i] == 0x0D and data[i+1] == 0x00:
                    string_end = i
                    break

            if string_end:
                record_len = string_end + 2 - offset
                parsed_records.append({
                    'offset': offset,
                    'type': 'NT',
                    'length': record_len,
                })
                offset = string_end + 2
                continue

    # Check for other patterns
    # Look for 0D 00 42 00 which seems to be another record type
    if offset + 3 < len(data) and data[offset:offset+2] == bytes([0x0D, 0x00]):
        # This might be a different record type
        parsed_records.append({
            'offset': offset,
            'type': '0D00',
            'length': 2,
        })
        offset += 2
        continue

    # Check for 42 00 pattern (often precedes NT records)
    if offset + 1 < len(data) and data[offset:offset+2] == bytes([0x42, 0x00]):
        # Parse until next NT or end
        next_nt = data.find(b'\x4E\x54', offset + 2, min(offset + 50, len(data)))
        if next_nt != -1:
            record_len = next_nt - offset
            parsed_records.append({
                'offset': offset,
                'type': '42XX',
                'length': record_len,
            })
            offset = next_nt
            continue

    # Unknown byte, skip it
    offset += 1

print(f"\nParsed {len(parsed_records)} records in second format")
print(f"Coverage: {offset - second_format_start}/{len(data) - second_format_start} bytes")

# Show record type distribution
type_counts = {}
for rec in parsed_records:
    t = rec['type']
    type_counts[t] = type_counts.get(t, 0) + 1

print(f"\nRecord type distribution:")
for t, count in sorted(type_counts.items()):
    print(f"  {t}: {count}×")
