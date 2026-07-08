# Comparación de precios de supermercados

Proyecto en Python para consolidar productos extraídos desde supermercados, normalizar sus columnas, comparar precios entre cadenas y construir análisis relacionados con carrito de compra y Canasta Básica de Alimentos (CBA).

Actualmente el flujo trabaja con tres supermercados:

- Jumbo
- Unimarc
- Lider

La carpeta principal de trabajo técnico es:

```text
Supermercados/Comparacion/src/extraccion_limpieza/
```

---

## Objetivo del proyecto

Este módulo toma los CSV generados por los procesos de scraping de cada supermercado, los unifica en un formato común y genera salidas analíticas para responder preguntas como:

- ¿Cuál es el consolidado completo de productos disponibles?
- ¿Qué productos parecen equivalentes entre supermercados?
- ¿Dónde conviene comprar un carrito definido por el usuario?
- ¿Qué supermercado tiene menor costo estimado para una CBA detectada?
- ¿Cuál sería una canasta económica o premium usando productos disponibles?

---

## Estructura general

```text
Supermercados/
├── CBA/
│   └── Valor_CBA_y_LPs_25.12.pdf
├── Jumbo/
│   └── output/
├── Lider/
│   └── output/
├── Unimarc/
│   └── output/
└── Comparacion/
    ├── README.md
    └── src/
        ├── extraccion_limpieza/
        │   ├── extraccion_limpieza.py
        │   ├── comparar_carrito.py
        │   ├── cba_builder.py
        │   ├── cba_ahorro_supermercado.py
        │   ├── cba_escenario_economico.py
        │   ├── cba_escenario_premium.py
        │   ├── extraer_cba_desde_pdf.py
        │   ├── carrito.txt
        │   ├── config.py
        │   ├── pipeline.py
        │   ├── readers.py
        │   ├── builders.py
        │   ├── normalizers.py
        │   ├── product_matcher.py
        │   └── utils.py
        └── output/
            ├── consolidado/
            ├── carrito_comparado/
            ├── cba/
            ├── cba_escenario1_economico/
            ├── cba_escenario_premium/
            └── out_cba/
```

---

## Requisitos

Versión recomendada:

- Python 3.10 o superior

Librerías usadas por los scripts:

```bash
pip install pandas numpy scikit-learn pdfplumber
```

Notas:

- `pandas` y `numpy` se usan en casi todo el procesamiento.
- `scikit-learn` se usa en el matching de productos (`product_matcher.py`).
- `pdfplumber` se usa para extraer datos de la CBA oficial desde PDF (`extraer_cba_desde_pdf.py`).

---

## Preparación inicial

Desde la raíz del repositorio:

```powershell
cd "C:\Users\fvergram\OneDrive - NTT DATA EMEAL\Desktop\webscrapping"
```

Luego entra a la carpeta de scripts:

```powershell
cd "Supermercados\Comparacion\src\extraccion_limpieza"
```

Los scripts detectan rutas a partir de su propia ubicación, pero se recomienda ejecutarlos desde esta carpeta para evitar problemas con imports locales.

---

## Entradas esperadas

### 1. CSV de supermercados

El consolidado espera encontrar archivos CSV dentro de:

```text
Supermercados/Jumbo/output/
Supermercados/Unimarc/output/
Supermercados/Lider/output/
```

Cada supermercado puede tener subcarpetas por categoría. El pipeline busca CSV dentro de esas carpetas y toma los archivos más recientes según la fecha del nombre o metadata disponible.

### 2. Carrito de compra

El archivo de carrito vive en:

```text
Supermercados/Comparacion/src/extraccion_limpieza/carrito.txt
```

Formato esperado: un producto por línea.

Ejemplo:

```text
arroz
aceite vegetal 1 litro
leche entera 1 litro
avena 500 g
pechuga de pollo 1 kg
tomate
plátano
chocolate
```

### 3. PDF oficial de CBA

Para extraer la CBA desde PDF, el script espera este archivo:

```text
Supermercados/CBA/Valor_CBA_y_LPs_25.12.pdf
```

El script actual extrae las páginas configuradas en `extraer_cba_desde_pdf.py`:

```python
TARGET_PAGES = [11, 12]
```

---

## Orden recomendado de ejecución

El flujo principal se puede entender así:

```text
CSV Jumbo/Lider/Unimarc
        │
        ▼
extraccion_limpieza.py
        │
        ├── comparar_carrito.py
        │
        ├── cba_builder.py ──► cba_ahorro_supermercado.py
        │
        └── extraer_cba_desde_pdf.py ──► cba_escenario_economico.py / cba_escenario_premium.py
```

Orden práctico:

1. `extraccion_limpieza.py`
2. `comparar_carrito.py`, si quieres analizar un carrito manual
3. `cba_builder.py`, si quieres construir la CBA detectada desde el consolidado
4. `cba_ahorro_supermercado.py`, si ya corriste `cba_builder.py`
5. `extraer_cba_desde_pdf.py`, si quieres generar el CSV oficial desde PDF
6. `cba_escenario_economico.py` y/o `cba_escenario_premium.py`, si ya tienes consolidado y CSV oficial CBA

---

## Scripts principales

### 1. `extraccion_limpieza.py`

Consolida los datos de Jumbo, Unimarc y Lider.

Qué hace:

- Busca los CSV de cada supermercado.
- Construye categorías normalizadas por supermercado.
- Homologa nombres de columnas.
- Normaliza precios, unidades, marcas, categorías y metadata.
- Genera un consolidado único.
- Ejecuta matching de productos equivalentes.
- Exporta reportes derivados.

Ejecutar:

```powershell
python extraccion_limpieza.py
```

Salidas:

```text
Supermercados/Comparacion/src/output/consolidado/
├── supermercados_consolidado_YYYYMMDD_HHMMSS.csv
├── productos_matches_YYYYMMDD_HHMMSS.csv
├── productos_grouped_YYYYMMDD_HHMMSS.csv
├── productos_group_detail_YYYYMMDD_HHMMSS.csv
└── productos_baratos_YYYYMMDD_HHMMSS.csv
```

Archivo más importante:

```text
supermercados_consolidado_YYYYMMDD_HHMMSS.csv
```

Este archivo es la base para los demás análisis.

---

### 2. `comparar_carrito.py`

Compara un carrito definido manualmente contra el consolidado.

Antes de ejecutarlo, edita:

```text
carrito.txt
```

Ejecutar:

```powershell
python comparar_carrito.py
```

Entrada principal:

```text
Supermercados/Comparacion/src/output/consolidado/supermercados_consolidado_*.csv
```

El script toma automáticamente el consolidado más reciente.

Salidas:

```text
Supermercados/Comparacion/src/output/carrito_comparado/
├── carrito_candidatos.csv
├── carrito_mejor_por_supermercado.csv
├── carrito_resumen_ejecutivo.csv
└── carrito_totales_ejecutivos.csv
```

Uso de cada salida:

- `carrito_candidatos.csv`: posibles productos encontrados para cada ítem del carrito.
- `carrito_mejor_por_supermercado.csv`: mejor candidato por supermercado.
- `carrito_resumen_ejecutivo.csv`: comparación resumida por producto.
- `carrito_totales_ejecutivos.csv`: totales generales del carrito y ahorro estimado.

---

### 3. `cba_builder.py`

Construye una aproximación de la Canasta Básica de Alimentos usando el consolidado de supermercados.

Ejecutar usando el consolidado más reciente:

```powershell
python cba_builder.py
```

Ejecutar indicando un consolidado específico:

```powershell
python cba_builder.py --input_csv "..\output\consolidado\supermercados_consolidado_YYYYMMDD_HHMMSS.csv"
```

Entrada principal:

```text
Supermercados/Comparacion/src/output/consolidado/supermercados_consolidado_*.csv
```

Salidas:

```text
Supermercados/Comparacion/src/output/cba/
├── cba_item_matches.csv
├── cba_resumen_supermercado.csv
├── cba_canasta_optima.csv
└── cba_cobertura.csv
```

Uso de cada salida:

- `cba_item_matches.csv`: candidatos detectados por ítem CBA.
- `cba_resumen_supermercado.csv`: costo estimado de CBA por supermercado.
- `cba_canasta_optima.csv`: selección más conveniente mezclando supermercados.
- `cba_cobertura.csv`: cobertura de ítems detectados versus faltantes.

---

### 4. `cba_ahorro_supermercado.py`

Construye vistas de ahorro por supermercado a partir de las salidas de `cba_builder.py`.

Ejecutar:

```powershell
python cba_ahorro_supermercado.py
```

Ejecutar indicando archivos específicos:

```powershell
python cba_ahorro_supermercado.py --resumen_csv "..\output\cba\cba_resumen_supermercado.csv" --optima_csv "..\output\cba\cba_canasta_optima.csv"
```

Entradas:

```text
Supermercados/Comparacion/src/output/cba/cba_resumen_supermercado.csv
Supermercados/Comparacion/src/output/cba/cba_canasta_optima.csv
```

Salidas:

```text
Supermercados/Comparacion/src/output/cba/ahorro/
├── cba_ranking_supermercados.csv
├── cba_ahorro_supermercado.csv
└── cba_resumen_ejecutivo.csv
```

---

### 5. `extraer_cba_desde_pdf.py`

Extrae la tabla oficial de CBA desde un PDF.

Ejecutar:

```powershell
python extraer_cba_desde_pdf.py
```

Entrada:

```text
Supermercados/CBA/Valor_CBA_y_LPs_25.12.pdf
```

Salida:

```text
Supermercados/Comparacion/src/output/out_cba/cba_anexo1_diciembre2025.csv
```

Columnas generadas:

- `Alimento`
- `Unidad`
- `Cantidad_dia`
- `Calorias_dia`
- `Valor_mensual`

---

### 6. `cba_escenario_economico.py`

Construye un escenario económico de CBA.

Criterio general:

- Prioriza precio bajo (`list_price`/precio disponible).
- Usa oferta y precio por unidad como información complementaria.
- Busca cubrir los productos de la CBA con alternativas económicas.

Ejecutar:

```powershell
python cba_escenario_economico.py
```

Ejecutar indicando consolidado:

```powershell
python cba_escenario_economico.py --input_csv "..\output\consolidado\supermercados_consolidado_YYYYMMDD_HHMMSS.csv"
```

Entradas:

```text
Supermercados/Comparacion/src/output/consolidado/supermercados_consolidado_*.csv
Supermercados/Comparacion/src/output/out_cba/cba_anexo1_diciembre2025.csv
```

Salidas:

```text
Supermercados/Comparacion/src/output/cba_escenario1_economico/
├── cba_econ_candidatos.csv
├── cba_econ_mejor_por_supermercado.csv
├── cba_econ_resumen_final.csv
└── cba_econ_total_por_supermercado.csv
```

---

### 7. `cba_escenario_premium.py`

Construye un escenario premium de CBA.

Criterio general:

- Prioriza mejor match de producto.
- Considera señales de marca/calidad.
- Luego compara precio dentro de los mejores candidatos.

Ejecutar:

```powershell
python cba_escenario_premium.py
```

Ejecutar indicando consolidado:

```powershell
python cba_escenario_premium.py --input_csv "..\output\consolidado\supermercados_consolidado_YYYYMMDD_HHMMSS.csv"
```

Entradas:

```text
Supermercados/Comparacion/src/output/consolidado/supermercados_consolidado_*.csv
Supermercados/Comparacion/src/output/out_cba/cba_anexo1_diciembre2025.csv
```

Salidas:

```text
Supermercados/Comparacion/src/output/cba_escenario_premium/
├── cba_premium_candidatos.csv
├── cba_premium_mejor_por_supermercado.csv
├── cba_premium_resumen_final.csv
└── cba_premium_total_por_supermercado.csv
```

---

## Scripts auxiliares

Estos archivos normalmente no se ejecutan directamente. Son módulos de apoyo usados por los scripts principales.

### `config.py`

Define:

- Columnas estándar (`STANDARD_COLS`)
- Expresión regular para timestamps (`TS_RE`)
- Clase `MarketConfig`

### `pipeline.py`

Contiene funciones comunes para:

- Buscar CSV por carpeta/categoría.
- Consolidar archivos por supermercado.
- Exportar resultados con timestamp.

### `readers.py`

Funciones de lectura robusta de CSV, considerando distintos separadores y codificaciones.

### `builders.py`

Construye o adapta categorías específicas por supermercado.

### `normalizers.py`

Normaliza columnas comunes al formato estándar definido en `config.py`.

### `product_matcher.py`

Ejecuta matching de productos entre supermercados usando limpieza de texto, agrupación y similitud.

### `utils.py`

Funciones utilitarias, principalmente relacionadas con timestamps.

---

## Columnas estándar del consolidado

El consolidado intenta dejar los productos con esta estructura común:

```text
sku
name
brand
price
list_price
discount_price
in_offer
net_content
unit
price_per_unit
price_per_unit_list
saving_text
image_url
detail_url
category
subcategory
last_category
category_url
page_num
extracted_at
supermarket
archivo
ruta_archivo
timestamp_archivo
mtime_archivo
category_std
```

---

## Carpeta de salidas

Todas las salidas analíticas quedan bajo:

```text
Supermercados/Comparacion/src/output/
```

Resumen:

```text
src/output/consolidado/
```

Contiene el consolidado y reportes derivados del matching.

```text
src/output/carrito_comparado/
```

Contiene la comparación del carrito manual.

```text
src/output/cba/
```

Contiene la CBA construida desde el consolidado.

```text
src/output/cba/ahorro/
```

Contiene rankings y análisis de ahorro por supermercado.

```text
src/output/out_cba/
```

Contiene la CBA oficial extraída desde PDF.

```text
src/output/cba_escenario1_economico/
```

Contiene el escenario económico.

```text
src/output/cba_escenario_premium/
```

Contiene el escenario premium.

---

## Ejecución completa sugerida

Desde:

```powershell
cd "Supermercados\Comparacion\src\extraccion_limpieza"
```

Ejecutar:

```powershell
python extraccion_limpieza.py
python comparar_carrito.py
python cba_builder.py
python cba_ahorro_supermercado.py
python extraer_cba_desde_pdf.py
python cba_escenario_economico.py
python cba_escenario_premium.py
```

Si solo necesitas el consolidado:

```powershell
python extraccion_limpieza.py
```

Si solo quieres comparar un carrito:

```powershell
python extraccion_limpieza.py
python comparar_carrito.py
```

Si solo quieres análisis CBA:

```powershell
python extraccion_limpieza.py
python cba_builder.py
python cba_ahorro_supermercado.py
```

Si quieres escenarios económico/premium con CBA oficial:

```powershell
python extraccion_limpieza.py
python extraer_cba_desde_pdf.py
python cba_escenario_economico.py
python cba_escenario_premium.py
```

---

## Formato de exportación

Los CSV se exportan generalmente con:

- Separador `;`
- Codificación `utf-8-sig`

Esto facilita abrirlos en Excel sin perder tildes ni caracteres especiales.

Los archivos generados por `extraccion_limpieza.py` incluyen timestamp:

```text
nombre_YYYYMMDD_HHMMSS.csv
```

Los análisis posteriores suelen sobrescribir archivos con nombre fijo dentro de su carpeta de salida.

---

## Problemas comunes

### No encuentra `supermercados_consolidado*.csv`

Ejecuta primero:

```powershell
python extraccion_limpieza.py
```

Verifica que exista un archivo en:

```text
Supermercados/Comparacion/src/output/consolidado/
```

### No encuentra `carrito.txt`

Debe existir en:

```text
Supermercados/Comparacion/src/extraccion_limpieza/carrito.txt
```

### No encuentra el PDF de CBA

Debe existir:

```text
Supermercados/CBA/Valor_CBA_y_LPs_25.12.pdf
```

Si el PDF cambia de nombre, modifica `PDF_PATH` en:

```text
extraer_cba_desde_pdf.py
```

### El PDF extrae cero filas

Revisar:

- Que el PDF sea el esperado.
- Que las páginas configuradas en `TARGET_PAGES` sean correctas.
- Que la tabla del PDF mantenga una estructura parecida.

### Problemas con tildes o caracteres raros

El proyecto incluye funciones para corregir mojibake en algunos scripts. Aun así, si un CSV de origen viene con codificación extraña, revisar:

- `readers.py`
- Funciones `load_csv_robust`
- Funciones `fix_mojibake_text` / `fix_mojibake_df`

---

## Notas de mantenimiento

Si se agrega un nuevo supermercado, normalmente hay que tocar:

1. `extraccion_limpieza.py`
2. `config.py`
3. `builders.py`
4. `normalizers.py`
5. Eventualmente `product_matcher.py`, si requiere reglas especiales

Si cambia la ruta del consolidado, revisar consumidores:

- `comparar_carrito.py`
- `cba_builder.py`
- `cba_escenario_economico.py`
- `cba_escenario_premium.py`

Actualmente el consolidado se guarda y se busca en:

```text
Supermercados/Comparacion/src/output/consolidado/
```

---

## Estado actual del flujo

El proyecto ya cuenta con:

- Consolidación multi-supermercado.
- Normalización de columnas.
- Matching de productos equivalentes.
- Comparación de carrito manual.
- Construcción de CBA desde consolidado.
- Ranking y ahorro por supermercado.
- Extracción de CBA oficial desde PDF.
- Escenario económico.
- Escenario premium.

