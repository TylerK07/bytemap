#!/usr/bin/env python3
"""Test if length field changes from 1 byte to 2 bytes in second section."""

from hexmap.core.io import PagedReader

reader = PagedReader("data/AA.FTM")
data = reader.read(0, reader.size)

print("="*70)
print("TESTING: Does length field change to 2 bytes?")
print("="*70)

# Parse first section normally (1-byte length)
offset = 0
record_num = 0
records = []

print("\nParsing with 1-byte length until we hit problems...")

while offset < len(data) and record_num < 8950:
    if offset + 5 > len(data):
        break

    type_bytes = data[offset:offset+3]
    unknown_byte = data[offset+3]
    length_byte = data[offset+4]

    payload_end = offset + 5 + length_byte

    if payload_end > len(data):
        break

    # Check if type looks like ASCII (sign of misalignment)
    type_is_ascii = all(32 <= b < 127 for b in type_bytes)
    has_letters = any(65 <= b <= 90 or 97 <= b <= 122 for b in type_bytes)

    records.append({
        'num': record_num,
        'offset': offset,
        'type': type_bytes.hex(),
        'is_ascii': type_is_ascii and has_letters,
        'length': length_byte,
    })

    offset = payload_end
    record_num += 1

first_ascii = next((r for r in records if r['is_ascii']), None)
if first_ascii:
    print(f"\n⚠️  First ASCII-looking type at record {first_ascii['num']}, offset {first_ascii['offset']:#06x}")
    print(f"    Type: {first_ascii['type']}")

    # Show records around it
    idx = first_ascii['num']
    print(f"\n    Records around the problem:")
    for i in range(max(0, idx-3), min(len(records), idx+3)):
        rec = records[i]
        marker = " ← ASCII type" if i == idx else ""
        print(f"      {rec['num']:4d}: {rec['offset']:06x} type={rec['type']} len={rec['length']:3d}{marker}")

    # Now try parsing from a few records back with 2-byte length
    print(f"\n" + "="*70)
    print(f"RETRYING: Parse from record {idx-5} with 2-BYTE length")
    print("="*70)

    # Start from 5 records before the problem
    start_record = records[max(0, idx-5)]
    offset = start_record['offset']
    record_num = start_record['num']

    print(f"\nStarting at record {record_num}, offset {offset:#06x}")
    print(f"Parsing with: type(3) + length(2, big-endian) + payload\n")

    for i in range(20):  # Parse 20 records
        if offset + 5 > len(data):
            break

        type_bytes = data[offset:offset+3]
        length_word = (data[offset+3] << 8) | data[offset+4]  # Big-endian u16

        payload_start = offset + 5
        payload_end = payload_start + length_word

        if payload_end > len(data):
            print(f"      {record_num:4d}: {offset:06x} ⚠️  Would extend beyond EOF (len={length_word})")
            break

        payload = data[payload_start:payload_end]

        # Check if this is NT record
        is_nt = type_bytes[0:2] == bytes([0x4E, 0x54])
        nt_marker = "[NT]" if is_nt else "    "

        # Try to decode payload
        preview = ""
        if is_nt and length_word >= 20:
            # Look for 1C separator
            marker_pos = payload.find(b'\x1C')
            if marker_pos != -1:
                term_pos = payload.find(b'\x0D', marker_pos)
                if term_pos != -1:
                    string_bytes = payload[marker_pos+2:term_pos]
                    try:
                        note = string_bytes.decode('ascii', errors='replace').strip()
                        preview = f"  \"{note[:40]}\""
                    except:
                        pass

        type_ascii = ''.join(chr(b) if 32 <= b < 127 else '.' for b in type_bytes)
        print(f"      {record_num:4d} {nt_marker}: {offset:06x} type={type_bytes.hex()} ('{type_ascii}') " +
              f"len={length_word:4d}{preview}")

        offset = payload_end
        record_num += 1

# Try parsing from the beginning with an adaptive approach
print(f"\n" + "="*70)
print(f"ADAPTIVE PARSING: Switch to 2-byte length when we see NT")
print("="*70)

offset = 0
record_num = 0
two_byte_mode = False
records_parsed = []

while offset < len(data):
    if offset + 5 > len(data):
        print(f"\nReached near EOF with {len(data) - offset} bytes remaining")
        break

    type_bytes = data[offset:offset+3]

    # Check if this might be start of NT section
    # Heuristic: if we see 4E 54 or several ASCII-looking types, switch to 2-byte length
    is_nt = type_bytes[0:2] == bytes([0x4E, 0x54])

    if is_nt and not two_byte_mode:
        print(f"\n⚠️  Detected NT record at {offset:#06x}, switching to 2-byte length mode")
        two_byte_mode = True

    if two_byte_mode:
        # 2-byte length
        length = (data[offset+3] << 8) | data[offset+4]
        header_size = 5
    else:
        # 1-byte length with unknown byte
        length = data[offset+4]
        header_size = 5

    payload_end = offset + header_size + length

    if payload_end > len(data):
        print(f"\n⚠️  Record {record_num} at {offset:#06x} would extend beyond EOF")
        break

    records_parsed.append({
        'offset': offset,
        'type': type_bytes.hex(),
        'is_nt': is_nt,
        'two_byte': two_byte_mode,
    })

    offset = payload_end
    record_num += 1

    if record_num >= 9100:  # Stop after getting past the transition
        break

print(f"\n✅ Parsed {len(records_parsed)} records")
print(f"   Unparsed: {len(data) - offset} bytes")

# Show statistics
one_byte_recs = [r for r in records_parsed if not r['two_byte']]
two_byte_recs = [r for r in records_parsed if r['two_byte']]
nt_recs = [r for r in records_parsed if r['is_nt']]

print(f"\n   1-byte length mode: {len(one_byte_recs)} records")
print(f"   2-byte length mode: {len(two_byte_recs)} records")
print(f"   NT-type records: {len(nt_recs)}")
