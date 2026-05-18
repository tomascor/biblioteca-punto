#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Biblioteca de Punto - Script de actualización
Conecta con MEGA, detecta PDFs nuevos, extrae miniaturas y actualiza la web.
"""

import os
import sys
import json
import subprocess
import re
import base64
import struct
import hashlib
import hmac
import time
import requests
from pathlib import Path

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
MEGA_ENLACE = "https://mega.nz/folder/NotjiSyL#GuuK9sPFOZlllkxQsFQmhQ"
CARPETA_MINIATURAS = "miniaturas"
ARCHIVO_DATOS = "datos.json"
TIPOS_DISPONIBLES = [
    "Jersey", "Calcetines", "Guantes", "Gorro", "Bufanda",
    "Chal", "Chaqueta", "Bolso", "Amigurumi", "Otro"
]
# ──────────────────────────────────────────────────────────────────────────────

def instalar_dependencias():
    """Instala librerías necesarias si no están presentes."""
    libs = ["pymupdf", "pillow", "requests"]
    for lib in libs:
        try:
            __import__(lib if lib != "pymupdf" else "fitz")
        except ImportError:
            print(f"  Instalando {lib}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib, "-q"])

def parsear_enlace_mega(enlace):
    """Extrae folder_id y folder_key del enlace de MEGA."""
    match = re.search(r'mega\.nz/folder/([^#/]+)#([^/\s]+)', enlace)
    if not match:
        raise ValueError(f"Enlace de MEGA no válido: {enlace}")
    return match.group(1), match.group(2)

def base64_to_a32(b64):
    """Convierte base64 de MEGA a lista de enteros."""
    b64 = b64.replace('-', '+').replace('_', '/')
    padding = (4 - len(b64) % 4) % 4
    b64 += '=' * padding
    data = base64.b64decode(b64)
    count = len(data) // 4
    return list(struct.unpack(f'>{count}I', data[:count*4]))

def b64_to_bytes(b64):
    """Decodifica base64 de MEGA a bytes."""
    b64 = b64.replace('-', '+').replace('_', '/')
    b64 += '=' * ((4 - len(b64) % 4) % 4)
    return base64.b64decode(b64)

def decrypt_attr(attr_bytes, node_key_bytes):
    """Descifra los atributos de un nodo MEGA."""
    try:
        from Crypto.Cipher import AES
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pycryptodome", "-q"])
        from Crypto.Cipher import AES

    cipher = AES.new(node_key_bytes, AES.MODE_CBC, iv=b'\x00'*16)
    decrypted = cipher.decrypt(attr_bytes)
    try:
        text = decrypted.decode('utf-8', errors='ignore').rstrip('\x00')
        match = re.search(r'MEGA(\{.+?\})', text)
        if match:
            return json.loads(match.group(1))
    except Exception:
        pass
    return {}

def obtener_clave_nodo(node_key_b64, folder_key_bytes):
    """Descifra la clave de un nodo usando la clave de la carpeta (bytes)."""
    from Crypto.Cipher import AES
    enc_bytes = b64_to_bytes(node_key_b64)
    cipher = AES.new(folder_key_bytes, AES.MODE_ECB)
    if len(enc_bytes) >= 32:
        dec1 = cipher.decrypt(enc_bytes[:16])
        dec2 = cipher.decrypt(enc_bytes[16:32])
        return bytes(a ^ b for a, b in zip(dec1, dec2))
    else:
        return cipher.decrypt(enc_bytes[:16])


def obtener_nodos_mega(folder_id, folder_key_a32):
    """Obtiene todos los nodos de la carpeta MEGA."""
    print("  Conectando con MEGA...")
    resp = requests.post(
        f'https://g.api.mega.co.nz/cs?id=0&n={folder_id}',
        json=[{'a': 'f', 'c': 1, 'r': 1}],
        headers={'Content-Type': 'application/json'},
        timeout=30
    )
    if resp.status_code != 200:
        raise ConnectionError(f"Error al conectar con MEGA: {resp.status_code}")
    
    data = resp.json()
    if isinstance(data, list) and len(data) > 0:
        return data[0].get('f', [])
    return []

def construir_arbol(nodos, folder_id):
    """Construye un árbol de carpetas/archivos a partir de los nodos."""
    nodo_por_id = {n['h']: n for n in nodos}
    hijos = {}
    for n in nodos:
        parent = n.get('p', '')
        if parent not in hijos:
            hijos[parent] = []
        hijos[parent].append(n['h'])
    return nodo_por_id, hijos

def generar_enlace_pdf(folder_id, folder_key_b64, file_id, file_key_a32):
    """Genera el enlace directo al PDF en MEGA."""
    # Enlace de tipo folder file
    return f"https://mega.nz/folder/{folder_id}/file/{file_id}"

def listar_pdfs_mega(folder_id, folder_key_b64):
    """Lista todos los PDFs de la carpeta MEGA con sus metadatos."""
    folder_key_bytes = b64_to_bytes(folder_key_b64)
    folder_key_a32 = base64_to_a32(folder_key_b64)
    nodos = obtener_nodos_mega(folder_id, folder_key_a32)

    if not nodos:
        print("  ⚠ No se encontraron nodos en MEGA.")
        return []

    nodo_por_id, hijos = construir_arbol(nodos, folder_id)

    # Encontrar nodo raíz: carpeta cuyo padre NO existe en la lista
    todos_ids = {n['h'] for n in nodos}
    raiz_id = None
    for n in nodos:
        if n.get('t') == 1 and n.get('p', '') not in todos_ids:
            raiz_id = n['h']
            break
    if not raiz_id:
        for n in nodos:
            if n.get('t') == 1:
                raiz_id = n['h']
                break
    if not raiz_id and nodos:
        raiz_id = nodos[0]['h']

    pdfs = []

    def recorrer(node_id, carpeta_actual):
        for hijo_id in hijos.get(node_id, []):
            nodo = nodo_por_id.get(hijo_id)
            if not nodo:
                continue

            tipo = nodo.get('t', 0)
            key_raw = nodo.get('k', '')

            # Buscar la clave cifrada con la clave de carpeta raíz
            key_b64 = ''
            for parte in key_raw.split('/'):
                if ':' in parte:
                    kid, kval = parte.split(':', 1)
                    if kid == raiz_id:
                        key_b64 = kval
                        break
            if not key_b64:
                for parte in key_raw.split('/'):
                    if ':' in parte:
                        key_b64 = parte.split(':', 1)[1]

            # Descifrar nombre
            nombre = f"nodo_{hijo_id}"
            if key_b64:
                try:
                    node_key_bytes = obtener_clave_nodo(key_b64, folder_key_bytes)
                    attr_b64 = nodo.get('a', '')
                    if attr_b64:
                        attr_bytes = b64_to_bytes(attr_b64)
                        attrs = decrypt_attr(attr_bytes, node_key_bytes)
                        nombre = attrs.get('n', nombre)
                except Exception:
                    pass

            if tipo == 1:  # carpeta
                recorrer(hijo_id, nombre)
            elif tipo == 0:  # archivo
                if nombre.lower().endswith('.pdf'):
                    enlace = generar_enlace_pdf(folder_id, folder_key_b64, hijo_id, [])
                    pdfs.append({
                        'id': hijo_id,
                        'nombre': Path(nombre).stem,
                        'disenadora': carpeta_actual,
                        'url_pdf': enlace,
                        'miniatura': '',
                        'tipo': '',
                        'observaciones': '',
                        'nuevo': True
                    })

    recorrer(raiz_id, '')
    return pdfs


def extraer_miniatura(url_pdf, nombre_archivo, carpeta_miniaturas):
    """Descarga el PDF y extrae la primera página como imagen."""
    import fitz  # PyMuPDF
    from PIL import Image
    import io

    ruta_miniatura = os.path.join(carpeta_miniaturas, nombre_archivo + ".jpg")
    
    if os.path.exists(ruta_miniatura):
        return ruta_miniatura

    print(f"    Descargando para miniatura: {nombre_archivo}...")
    try:
        # Intentar descargar solo el inicio del PDF
        headers = {'Range': 'bytes=0-500000'}  # primeros 500KB
        resp = requests.get(url_pdf, headers=headers, timeout=30, stream=True)
        
        if resp.status_code not in (200, 206):
            return ''

        pdf_bytes = b''
        for chunk in resp.iter_content(chunk_size=8192):
            pdf_bytes += chunk
            if len(pdf_bytes) > 500000:
                break

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pagina = doc[0]
        mat = fitz.Matrix(1.5, 1.5)
        pix = pagina.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.save(ruta_miniatura, "JPEG", quality=75, optimize=True)
        doc.close()
        return ruta_miniatura
    except Exception as e:
        print(f"    ⚠ No se pudo extraer miniatura: {e}")
        return ''

def pedir_tipo(nombre):
    """Pregunta al usuario el tipo de diseño."""
    print(f"\n  📄 Diseño: {nombre}")
    print("  Elige el tipo:")
    for i, t in enumerate(TIPOS_DISPONIBLES, 1):
        print(f"    {i}. {t}")
    while True:
        resp = input("  Número (o Enter para saltar): ").strip()
        if resp == '':
            return ''
        if resp.isdigit() and 1 <= int(resp) <= len(TIPOS_DISPONIBLES):
            return TIPOS_DISPONIBLES[int(resp)-1]
        print("  Número no válido, intenta de nuevo.")

def pedir_observaciones(nombre):
    """Pregunta observaciones opcionales."""
    obs = input(f"  Observaciones (Enter para dejar vacío): ").strip()
    return obs

def main():
    print("\n" + "="*55)
    print("  🧶 Biblioteca de Punto — Actualizador")
    print("="*55 + "\n")

    # Instalar dependencias
    print("▶ Verificando dependencias...")
    instalar_dependencias()
    import fitz
    from PIL import Image

    # Crear carpeta de miniaturas si no existe
    os.makedirs(CARPETA_MINIATURAS, exist_ok=True)

    # Cargar datos existentes
    datos_existentes = []
    if os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, 'r', encoding='utf-8') as f:
            try:
                datos_existentes = json.load(f)
            except json.JSONDecodeError:
                datos_existentes = []

    ids_existentes = {d['id'] for d in datos_existentes if 'id' in d}
    print(f"▶ Diseños ya en base de datos: {len(datos_existentes)}\n")

    # Conectar con MEGA
    print("▶ Conectando con MEGA y listando PDFs...")
    try:
        folder_id, folder_key_b64 = parsear_enlace_mega(MEGA_ENLACE)
        todos_pdfs = listar_pdfs_mega(folder_id, folder_key_b64)
    except Exception as e:
        print(f"\n  ✗ Error al acceder a MEGA: {e}")
        input("\nPulsa Enter para cerrar...")
        sys.exit(1)

    print(f"  ✓ PDFs encontrados en MEGA: {len(todos_pdfs)}")

    # Detectar nuevos
    nuevos = [p for p in todos_pdfs if p['id'] not in ids_existentes]
    print(f"  ✓ PDFs nuevos detectados: {len(nuevos)}\n")

    if not nuevos:
        print("✅ No hay diseños nuevos. Todo está al día.")
        # Marcar todos como no-nuevos en datos existentes
        for d in datos_existentes:
            d['nuevo'] = False
        with open(ARCHIVO_DATOS, 'w', encoding='utf-8') as f:
            json.dump(datos_existentes, f, ensure_ascii=False, indent=2)
        subir_a_github()
        input("\nPulsa Enter para cerrar...")
        return

    print(f"▶ Procesando {len(nuevos)} diseño(s) nuevo(s)...\n")
    print(f"▶ Procesando {len(nuevos)} diseño(s) nuevo(s)...\n")

    # Preguntar modo de clasificación
    print("  ¿Cómo quieres clasificar los nuevos diseños?")
    print("    1. Uno a uno ahora")
    print("    2. Saltar todos (quedan como Sin clasificar)")
    modo = input("  Elige (1 o 2): ").strip()
    clasificar_ahora = (modo == "1")
    print()

    for i, pdf in enumerate(nuevos, 1):
        print(f"  [{i}/{len(nuevos)}] {pdf['nombre']}")

        # Extraer miniatura
        ruta_mini = extraer_miniatura(pdf['url_pdf'], pdf['id'], CARPETA_MINIATURAS)
        if ruta_mini:
            pdf['miniatura'] = ruta_mini.replace('\\', '/')

        if clasificar_ahora:
            pdf['tipo'] = pedir_tipo(pdf['nombre'])
            pdf['observaciones'] = pedir_observaciones(pdf['nombre'])
        else:
            pdf['tipo'] = 'Sin clasificar'
            pdf['observaciones'] = ''
        pdf['nuevo'] = True

    # Marcar los anteriores como no-nuevos
    for d in datos_existentes:
        d['nuevo'] = False

    # Combinar y guardar
    datos_finales = datos_existentes + nuevos
    with open(ARCHIVO_DATOS, 'w', encoding='utf-8') as f:
        json.dump(datos_finales, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Base de datos actualizada: {len(datos_finales)} diseños en total.")

    # Subir a GitHub
    subir_a_github()
    input("\nPulsa Enter para cerrar...")

def subir_a_github():
    """Hace commit y push a GitHub."""
    print("\n▶ Subiendo cambios a GitHub...")
    try:
        subprocess.run(['git', 'add', '.'], check=True)
        resultado = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            capture_output=True
        )
        if resultado.returncode == 0:
            print("  No hay cambios nuevos que subir.")
            return
        subprocess.run(['git', 'commit', '-m', 'Actualización automática de diseños'], check=True)
        subprocess.run(['git', 'push'], check=True)
        print("  ✓ Web actualizada en GitHub Pages.")
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ Error al subir a GitHub: {e}")

if __name__ == '__main__':
    main()
