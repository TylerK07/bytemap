#!/usr/bin/env python3
"""Parse with understanding that NT records are delimited, not length-prefixed."""

from hexmap.core.io import PagedReader

reader = PagedReader("data/AA.FTM")
data = reader.read(0, reader.size)

print("="*70)
print("HYBRID PARSING: Length-prefixed + Delimited records")
print("="*70)

# Parse first section with fixed framing
offset = 0
record_num = 0
records = []

# Parse until we hit the first NT record
while offset < len(data):
    if offset + 5 > len(data):
        break

    type_bytes = data[offset:offset+3]

    # Check if this is an NT record (4E 54 XX)
    if type_bytes[0:2] == bytes([0x4E, 0x54]):
        print(f"\n🔄 Found NT record at {offset:#06x} (record #{record_num})")
        print("   Switching to delimited parsing for this record...")

        # Parse NT record by finding 0D 00 terminator
        terminator_pos = data.find(b'\x0D\x00', offset)

        if terminator_pos != -1:
            record_length = terminator_pos + 2 - offset
            payload = data[offset+3:terminator_pos]

            # Try to extract note text
            note_text = ""
            marker_pos = payload.find(b'\x1C')
            if marker_pos != -1:
                string_start = marker_pos + 2
                string_bytes = payload[string_start:]
                try:
                    note_text = string_bytes.decode('ascii', errors='replace').strip()
                except:
                    pass

            records.append({
                'num': record_num,
                'offset': offset,
                'type': type_bytes.hex(),
                'length': record_length,
                'is_nt': True,
                'note': note_text,
            })

            print(f"   NT record length: {record_length} bytes")
            print(f"   Note: \"{note_text[:50]}\"")

            # Skip past this NT record (including the 0D 00 terminator)
            offset = terminator_pos + 2
            record_num += 1
            continue
        else:
            print(f"   ⚠️  No terminator found, treating as regular record")

    # Regular record with fixed framing: type(3) + unknown(1) + length(1)
    unknown_byte = data[offset+3]
    length_byte = data[offset+4]

    payload_end = offset + 5 + length_byte

    if payload_end > len(data):
        print(f"\n⚠️  Record {record_num} at {offset:#06x} would extend beyond EOF")
        break

    records.append({
        'num': record_num,
        'offset': offset,
        'type': type_bytes.hex(),
        'length': 5 + length_byte,
        'is_nt': False,
    })

    offset = payload_end
    record_num += 1

    # Stop after we've seen enough records
    if record_num > 9100:
        break

print(f"\n✅ Successfully parsed {len(records)} records")
print(f"   Final offset: {offset:#06x}")
print(f"   Unparsed: {len(data) - offset} bytes")

# Statistics
nt_records = [r for r in records if r['is_nt']]
regular_records = [r for r in records if not r['is_nt']]

print(f"\n   Regular records: {len(regular_records)}")
print(f"   NT records: {len(nt_records)}")

if nt_records:
    first_nt = nt_records[0]['num']
    print(f"\n   First NT record: #{first_nt}")

    # Show distribution before/after
    before = [r for r in records if r['num'] < first_nt]
    after = [r for r in records if r['num'] >= first_nt]
    nt_in_after = [r for r in after if r['is_nt']]

    print(f"\n   Before first NT: {len(before)} records (all regular)")
    print(f"   After first NT: {len(after)} records")
    print(f"     - NT: {len(nt_in_after)} ({len(nt_in_after)/len(after)*100:.1f}%)")
    print(f"     - Regular: {len(after) - len(nt_in_after)} ({(len(after) - len(nt_in_after))/len(after)*100:.1f}%)")

# Show sample NT records
print(f"\n" + "="*70)
print("SAMPLE NT RECORDS")
print("="*70)

for i, rec in enumerate(nt_records[:10]):
    print(f"\n{i+1}. Record #{rec['num']} at {rec['offset']:#06x}")
    print(f"   Type: {rec['type']}, Total length: {rec['length']} bytes")
    if rec.get('note'):
        print(f"   Note: \"{rec['note']}\"")

# Show records around first NT
if nt_records:
    print(f"\n" + "="*70)
    print(f"RECORDS AROUND FIRST NT (record #{nt_records[0]['num']})")
    print("="*70)

    first_idx = nt_records[0]['num']
    start = max(0, first_idx - 5)
    end = min(len(records), first_idx + 10)

    for i in range(start, end):
        rec = records[i]
        marker = " ← FIRST NT" if i == first_idx else ""
        nt_flag = "[NT]" if rec['is_nt'] else "    "

        preview = ""
        if rec['is_nt'] and rec.get('note'):
            preview = f"  \"{rec['note'][:40]}\""

        print(f"{rec['num']:4d} {nt_flag}: {rec['offset']:06x} type={rec['type']} " +
              f"len={rec['length']:4d}{preview}{marker}")
