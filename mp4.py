import requests
import struct
import sys

ATOM_TYPES = [
    "ftyp", "mdat", "moov", "pnot", "udta", "uuid", "moof", "free", "skip",
    "jP2 ", "wide", "load", "ctab", "imap", "matt", "kmat", "clip", "crgn",
    "sync", "chap", "tmcd", "scpt", "ssrc", "PICT"
]
SUB_TYPES = [
    "avc1", "iso2", "isom", "mmp4", "mp41", "mp42", "mp71", "msnv", "ndas",
    "ndsc", "ndsh", "ndsm", "ndsp", "ndss", "ndxc", "ndxh", "ndxm", "ndxp",
    "ndxs"
]

class Info:
    """Info extracts MP4 headers from a video stream"""
    def __init__(self, url: str):
        self.url = url
        self.timeout = 5
        self.session = requests.session()
        self.offset = 0
        self.duration = 0

    def _set_headers(self, offset: int, seek: int):
        """The Range HTTP request header indicates the part of a document that
        the server should return.

        'Range: <unit>=<range-start>-<range-end>'
        """
        self.session.headers["Range"] = f"bytes={offset}-{offset + seek}"

    def _send_request(self):
        resp = self.session.get(url=self.url, stream=True, timeout=self.timeout)

        # If the server sends back ranges, it uses the 206 Partial Content for
        # the response so we assert here.
        assert resp.status_code == 206

        return resp.raw.read()

    def get_duration(self) -> float:
        
        while True:
            # Make request with 'Range' header to get an MP4 atom. Each atom has
            # an 8 byte header. For example, the first 'Range' header will
            # always be 'bytes=0-7'
            self._set_headers(self.offset, 7)

            data = self._send_request()

            # The 8 byte header has a 4-byte atom size (big-endian, high byte
            # first) and 4-byte atom type.
            # ">"" = big-endian
            # "I" = integer
            atom_size = int(struct.unpack(">I", data[:4])[0])
            atom_type = data[-4:].decode()

            assert atom_type in ATOM_TYPES

            # The movie (moov) atom contains a movie header atom (mvhd) that
            # defines the timescale and duration information. Other atoms may
            # exist within the parent moov atom but mvhd is required and always
            # first. Knowing this we can get the timescale and duration easily.
            # The layout of a mvhd atom (atom, bytes):
            # Atom size, 4
            # Type = 'mvhd', 4
            # Version, 1
            # Flags, 3
            # Creation time, 4
            # Modification time, 4
            # Time scale, 4
            # Duration, 4
            # etc ...
            if atom_type == "moov":
                self.offset += 8 + 20
                self._set_headers(self.offset, 7)
                data = self._send_request()
                time_scale = int(struct.unpack(">I", data[:4])[0])
                duration = int(struct.unpack(">I", data[-4:])[0])
                self.duration = duration/time_scale

                return self.duration


            # We add the atom size to self.seek to get the next atom.
            #
            # For example:
            # 1st atom (type ftyp) has size 36 and located at offset 0. The 2nd
            # atom will be located at offset 0 + 36 = 36. The 2nd atom (type
            # moov) has size 771556. The 3rd atom will be located at offset
            # 0 + 36 + 771556 = 771592.
            # Etc..
            self.offset += atom_size
