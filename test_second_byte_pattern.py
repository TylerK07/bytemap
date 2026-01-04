#!/usr/bin/env python3
"""Test the pattern where length is in SECOND byte of a 2-byte field."""

from hexmap.core.io import PagedReader

reader = PagedReader("data/AA.FTM")
data = reader.read(0, reader.size)

print("="*70)
print("TESTING: Length in SECOND byte of 2-byte length field")
print("="*70)

# Parse starting at the transition point
start_offset = 0x5797

print(f"\nStarting at offset {start_offset:#06x}")
print(f"Raw bytes: {data[start_offset:start_offset+30].hex(' ')}")

# Parse with: type(3) + length_field(2, use byte 2) + payload
offset = start_offset
records = []

for i in range(20):
    if offset + 5 > len(data):
        break

    type_bytes = data[offset:offset+3]
    length_byte1 = data[offset+3]
    length_byte2 = data[offset+4]

    # Use SECOND byte as length
    length = length_byte2

    payload_offset = offset + 5
    payload_end = payload_offset + length

    if payload_end > len(data):
        print(f"\n⚠️  Would extend beyond EOF")
        break

    payload = data[payload_offset:payload_end]

    records.append({
        'offset': offset,
        'type': type_bytes.hex(),
        'byte1': length_byte1,
        'byte2': length_byte2,
        'length': length,
        'payload': payload,
    })

    print(f"\nRecord {i} at {offset:#06x}:")
    print(f"  Type: {type_bytes.hex()}")
    print(f"  Length field: {length_byte1:02x} {length_byte2:02x} → use byte2={length_byte2} ({length} bytes)")
    print(f"  Payload: {payload.hex(' ')[:50]}")

    # Try to interpret payload as string
    try:
        decoded = payload.decode('ascii')
        if decoded.isprintable():
            print(f"  ASCII: '{decoded}'")
    except:
        pass

    offset = payload_end

# Now search for the "07 00 FF" type with "WINDSOR" payload
print(f"\n" + "="*70)
print("SEARCHING FOR '07 00 FF' + WINDSOR pattern")
print("="*70)

windsor = b"WINDSOR"
for i in range(len(data) - 20):
    if data[i:i+7] == windsor:
        print(f"\nFound 'WINDSOR' at {i:#06x}")

        # Look backwards for potential header
        for back in range(5, 10):
            header_start = i - back
            if header_start < 0:
                continue

            header = data[header_start:i]
            print(f"  -{back} bytes: {header.hex(' ')}")

            # Check if this could be: type(3) + length_field(2)
            if back == 5:
                type_bytes = header[:3]
                len_field = header[3:5]
                print(f"    Possible: type={type_bytes.hex()}, length_field={len_field.hex()}")

# Also search for the pattern where it says "07 00 ff 00 16"
print(f"\n" + "="*70)
print("SEARCHING FOR '07 00 ff' bytes")
print("="*70)

target = bytes([0x07, 0x00, 0xff])
for i in range(len(data) - 20):
    if data[i:i+3] == target:
        context = data[i:i+25]
        print(f"\nFound '07 00 ff' at {i:#06x}:")
        print(f"  Bytes: {context.hex(' ')}")

        # If this is a type field, next 2 bytes are length
        len_byte1 = data[i+3]
        len_byte2 = data[i+4]
        print(f"  Next 2 bytes: {len_byte1:02x} {len_byte2:02x}")

        # Try as payload
        payload_start = i + 5

        # Try byte 2 as length
        if len_byte2 > 0 and len_byte2 < 100:
            payload = data[payload_start:payload_start+len_byte2]
            print(f"  If length={len_byte2} (byte2): payload = {payload.hex(' ')[:40]}")
            try:
                decoded = payload.decode('ascii')
                if decoded.isprintable():
                    print(f"    ASCII: '{decoded}'")
            except:
                pass
