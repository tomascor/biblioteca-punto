import json, re

with open('datos.json', 'r', encoding='utf-8') as f:
    datos = json.load(f)

folder_id = 'NotjiSyL'
folder_key = 'GuuK9sPFOZlllkxQsFQmhQ'

for d in datos:
    url = d.get('url_pdf', '')
    # Arreglar URLs sin la clave
    match = re.search(r'/file/([^#\s]+)', url)
    if match and '#' not in url:
        file_id = match.group(1)
        d['url_pdf'] = f"https://mega.nz/folder/{folder_id}#{folder_key}/file/{file_id}"

with open('datos.json', 'w', encoding='utf-8') as f:
    json.dump(datos, f, ensure_ascii=False, indent=2)

print(f"URLs corregidas: {len(datos)}")
print("Ejemplo:", datos[0]['url_pdf'])