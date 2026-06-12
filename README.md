# IRDI Galicia · Risco diario de incendios

Sistema que extrae a diario o **Índice de Risco Diario de Incendios (IRDI)** de
Medio Rural (Xunta de Galicia), crúzao coa capa municipal dos 313 concellos e
xera ficheiros GeoJSON que se mostran nun mapa web.

Inclúe:

- **Visor independente** (`index.html`): mapa de Galicia cos concellos coloreados
  por risco, con botóns de Hoxe / Mañá / +2 / +3 días.
- **Scraper diario** (`scripts/`): descarga os datos e xera os GeoJSON.
- **Automatización** (GitHub Actions): actualízase só cada mañá.
- **Integración** na app de incendios de VOST (capa "🔥 Risco IRDI" no mapa).

---

## Como poñelo en marcha (paso a paso)

### 1. Crear o repositorio en GitHub

1. Entra en GitHub → **New repository**.
2. Nome suxerido: `irdi-galicia`. Marca **Public** (necesario para GitHub Pages
   de balde).
3. Crea o repositorio baleiro.

### 2. Subir estes ficheiros

Arrastra todo o contido deste cartafol ao repositorio (botón **Add file → Upload
files**), incluíndo as carpetas `scripts/`, `.github/` e `data/`.

### 3. Activar GitHub Pages

1. No repositorio: **Settings → Pages**.
2. En "Source", elixe a rama **main** e o cartafol **/ (root)**.
3. Garda. En 1-2 minutos a web estará en:
   `https://TEU-USUARIO.github.io/irdi-galicia/`

### 4. Activar a automatización diaria

1. No repositorio: pestana **Actions**.
2. Se pide activar os workflows, acéptao.
3. Verás o workflow **"Actualizar IRDI Galicia"**. Podes lanzalo á man co botón
   **Run workflow** para a primeira carga, sen agardar ás 9:00.

### 5. (Opcional) Capa municipal propia

O sistema descarga só unha capa municipal de Galicia a primeira vez. Se prefires
usar a túa propia (exportada de QGIS en **EPSG:4326**, formato GeoJSON), súbea como
`data/concellos_galicia.geojson` substituíndo a existente. Debe ter un campo co
nome do concello (vale `NAMEUNIT`, `nome`, `NOMBRE`…) e, idealmente, o código INE.

---

## Conectar coa app de incendios de VOST

Na app de incendios, o ficheiro `src/lib/config.js` ten esta liña:

```js
export const IRDI_BASE = 'https://aeroguard-gal.github.io/irdi-galicia/data'
```

Cambia esa URL pola da túa GitHub Pages (paso 3) + `/data`. Por exemplo, se o teu
usuario é `vostgalicia`:

```js
export const IRDI_BASE = 'https://vostgalicia.github.io/irdi-galicia/data'
```

Co cambio feito, no mapa da app aparecerá na lenda a sección **"🔥 Risco IRDI"**
cos botóns de día. Ao elixir un día, os concellos colórense por risco debaixo dos
incendios activos.

---

## Como funciona por dentro

```
Web da Xunta (IRDI)
   ↓  scripts/actualizar_irdi.py  (scraping diario)
Táboa concello + risco
   ↓  cruce coa capa municipal (por nome normalizado / código INE)
data/irdi_dia_1..4.geojson
   ↓
Visor propio (index.html)  +  app de incendios de VOST
```

A clave: o scraping faise **no servidor de GitHub unha vez ao día**, non no
navegador. A web só le ficheiros GeoJSON do propio dominio, polo que **non hai
problema de CORS** (que é o que impedía cargar os WMS oficiais directamente).

---

## Niveis de risco e cores

| Nivel      | Valor | Cor        |
|------------|-------|------------|
| Baixo      | 1     | Verde      |
| Moderado   | 2     | Amarelo    |
| Alto       | 3     | Laranxa    |
| Moi alto   | 4     | Vermello   |
| Extremo    | 5     | Morado     |
| Sen dato   | 0     | Gris       |

---

## Atribución

Os datos do IRDI son propiedade de **Medio Rural · Xunta de Galicia**
(https://mediorural.xunta.gal/es/temas/defensa-monte/irdi). Este sistema
limítase a mostralos con fins de protección civil, citando sempre a fonte.

Capa municipal: límites administrativos do IGN / CNIG.
