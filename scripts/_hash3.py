import hashlib, struct
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
pem = r'C:\Users\lwz18\.mitmproxy\mitmproxy-ca-cert.pem'
cert = x509.load_pem_x509_certificate(open(pem,'rb').read())
# Get subject as DER (Name type pre-encoded)
# cryptography exposes subject via rfc4514_string, but we need raw DER via _init
from cryptography.x509.oid import NameOID
# Use the raw public extension: subject.public_bytes() exists
try:
    subject_der = cert.subject.public_bytes()
    print('subject_public_bytes ok, len:', len(subject_der))
except Exception as e:
    print('public_bytes failed:', e)
    # fallback: re-encode via openssl
    import OpenSSL.crypto as occ
    ocrt = occ.load_certificate(occ.FILETYPE_PEM, open(pem,'rb').read())
    subject_der = occ.dump_certificate(occ.FILETYPE_ASN1, ocrt)
    # NOT subject only: that's whole cert. But can use it to compute subject hash via openssl Extract DN
    subject_der = ocrt.get_subject()._x509_name  # may not work
md5 = hashlib.md5(subject_der).digest()
# Take first 4 bytes as little-endian unsigned int  
h = struct.unpack('<I', md5[:4])[0]
print('hash_old_style:', f'{h:08x}.0')
