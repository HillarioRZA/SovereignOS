"""
Smart Guardian & Static Security Scanner.
Menegakkan Invarian Suci 5: Keamanan ditegakkan secara deterministik oleh kode.
Mencegah injeksi kode berbahaya, akses ke berkas sensitif OS, dan circuit breaker denial.
"""

import re
from typing import List, Optional, Tuple

DANGEROUS_PATTERNS: List[Tuple[str, str]] = [
    (r"rm\s+(-[rfRF]+\s+|--recursive\s+|--force\s+)*[/~]", "Perintah penghapusan sistem berbahaya (rm -rf root/home)"),
    (r"/etc/(?:passwd|shadow|sudoers)", "Akses ke berkas kredensial sistem Linux"),
    (r"~?/\.(?:ssh|aws|docker)/", "Akses ke folder kredensial sensitif (.ssh, .aws, .docker)"),
    (r"/var/run/docker\.sock", "Percobaan eskalasi akses Docker socket"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork bomb terdeteksi"),
    (r"(?:mkfs|fdisk|dd\s+if=)", "Operasi manipulasi filesystem mentah berbahaya"),
    (r"__import__\s*\(\s*['\"]os['\"]\s*\)\.system", "Percobaan remote code execution os.system tidak sah"),
    (r"shutil\.rmtree\s*\(\s*['\"][/~]", "Penghapusan direktori rekursif berbahaya"),
]


def scan_payload_safety(text: str) -> Tuple[bool, Optional[str]]:
    """Memindai konten teks, skrip, atau perintah dari potensi eksploitasi berbahaya.
    
    Mengembalikan:
        Tuple (is_safe, error_message).
    """
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False, f"Pemindaian Keamanan Menolak Eksekusi: {description}"
    return True, None


def check_denial_circuit_breaker(consecutive_failures: int, max_threshold: int = 3) -> bool:
    """Memeriksa apakah batas toleransi kegagalan berturut-turut telah terlampaui."""
    return consecutive_failures >= max_threshold
