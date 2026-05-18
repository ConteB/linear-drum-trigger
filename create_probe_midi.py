import struct

def write_vlk(value):
    """Write variable length quantity."""
    if value == 0:
        return b'\x00'
    out = b''
    while value > 0:
        byte = value & 0x7F
        value >>= 7
        if out:
            byte |= 0x80
        out = struct.pack('B', byte) + out
    return out

def create_midi_probe(filename, start_note=24, end_note=84):
    # MIDI header: Type 0, 1 track, 480 ticks per quarter note
    header = b'MThd' + struct.pack('>IHHH', 6, 0, 1, 480)
    
    # MIDI track
    track_data = b''
    
    for note in range(start_note, end_note + 1):
        # Delta time 0 for Note On
        track_data += b'\x00' 
        # Note on: Channel 10 (0x99), Note, Velocity 100
        track_data += struct.pack('BBB', 0x99, note, 100)
        
        # Delta time 480 (1 quarter note) for Note Off
        track_data += b'\x83\x60' # 480 in variable length is 0x83 0x60? No.
        # 480 = 0x01 E0. 0x03 * 128 + 0x60 = 384 + 96 = 480. 
        # 480 >> 7 = 3. 480 & 0x7F = 0x60. So 0x83 0x60.
        
        # Note off (or note on with velocity 0)
        track_data += struct.pack('BBB', 0x99, note, 0)
    
    # End of track: Delta time 0, Meta event 0xFF 0x2F 0x00
    track_data += b'\x00' + b'\xFF\x2F\x00'
    
    track = b'MTrk' + struct.pack('>I', len(track_data)) + track_data
    
    with open(filename, 'wb') as f:
        f.write(header + track)

if __name__ == "__main__":
    create_midi_probe("data/temp/probe.midi")
    print("Created data/temp/probe.midi")

if __name__ == "__main__":
    create_midi_probe("data/temp/probe.midi")
    print("Created data/temp/probe.midi")
