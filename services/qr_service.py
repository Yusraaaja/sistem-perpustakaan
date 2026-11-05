# -*- coding: utf-8 -*-
"""
Modul Generator QR Code Murni Python (Zero-Dependency) untuk Sistem Perpustakaan Digital.
Memenuhi DEC-011, LIB-QR-004, Task 3-08.

Fitur:
- Standar ISO/IEC 18004 (Model 2, Versi 1 s.d. 40, Level ECC: Low, Medium, Quartile, High).
- Mode encoding: Numeric, Alphanumeric (Crockford Base32), dan Byte (UTF-8).
- Output format: Scalable Vector Graphics (SVG) murni tanpa pustaka grafis eksternal.
- Payload ketat: hanya memuat identifier eksemplar (copy_id), tanpa data pribadi atau URL.
"""
import collections
from typing import Sequence, List, Tuple, Optional, Callable


class Ecc:
    """Tingkat koreksi kesalahan (Error Correction Level)."""
    LOW = 0       # ~7% pemulihan
    MEDIUM = 1    # ~15% pemulihan (standar label buku)
    QUARTILE = 2  # ~25% pemulihan
    HIGH = 3      # ~30% pemulihan


_FORMAT_BITS = (1, 0, 3, 2)

_ECC_CODEWORDS_PER_BLOCK = (
    # Low
    (-1,  7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    # Medium
    (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    # Quartile
    (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    # High
    (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 24, 24, 24, 28, 28, 26, 26, 26, 26, 30, 28, 28, 28, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
)

_NUM_ERROR_CORRECTION_BLOCKS = (
    # Low
    (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2,  2,  4,  4,  4,  4,  4,  6,  6,  6,  6,  7,  8,  8,  9,  9, 10, 12, 12, 12, 13, 14, 14, 14, 14, 15, 16, 17, 17, 18, 19, 19),
    # Medium
    (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5,  5,  6,  8,  8,  8, 10, 10, 11, 13, 14, 16, 16, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49, 51),
    # Quartile
    (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8,  8,  8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    # High
    (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8,  8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 78, 82),
)

ALPHANUMERIC_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"

_MASK_PATTERNS = (
    lambda x, y: (x + y) % 2,
    lambda x, y: y % 2,
    lambda x, y: x % 3,
    lambda x, y: (x + y) % 3,
    lambda x, y: (x // 3 + y // 2) % 2,
    lambda x, y: x * y % 2 + x * y % 3,
    lambda x, y: (x * y % 2 + x * y % 3) % 2,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2,
)

_PENALTY_N1 = 3
_PENALTY_N2 = 3
_PENALTY_N3 = 40
_PENALTY_N4 = 10


class _BitBuffer(list):
    """Penyimpan bit terurut untuk data codeword."""
    def append_bits(self, val: int, n: int) -> None:
        if n < 0 or (val >> n != 0):
            raise ValueError(f"Value out of range: val={val}, n={n}")
        for i in range(n - 1, -1, -1):
            self.append((val >> i) & 1)


def _get_bit(x: int, i: int) -> bool:
    return ((x >> i) & 1) != 0


def _get_num_raw_data_modules(ver: int) -> int:
    if not (1 <= ver <= 40):
        raise ValueError("Nomor versi QR Code harus antara 1 dan 40.")
    res = (16 * ver + 128) * ver + 64
    if ver >= 2:
        numalign = ver // 7 + 2
        res -= (25 * numalign - 10) * numalign - 55
    if ver >= 7:
        res -= 36
    return res


def _get_num_data_codewords(ver: int, ecl: int) -> int:
    return _get_num_raw_data_modules(ver) // 8 - _ECC_CODEWORDS_PER_BLOCK[ecl][ver] * _NUM_ERROR_CORRECTION_BLOCKS[ecl][ver]


def _reed_solomon_multiply(x: int, y: int) -> int:
    if (x >> 8 != 0) or (y >> 8 != 0):
        raise ValueError("Byte out of range")
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _reed_solomon_compute_divisor(degree: int) -> bytes:
    if not (1 <= degree <= 255):
        raise ValueError("Degree out of range")
    result = bytearray([0] * degree)
    result[-1] = 1
    root = 0x01
    for _ in range(degree):
        for j in range(degree):
            result[j] = _reed_solomon_multiply(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _reed_solomon_multiply(root, 0x02)
    return bytes(result)


def _reed_solomon_compute_remainder(data: bytes, divisor: bytes) -> bytes:
    result = bytearray([0] * len(divisor))
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _reed_solomon_multiply(coef, factor)
    return bytes(result)


def _get_alignment_pattern_positions(ver: int) -> List[int]:
    if ver == 1:
        return []
    numalign = ver // 7 + 2
    step = (ver * 8 + numalign * 3 + 5) // (numalign * 4 - 4) * 2
    result = []
    pos = ver * 4 + 10
    while len(result) < numalign - 1:
        result.append(pos)
        pos -= step
    result.append(6)
    return result[::-1]


class QrCode:
    """Objek representasi matriks QR Code biner Model 2."""
    def __init__(self, version: int, ecl: int, data_codewords: bytes, mask: int = -1):
        if not (1 <= version <= 40):
            raise ValueError("Nomor versi QR Code harus antara 1 dan 40.")
        if not (0 <= ecl <= 3):
            raise ValueError("Tingkat ECC tidak valid.")
        self.version = version
        self.ecl = ecl
        self.size = version * 4 + 17
        self.modules = [[False] * self.size for _ in range(self.size)]
        self.is_function = [[False] * self.size for _ in range(self.size)]

        self._draw_function_patterns()
        all_codewords = self._add_ecc_and_interleave(data_codewords)
        self._draw_codewords(all_codewords)

        if mask == -1:
            min_penalty = 1 << 32
            best_mask = 0
            for m in range(8):
                self._apply_mask(m)
                self._draw_format_bits(m)
                penalty = self._get_penalty_score()
                if penalty < min_penalty:
                    min_penalty = penalty
                    best_mask = m
                self._apply_mask(m)
            mask = best_mask

        self.mask = mask
        self._apply_mask(mask)
        self._draw_format_bits(mask)

    def _set_function_module(self, x: int, y: int, is_dark: bool) -> None:
        self.modules[y][x] = is_dark
        self.is_function[y][x] = True

    def _draw_function_patterns(self) -> None:
        # Pola Timing horizontal & vertikal
        for i in range(self.size):
            self._set_function_module(6, i, i % 2 == 0)
            self._set_function_module(i, 6, i % 2 == 0)

        # 3 Pola Finder (Pencari Sudut)
        self._draw_finder_pattern(3, 3)
        self._draw_finder_pattern(self.size - 4, 3)
        self._draw_finder_pattern(3, self.size - 4)

        # Pola Alignment (Penyeimbang, untuk versi >= 2)
        align_pos = _get_alignment_pattern_positions(self.version)
        num_align = len(align_pos)
        skips = ((0, 0), (0, num_align - 1), (num_align - 1, 0))
        for i in range(num_align):
            for j in range(num_align):
                if (i, j) not in skips:
                    self._draw_alignment_pattern(align_pos[i], align_pos[j])

        # Format bits dummy (ditimpa setelah evaluasi mask)
        self._draw_format_bits(0)
        self._draw_version()

    def _draw_finder_pattern(self, x: int, y: int) -> None:
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                xx, yy = x + dx, y + dy
                if 0 <= xx < self.size and 0 <= yy < self.size:
                    dist = max(abs(dx), abs(dy))
                    self._set_function_module(xx, yy, dist not in (2, 4))

    def _draw_alignment_pattern(self, x: int, y: int) -> None:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                dist = max(abs(dx), abs(dy))
                self._set_function_module(x + dx, y + dy, dist != 1)

    def _draw_format_bits(self, mask: int) -> None:
        data = (_FORMAT_BITS[self.ecl] << 3) | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = ((data << 10) | rem) ^ 0x5412

        # Salinan pertama (sekeliling sudut kiri atas)
        for i in range(0, 6):
            self._set_function_module(8, i, _get_bit(bits, i))
        self._set_function_module(8, 7, _get_bit(bits, 6))
        self._set_function_module(8, 8, _get_bit(bits, 7))
        self._set_function_module(7, 8, _get_bit(bits, 8))
        for i in range(9, 15):
            self._set_function_module(14 - i, 8, _get_bit(bits, i))

        # Salinan kedua (sudut kanan atas dan kiri bawah)
        for i in range(0, 8):
            self._set_function_module(self.size - 1 - i, 8, _get_bit(bits, i))
        for i in range(8, 15):
            self._set_function_module(8, self.size - 15 + i, _get_bit(bits, i))
        self._set_function_module(8, self.size - 8, True)  # Modul gelap permanen

    def _draw_version(self) -> None:
        if self.version < 7:
            return
        rem = self.version
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = (self.version << 12) | rem
        for i in range(18):
            bit = _get_bit(bits, i)
            a = self.size - 11 + i % 3
            b = i // 3
            self._set_function_module(a, b, bit)
            self._set_function_module(b, a, bit)

    def _add_ecc_and_interleave(self, data: bytes) -> bytes:
        numblocks = _NUM_ERROR_CORRECTION_BLOCKS[self.ecl][self.version]
        blockecclen = _ECC_CODEWORDS_PER_BLOCK[self.ecl][self.version]
        rawcodewords = _get_num_raw_data_modules(self.version) // 8
        numshortblocks = numblocks - rawcodewords % numblocks
        shortblocklen = rawcodewords // numblocks

        blocks: List[bytearray] = []
        rsdiv = _reed_solomon_compute_divisor(blockecclen)
        k = 0
        for i in range(numblocks):
            block_data_len = shortblocklen - blockecclen + (0 if i < numshortblocks else 1)
            dat = bytearray(data[k : k + block_data_len])
            k += len(dat)
            ecc = _reed_solomon_compute_remainder(dat, rsdiv)
            if i < numshortblocks:
                dat.append(0)
            blocks.append(dat + bytearray(ecc))
        assert k == len(data)

        result = bytearray()
        for i in range(len(blocks[0])):
            for j, blk in enumerate(blocks):
                if (i != shortblocklen - blockecclen) or (j >= numshortblocks):
                    result.append(blk[i])
        assert len(result) == rawcodewords
        return bytes(result)

    def _draw_codewords(self, data: bytes) -> None:
        i = 0
        right = self.size - 1
        while right > 0:
            if right == 6:
                right -= 1
            for vert in range(self.size):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = (self.size - 1 - vert) if upward else vert
                    if not self.is_function[y][x] and (i < len(data) * 8):
                        self.modules[y][x] = _get_bit(data[i >> 3], 7 - (i & 7))
                        i += 1
            right -= 2
        assert i == len(data) * 8

    def _apply_mask(self, mask: int) -> None:
        masker = _MASK_PATTERNS[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.is_function[y][x]:
                    self.modules[y][x] ^= (masker(x, y) == 0)

    def _get_penalty_score(self) -> int:
        result = 0
        size = self.size
        modules = self.modules

        # Rule 1 & Rule 3 (Horizontal)
        for y in range(size):
            runcolor = False
            runx = 0
            runhistory = collections.deque([0] * 7, 7)
            for x in range(size):
                if modules[y][x] == runcolor:
                    runx += 1
                    if runx == 5:
                        result += _PENALTY_N1
                    elif runx > 5:
                        result += 1
                else:
                    self._finder_penalty_add_history(runx, runhistory)
                    if not runcolor:
                        result += self._finder_penalty_count_patterns(runhistory) * _PENALTY_N3
                    runcolor = modules[y][x]
                    runx = 1
            result += self._finder_penalty_terminate_and_count(runcolor, runx, runhistory) * _PENALTY_N3

        # Rule 1 & Rule 3 (Vertikal)
        for x in range(size):
            runcolor = False
            runy = 0
            runhistory = collections.deque([0] * 7, 7)
            for y in range(size):
                if modules[y][x] == runcolor:
                    runy += 1
                    if runy == 5:
                        result += _PENALTY_N1
                    elif runy > 5:
                        result += 1
                else:
                    self._finder_penalty_add_history(runy, runhistory)
                    if not runcolor:
                        result += self._finder_penalty_count_patterns(runhistory) * _PENALTY_N3
                    runcolor = modules[y][x]
                    runy = 1
            result += self._finder_penalty_terminate_and_count(runcolor, runy, runhistory) * _PENALTY_N3

        # Rule 2: Kotak modul 2x2 satu warna
        for y in range(size - 1):
            for x in range(size - 1):
                if modules[y][x] == modules[y][x + 1] == modules[y + 1][x] == modules[y + 1][x + 1]:
                    result += _PENALTY_N2

        # Rule 4: Keseimbangan modul gelap & terang
        dark = sum(row.count(True) for row in modules)
        total = size * size
        k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
        result += k * _PENALTY_N4
        return result

    def _finder_penalty_add_history(self, currentrunlength: int, runhistory: collections.deque) -> None:
        if runhistory[0] == 0:
            currentrunlength += self.size
        runhistory.appendleft(currentrunlength)

    def _finder_penalty_count_patterns(self, runhistory: collections.deque) -> int:
        n = runhistory[1]
        core = (n > 0 and runhistory[2] == n and runhistory[4] == n and runhistory[5] == n and runhistory[3] == n * 3)
        return (1 if (core and runhistory[0] >= n * 4 and runhistory[6] >= n) else 0) + \
               (1 if (core and runhistory[6] >= n * 4 and runhistory[0] >= n) else 0)

    def _finder_penalty_terminate_and_count(self, currentruncolor: bool, currentrunlength: int, runhistory: collections.deque) -> int:
        if currentruncolor:
            self._finder_penalty_add_history(currentrunlength, runhistory)
            currentrunlength = 0
        currentrunlength += self.size
        self._finder_penalty_add_history(currentrunlength, runhistory)
        return self._finder_penalty_count_patterns(runhistory)

    def to_svg(self, border: int = 2) -> str:
        """
        Menghasilkan markup SVG inline yang ringkas dan tajam untuk pencetakan.
        """
        parts = []
        for y in range(self.size):
            for x in range(self.size):
                if self.modules[y][x]:
                    parts.append(f"M{x + border},{y + border}h1v1h-1z")
        total_dim = self.size + border * 2
        path_str = " ".join(parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'viewBox="0 0 {total_dim} {total_dim}" '
            f'width="100%" height="100%" shape-rendering="crispEdges">\n'
            f'<rect width="100%" height="100%" fill="#FFFFFF"/>\n'
            f'<path d="{path_str}" fill="#000000"/>\n'
            f'</svg>'
        )


def encode_text(text: str, ecl: int = Ecc.MEDIUM) -> QrCode:
    """
    Mengenkode teks menjadi objek matriks QrCode dengan memilih mode dan versi optimal.
    """
    if not text:
        raise ValueError("Teks untuk QR Code tidak boleh kosong.")

    # Tentukan mode karakter paling efisien
    if all(c in "0123456789" for c in text):
        mode = "numeric"
    elif all(c in ALPHANUMERIC_CHARSET for c in text):
        mode = "alphanumeric"
    else:
        mode = "byte"

    # Cari versi terkecil yang muat
    chosen_ver = None
    bb = None
    for ver in range(1, 41):
        data_cap_bytes = _get_num_data_codewords(ver, ecl)
        data_cap_bits = data_cap_bytes * 8

        b = _BitBuffer()
        if mode == "numeric":
            b.append_bits(0b0001, 4)
            c_bits = 10 if ver < 10 else (12 if ver < 27 else 14)
            b.append_bits(len(text), c_bits)
            for i in range(0, len(text), 3):
                chunk = text[i:i+3]
                b.append_bits(int(chunk), 10 if len(chunk) == 3 else (7 if len(chunk) == 2 else 4))
        elif mode == "alphanumeric":
            b.append_bits(0b0010, 4)
            c_bits = 9 if ver < 10 else (11 if ver < 27 else 13)
            b.append_bits(len(text), c_bits)
            for i in range(0, len(text), 2):
                chunk = text[i:i+2]
                if len(chunk) == 2:
                    v = ALPHANUMERIC_CHARSET.index(chunk[0]) * 45 + ALPHANUMERIC_CHARSET.index(chunk[1])
                    b.append_bits(v, 11)
                else:
                    v = ALPHANUMERIC_CHARSET.index(chunk[0])
                    b.append_bits(v, 6)
        else:  # byte
            data_bytes = text.encode("utf-8")
            b.append_bits(0b0100, 4)
            c_bits = 8 if ver < 10 else 16
            b.append_bits(len(data_bytes), c_bits)
            for byte in data_bytes:
                b.append_bits(byte, 8)

        if len(b) <= data_cap_bits:
            chosen_ver = ver
            bb = b
            break

    if chosen_ver is None:
        raise ValueError("Data terlalu panjang untuk kapasitas QR Code.")

    data_cap_bits = _get_num_data_codewords(chosen_ver, ecl) * 8
    # Terminator
    term_bits = min(4, data_cap_bits - len(bb))
    bb.append_bits(0, term_bits)

    # Pad ke kelipatan 8 bit
    while len(bb) % 8 != 0:
        bb.append(0)

    # Pad bytes alternating 0xEC, 0x11
    pad_bytes = (0xEC, 0x11)
    pad_idx = 0
    while len(bb) < data_cap_bits:
        bb.append_bits(pad_bytes[pad_idx], 8)
        pad_idx ^= 1

    # Konversi bit buffer ke bytes
    raw_bytes = bytearray()
    for i in range(0, len(bb), 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | bb[i + j]
        raw_bytes.append(byte_val)

    return QrCode(chosen_ver, ecl, bytes(raw_bytes))


def generate_qr_svg(payload: str, ecl: int = Ecc.MEDIUM, border: int = 2) -> str:
    """
    Menghasilkan string SVG representasi QR Code dari payload teks.
    """
    qr = encode_text(payload, ecl=ecl)
    return qr.to_svg(border=border)


def generate_copy_qr_svg(copy_id: str, border: int = 2) -> str:
    """
    Menghasilkan SVG QR Code khusus untuk eksemplar buku (Task 3-08).
    Memenuhi DEC-011:
    - Payload HANYA dan STRICTLY memuat copy_id unik (contoh: 'C-234567').
    - Tidak memuat judul, nama anggota, nomor telepon, URL, atau metadata lainnya.
    """
    if not copy_id or not str(copy_id).strip():
        raise ValueError("ID eksemplar wajib diisi untuk pembuatan label QR.")

    clean_id = str(copy_id).strip()
    return generate_qr_svg(clean_id, ecl=Ecc.MEDIUM, border=border)


def generate_member_qr_svg(token: str, border: int = 2) -> str:
    """
    Menghasilkan SVG QR Code khusus untuk kartu anggota perpustakaan (Task 4-01, DEC-010, LIB-QR-001).
    Payload berupa token HMAC-SHA256: '{member_id}:{qr_version}:{signature_hex}'.
    Tidak memuat data pribadi anggota (nama, kelas, telepon) dalam teks terbuka.
    """
    if not token or not isinstance(token, str) or not token.strip():
        raise ValueError("Token anggota wajib diisi untuk pembuatan QR Code.")

    clean_token = token.strip()
    return generate_qr_svg(clean_token, ecl=Ecc.MEDIUM, border=border)


