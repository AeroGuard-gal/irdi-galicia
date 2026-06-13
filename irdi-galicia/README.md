# IRDI Galicia · Risco diario de incendios

Sistema que extrae cada día o IRDI de Medio Rural, crúzao coa capa municipal e publica un mapa web con 4 días de predición. Actualízase só mediante GitHub Actions (gratuíto).

---

## Como poñelo en marcha

### Paso 1 · Crear o repositorio en GitHub

1. Vai a [github.com](https://github.com) e inicia sesión.
2. Preme o botón verde **"New"** (esquina superior esquerda) ou vai a `github.com/new`.
3. Enche o formulario:
   - **Repository name:** `irdi-galicia`
   - **Visibility:** marca **Public** (obrigatorio para GitHub Pages gratuíto)
   - **NON marques** "Add a README file" nin ningunha outra opción
4. Preme **"Create repository"**.

---

### Paso 2 · Subir os ficheiros

Ao crear o repositorio baleiro verás unha páxina con instrucións. Ignóraa e fai isto:

1. Preme o botón **"uploading an existing file"** (ligazón en letra pequena na páxina) ou vai directamente a:
   `https://github.com/TEU-USUARIO/irdi-galicia/upload/main`

2. **Descomprime** o ficheiro `irdi-galicia.zip` no teu ordenador. Verás estes ficheiros e cartafoles:
   ```
   index.html
   README.md
   .gitignore
   data/
     irdi_dia_1.geojson
     irdi_dia_2.geojson
     irdi_dia_3.geojson
     irdi_dia_4.geojson
     irdi_meta.json
   scripts/
     actualizar_irdi.py
     preparar_concellos.py
   .github/
     workflows/
       actualizar-irdi.yml
   ```

3. **Arrastra TODOS estes ficheiros e cartafoles** á zona de subida de GitHub (a caixa grande que di "Drag files here").
   - ⚠️ **Importante:** a carpeta `.github` pode estar oculta no teu ordenador (comeza por punto). En Mac preme `Cmd+Shift+.` para ver os ficheiros ocultos. En Windows activa "Mostrar ficheiros ocultos" no Explorador.

4. Abaixo do todo, en "Commit changes", deixa o texto por defecto e preme **"Commit changes"**.

5. Agarda 10-15 segundos e recarga a páxina. Deberías ver os ficheiros no repositorio.

---

### Paso 3 · Activar GitHub Pages

GitHub Pages publica o teu `index.html` como páxina web gratuíta.

1. No repositorio, preme a pestana **"Settings"** (última pestana da fila superior, ten icona de engrenaxe).

2. No menú da esquerda, busca a sección **"Code and automation"** e preme **"Pages"**.

3. Verás "Build and deployment". En **"Source"** hai un despregable que di `Deploy from a branch`. **Non o cambies**, déixao así.

4. En **"Branch"** hai dous despregables:
   - Primeiro (a rama): cámbialo de `None` a **`main`**
   - Segundo (o cartafol): déixao en **`/ (root)`**

5. Preme **"Save"**.

6. Aparecerá un aviso azul: *"GitHub Pages source saved"*. Agarda 2-3 minutos.

7. Recarga a páxina de Settings → Pages. Aparecerá unha caixa verde con:
   ```
   Your site is live at https://TEU-USUARIO.github.io/irdi-galicia/
   ```
   Apunta esa URL, a necesitarás no paso 6.

8. **Verifica:** preme a ligazón. Deberías ver o mapa do IRDI con datos de exemplo (unos poucos concellos en cores aleatorias). Se sae, GitHub Pages funciona correctamente.

---

### Paso 4 · Activar as Actions (automatización diaria)

1. No repositorio, preme a pestana **"Actions"** (na fila de pestanas superiores).

2. É posible que apareza un aviso amarelo: *"Workflows aren't being run on this forked repository"* ou similar, con un botón **"I understand my workflows, go ahead and enable them"**. Preme ese botón.

3. No menú da esquerda verás **"Actualizar IRDI Galicia"**. Preme nel.

4. Á dereita verás o botón **"Run workflow"** con un despregable. Preme nel.

5. Aparecerá un formulario pequeno cunha rama (`main`) e un botón verde **"Run workflow"**. Preme ese botón verde.

6. Recarga a páxina. Verás unha execución nova na lista co estado "queued" (en cola) e logo "in progress" (en execución). Ten un círculo amarelo xirando.

7. Agarda 2-4 minutos. Se todo vai ben, o círculo volverase **verde** ✓. Se é **vermello** ✗, hai un erro — preme nel e cópiame o texto vermello que aparece no rexistro.

8. Cando remate con éxito, vai á pestana **"Code"** e entra na carpeta `data/`. Os ficheiros `irdi_dia_1.geojson` etc. deberían ter a data de hoxe e un tamaño maior (≈200-400 KB en vez dos poucos KB dos datos de exemplo). Iso significa que o scraper obtivo os datos reais dos 313 concellos.

---

### Paso 5 · Verificar o visor

1. Abre de novo a URL de GitHub Pages:
   `https://TEU-USUARIO.github.io/irdi-galicia/`

2. Agarda que cargue o mapa (pode tardar 5-10 segundos a primeira vez, é normal).

3. Deberías ver Galicia con todos os concellos coloreados en verde/amarelo/laranxa/vermello/morado segundo o risco do día.

4. Proba os botóns **Hoxe / Mañá / +2 días / +3 días** — os concellos deben cambiar de cor ao cambialos.

5. Preme sobre calquera concello — debe aparecer un popup con nome e nivel de risco.

Se algo non se ve, recarga con **Ctrl+Shift+R** (forzar caché).

---

### Paso 6 · Conectar co mapa de incendios de VOST

Este paso integra o IRDI no mapa da app de incendios, como capa adicional.

1. Na app de incendios, abre o ficheiro `src/lib/config.js`.

2. Busca esta liña (está preto do principio):
   ```javascript
   export const IRDI_BASE = 'https://aeroguard-gal.github.io/irdi-galicia/data'
   ```

3. Cambia a URL pola túa. Substitúe `aeroguard-gal` polo teu usuario de GitHub:
   ```javascript
   export const IRDI_BASE = 'https://TEU-USUARIO.github.io/irdi-galicia/data'
   ```

4. Garda, sube a GitHub e desprega en Vercel como sempre.

5. Abre a app de incendios. No mapa principal, na lenda (botón "☰ Lenda"), verás a sección **"🔥 Risco IRDI"** con catro botóns de día. Ao premer un, os concellos colórense por risco debaixo dos puntos de incendios activos.

---

### Paso 7 · Automatización verificada (opcional pero recomendado)

Para confirmar que o sistema se actualiza só cada día:

1. No repositorio IRDI, vai a **Actions → Actualizar IRDI Galicia**.
2. Verás o historial de execucións. Cada mañá ás 9:00 (hora peninsular) debería aparecer unha nova entrada verde.
3. Se algunha día sae vermella, avísame e o arranxo — normalmente é que a web da Xunta cambiou algo.

---

## Resumo de URLs

| Cousa | URL |
|---|---|
| Repositorio | `https://github.com/TEU-USUARIO/irdi-galicia` |
| Visor web | `https://TEU-USUARIO.github.io/irdi-galicia/` |
| Datos (GeoJSON) | `https://TEU-USUARIO.github.io/irdi-galicia/data/irdi_dia_1.geojson` |
| Actions | `https://github.com/TEU-USUARIO/irdi-galicia/actions` |

---

## Niveis de risco e cores

| Nivel | Cor |
|---|---|
| Baixo | 🟢 Verde |
| Moderado | 🟡 Amarelo |
| Alto | 🟠 Laranxa |
| Moi alto | 🔴 Vermello |
| Extremo | 🟣 Morado |
| Sen dato | ⚫ Gris |

---

## Atribución obrigatoria

Os datos son de **Medio Rural · Xunta de Galicia**. O visor mostra sempre a atribución. Non eliminar.
