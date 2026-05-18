import requests, json, base64, struct
from Crypto.Cipher import AES

folder_id = 'NotjiSyL'
folder_key_b64 = 'GuuK9sPFOZlllkxQsFQmhQ'
raiz_id = 'Rt03gb6T'

def b64_to_bytes(b64):
    b64 = b64.replace('-','+').replace('_','/')
    b64 += '=' * ((4 - len(b64) % 4) % 4)
    return base64.b64decode(b64)

def b64_to_a32(b64):
    data = b64_to_bytes(b64)
    return list(struct.unpack(f'>{len(data)//4}I', data[:len(data)//4*4]))

def a32_to_bytes(a32):
    return struct.pack(f'>{len(a32)}I', *a32)

# La clave de carpeta se usa directamente como clave AES de 16 bytes
folder_key_bytes = b64_to_bytes(folder_key_b64)
print(f'folder_key_bytes len: {len(folder_key_bytes)}')
print(f'folder_key_bytes: {folder_key_bytes.hex()}')

resp = requests.post(
    f'https://g.api.mega.co.nz/cs?id=0&n={folder_id}',
    json=[{'a': 'f', 'c': 1, 'r': 1}],
    headers={'Content-Type': 'application/json'},
    timeout=30
)
nodos = resp.json()[0].get('f', [])
archivos = [n for n in nodos if n.get('t') == 0]
n = archivos[0]

# Extraer clave cifrada con raiz_id
key_raw = n.get('k', '')
key_b64 = ''
for parte in key_raw.split('/'):
    if ':' in parte:
        kid, kval = parte.split(':', 1)
        if kid == raiz_id:
            key_b64 = kval

enc_bytes = b64_to_bytes(key_b64)
print(f'enc_bytes len: {len(enc_bytes)}')

# Descifrar con AES-ECB usando folder_key directamente
cipher = AES.new(folder_key_bytes[:16], AES.MODE_ECB)

# Para archivos: la clave cifrada son 32 bytes (2 bloques AES)
# Descifrar y hacer XOR de los dos bloques para obtener la clave real
dec1 = cipher.decrypt(enc_bytes[:16])
dec2 = cipher.decrypt(enc_bytes[16:32])
# XOR de los dos bloques
node_key = bytes(a^b for a,b in zip(dec1, dec2))
print(f'node_key: {node_key.hex()}')

# Descifrar atributos
attr_bytes = b64_to_bytes(n['a'])
cipher2 = AES.new(node_key, AES.MODE_CBC, iv=b'\x00'*16)
dec = cipher2.decrypt(attr_bytes)
print(f'Descifrado: {dec[:80]}')