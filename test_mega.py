import requests, json

folder_id = 'NotjiSyL'

resp = requests.post(
    f'https://g.api.mega.co.nz/cs?id=0&n={folder_id}',
    json=[{'a': 'f', 'c': 1, 'r': 1}],
    headers={'Content-Type': 'application/json'},
    timeout=30
)
nodos = resp.json()[0].get('f', [])
print('Total nodos:', len(nodos))

# Mostrar todos los tipos
tipos = {}
for n in nodos:
    t = n.get('t', 0)
    tipos[t] = tipos.get(t, 0) + 1
print('Conteo por tipo:', tipos)

# Mostrar primeros 5 nodos tipo 1 (carpetas)
print('\nPrimeras carpetas:')
carpetas = [n for n in nodos if n.get('t') == 1]
for c in carpetas[:5]:
    print(json.dumps(c, indent=2))