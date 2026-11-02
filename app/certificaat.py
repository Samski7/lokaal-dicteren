"""Maakt een self-signed certificaat zodat de microfoon ook op een gsm in het LAN werkt.

Browsers geven enkel microfoontoegang via HTTPS (of op localhost). Het certificaat is
geldig voor localhost en de huidige LAN-IP's van deze pc.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def lan_ips() -> list[str]:
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    # IP van de standaardroute (stuurt geen pakketten, bepaalt enkel de interface).
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def zorg_voor_certificaat(map_: Path) -> tuple[Path, Path]:
    """Geeft (cert, key); maakt ze opnieuw als ze ontbreken of de LAN-IP's veranderd zijn."""
    map_.mkdir(parents=True, exist_ok=True)
    cert_pad, key_pad = map_ / "cert.pem", map_ / "key.pem"
    ips = lan_ips()

    if cert_pad.exists() and key_pad.exists():
        cert = x509.load_pem_x509_certificate(cert_pad.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        bekend = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
        nog_geldig = cert.not_valid_after_utc > dt.datetime.now(dt.UTC) + dt.timedelta(days=7)
        if set(ips) <= bekend and nog_geldig:
            return cert_pad, key_pad

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    naam = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "spraak-naar-tekst (lokaal)")])
    alt = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    alt += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]
    nu = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(naam)
        .issuer_name(naam)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(nu - dt.timedelta(days=1))
        .not_valid_after(nu + dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_pad.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_pad.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return cert_pad, key_pad
