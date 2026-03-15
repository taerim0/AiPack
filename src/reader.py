def read_file(aip, target):

    with open(aip, "rb") as f:

        magic = f.read(4)
        version = struct.unpack("H", f.read(2))[0]
        count = struct.unpack("Q", f.read(8))[0]

        index_offset = struct.unpack("Q", f.read(8))[0]

        f.seek(index_offset)

        for _ in range(count):

            l = struct.unpack("H", f.read(2))[0]
            path = f.read(l).decode()

            t = struct.unpack("B", f.read(1))[0]
            off = struct.unpack("Q", f.read(8))[0]
            size = struct.unpack("Q", f.read(8))[0]

            if path == target:

                f.seek(off)
                return f.read(size)