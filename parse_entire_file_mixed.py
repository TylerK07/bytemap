#!/usr/bin/env python3
"""Parse entire file as single chunk stream, with special NT record handling."""

from hexmap.core.io import PagedReader

reader = PagedReader("data/AA.FTM")
data = reader.read(0, reader.size)

print("="*70)
print("PARSING ENTIRE FILE AS UNIFIED CHUNK STREAM")
print("="*70)

# Parse with: type(3) + unknown(1) + length(1) + payload
offset = 0
record_num = 0
records = []
nt_records = []

while offset < len(data):
    if offset + 5 > len(data):
        print(f"\n⚠️  Reached near EOF at {offset:#06x} with {len(data) - offset} bytes remaining")
        break

    type_bytes = data[offset:offset+3]
    unknown_byte = data[offset+3]
    length_byte = data[offset+4]

    payload_start = offset + 5
    payload_end = payload_start + length_byte

    if payload_end > len(data):
        print(f"\n⚠️  Record {record_num} at {offset:#06x} would extend beyond EOF")
        print(f"    Type: {type_bytes.hex()}, Unknown: {unknown_byte:02x}, Length: {length_byte}")
        break

    payload = data[payload_start:payload_end]

    # Check if this is an NT record
    is_nt = type_bytes[0:2] == bytes([0x4E, 0x54])

    rec = {
        'num': record_num,
        'offset': offset,
        'type': type_bytes.hex(),
        'unknown': unknown_byte,
        'length': length_byte,
        'is_nt': is_nt,
    }

    if is_nt:
        # Try to parse the note structure
        if length_byte >= 20:  # Must have at least 4 + 10 + 1C + something
            four_bytes = payload[0:4]
            ten_bytes = payload[4:14]

            # Look for 1C in the payload
            marker_pos = payload.find(b'\x1C')
            if marker_pos != -1 and marker_pos >= 14:
                # Find 0D terminator
                term_pos = payload.find(b'\x0D', marker_pos)
                if term_pos != -1:
                    # Extract string (skip 1C and following 00)
                    string_start = marker_pos + 2
                    string_bytes = payload[string_start:term_pos]

                    try:
                        note_text = string_bytes.decode('ascii', errors='replace').strip()
                        rec['note'] = note_text
                        rec['four_bytes'] = four_bytes.hex(' ')
                    except:
                        pass

        nt_records.append(rec)

    records.append(rec)
    offset = payload_end
    record_num += 1

print(f"\n✅ Successfully parsed {len(records)} records")
print(f"   Final offset: {offset:#06x} ({offset})")
print(f"   File size: {len(data):#06x} ({len(data)})")
print(f"   Unparsed: {len(data) - offset} bytes")
print(f"\n   NT-type records: {len(nt_records)} ({len(nt_records)/len(records)*100:.2f}%)")

# Show transition from regular to mixed records
print(f"\n" + "="*70)
print("RECORDS AROUND TRANSITION TO NT RECORDS")
print("="*70)

if nt_records:
    first_nt_num = nt_records[0]['num']
    print(f"\nFirst NT record is #{first_nt_num}")

    # Show records around it
    start = max(0, first_nt_num - 5)
    end = min(len(records), first_nt_num + 10)

    for i in range(start, end):
        rec = records[i]
        marker = " ← FIRST NT" if i == first_nt_num else ""
        nt_flag = "[NT]" if rec['is_nt'] else "    "

        # Try to decode payload as ASCII for context
        payload = data[rec['offset']+5:rec['offset']+5+rec['length']]
        preview = ""
        if rec['is_nt'] and 'note' in rec:
            preview = f"  \"{rec['note'][:40]}\""
        elif rec['length'] > 0 and rec['length'] < 50:
            try:
                decoded = payload.decode('ascii', errors='replace')
                if all(c.isprintable() or c in '\r\n' for c in decoded):
                    preview = f"  '{decoded[:30]}'"
            except:
                pass

        print(f"{rec['num']:4d} {nt_flag}: {rec['offset']:06x} type={rec['type']} " +
              f"unk={rec['unknown']:02x} len={rec['length']:3d}{preview}{marker}")

# Show distribution of records before/after first NT
print(f"\n" + "="*70)
print("RECORD DISTRIBUTION")
print("="*70)

if nt_records:
    first_nt_num = nt_records[0]['num']
    before_nt = records[:first_nt_num]
    after_nt = records[first_nt_num:]

    nt_in_after = [r for r in after_nt if r['is_nt']]
    regular_in_after = [r for r in after_nt if not r['is_nt']]

    print(f"\nBefore first NT record (records 0-{first_nt_num-1}):")
    print(f"  Total: {len(before_nt)}")
    print(f"  NT: 0 (0%)")

    print(f"\nAfter first NT record (records {first_nt_num}-{len(records)-1}):")
    print(f"  Total: {len(after_nt)}")
    print(f"  NT: {len(nt_in_after)} ({len(nt_in_after)/len(after_nt)*100:.1f}%)")
    print(f"  Regular: {len(regular_in_after)} ({len(regular_in_after)/len(after_nt)*100:.1f}%)")

# Show some examples of regular records mixed with NT
print(f"\n" + "="*70)
print("EXAMPLES: REGULAR RECORDS BETWEEN NT RECORDS")
print("="*70)

if len(nt_records) >= 2:
    # Find regular records between first two NT records
    first_nt = nt_records[0]['num']
    second_nt = nt_records[1]['num']

    between = records[first_nt+1:second_nt]
    print(f"\nBetween NT record #{first_nt} and #{second_nt}:")

    for rec in between[:5]:
        payload = data[rec['offset']+5:rec['offset']+5+rec['length']]
        print(f"  {rec['num']:4d}: {rec['offset']:06x} type={rec['type']} " +
              f"len={rec['length']:3d} payload={payload.hex(' ')[:30]}")

# Sample some NT records with their notes
print(f"\n" + "="*70)
print("SAMPLE NT RECORDS WITH NOTES")
print("="*70)

for i, rec in enumerate(nt_records[:10]):
    if 'note' in rec:
        print(f"\n{i+1}. Record #{rec['num']} at {rec['offset']:#06x}")
        print(f"   Type: {rec['type']}, Length: {rec['length']}")
        print(f"   Four bytes: {rec.get('four_bytes', 'N/A')}")
        print(f"   Note: \"{rec['note']}\"")
