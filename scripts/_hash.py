import sys
from OpenSSL import crypto
import hashlib
pem = r'C:\Users\lwz18\.mitmproxy\mitmproxy-ca-cert.pem'
cert = crypto.load_certificate(crypto.FILETYPE_PEM, open(pem,'rb').read())
# The "old" hash is computed by openssl's X509_subject_hash_old defined for pre-1.0.0 openssl.
# Replicate with md5 first 4 bytes of subject Name as canonical DER form's md5.
der = crypto.dump_certificate(crypto.FILETYPE_ASN1, cert)
# subject_hash_old in openssl:
#   unsigned long ret = 0;
#   for (int i=0; i<MD5_DIGEST_LENGTH; i++) ret = (ret*16+md5[i])%... (simplified)
# Easiest is invoke cffi to call openssl X509_subject_hash_old directly.
import ctypes
# load libeay32/libcrypto
import os, glob
candidates = glob.glob(r'C:\Program Files\OpenSSL-Win64\bin\libcrypto*.dll') + \
  glob.glob(r'C:\Users\lwz18\AppData\Local\Programs\Python\Python312\DLLs\libcrypto*.dll') + \
  glob.glob(r'C:\Users\lwz18\AppData\Local\Programs\Python\Python312\Lib\site-packages\**\libcrypto*.dll', recursive=True) + \
  glob.glob(r'C:\Users\lwz18\AppData\Local\Programs\Python\Python312\DLLs\libssl*.dll')
print('libcrypto candidates:', candidates)
