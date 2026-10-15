import gzip
import os
import ssl
import urllib.request
from pathlib import Path

USER_AGENT = 'Master-API'
GZIP_MAGIC = b'\x1f\x8b'
CHUNK_BYTES = 1 << 20

# The IBGE server doesn't send Sectigo's intermediate certificate. Browsers
# and Windows fetch it on their own; Python doesn't and refuses the
# connection (CERTIFICATE_VERIFY_FAILED), so it ships here. Valid until
# 2036-03-21. Source: http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt
IBGE_INTERMEDIATE_CERT = Path(__file__).with_name('ibge_intermediate.pem')


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=IBGE_INTERMEDIATE_CERT)
    # Accept a chain ending at the intermediate, in case the root is missing
    context.verify_flags |= getattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN', 0)
    return context


SSL_CONTEXT = _ssl_context()


def _open(url: str, timeout: float):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    return urllib.request.urlopen(
        request, timeout=timeout, context=SSL_CONTEXT
    )


def fetch(url: str, timeout: float = 120) -> bytes:
    with _open(url, timeout) as response:
        content = response.read()
    # IBGE sends gzip even unasked, sometimes without Content-Encoding
    return gzip.decompress(content) if content[:2] == GZIP_MAGIC else content


def download(url: str, destination: Path, timeout: float = 600) -> Path:
    """Streams url into destination; a failed download leaves no file."""
    partial = destination.with_name(destination.name + '.part')
    with _open(url, timeout) as response, partial.open('wb') as file:
        while chunk := response.read(CHUNK_BYTES):
            file.write(chunk)
    os.replace(partial, destination)
    return destination
