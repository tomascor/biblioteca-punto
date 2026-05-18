import requests, json, base64, struct

folder_id = 'NotjiSyL'
folder_key_b64 = 'GuuK9sPFOZlllkxQsFQmhQ'

def base64_to_a32(b64):
    b64 = b64.replace('-', '+').replace('_', '/')
    padding = (4 - len(b64) % 4) % 4
    b64 += '=' * padding
    data = base64.b64decode(b64)
    count = len(data) // 4
    return list(struct.unpack(f'>{count}I', data[:count*4]))

resp = requests.post(
    f'https://g.api.mega.co.nz/cs?id=0&n={folder_id}',
    json=[{'a': 'f', 'c': 1, 'r': 1}],
    headers={'Content-Type': 'application/json'},
    timeout=30
)
nodos = resp.json()[0].get('f', [])
todos_ids = {n['h'] for n in nodos}

# Encontrar raíz
raiz_id = None
for n in nodos:
    if n.get('t') == 1 and n.get('p', '') not in todos_ids:
        raiz_id = n['h']
        break

print(f'Raíz encontrada: {raiz_id}')

# Contar hijos directos de la raíz
hijos_raiz = [n for n in nodos if n.get('p') == raiz_id]
print(f'Hijos directos de la raíz: {len(hijos_raiz)}')

# Mostrar un archivo (t=0) de ejemplo
archivos = [n for n in nodos if n.get('t') == 0]
print(f'\nTotal archivos: {len(archivos)}')
print('Ejemplo de archivo:')
print(json.dumps(archivos[0], indent=2))

# Intentar descifrar el nombre del primer archivo
from Crypto.Cipher import AES

folder_key = base64_to_a32(folder_key_b64)
n = archivos[0]