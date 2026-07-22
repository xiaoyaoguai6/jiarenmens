import hashlib
from OpenSSL import crypto
pem = r'C:\Users\lwz18\.mitmproxy\mitmproxy-ca-cert.pem'
cert = crypto.load_certificate(crypto.FILETYPE_PEM, open(pem,'rb').read())
subject_der = crypto.dump_X509_NAME(crypto.FILETYPE_ASN1, cert.get_subject())
# Open's X509_subject_hash_old actually recomputes subject as canonical (i.e., UTF8String normalisation)
# but mitmproxy's CA cert is typically pure ASCII, canonical == raw.
md5 = hashlib.md5(subject_der).digest()
# OpenSSL: hash is a 4-byte little-endian value out of md5
import struct
h = struct.unpack('<I', md5[:4])[0]
filename = f'{h:08x}.0'
print('subject_hash_old filename:', filename)
