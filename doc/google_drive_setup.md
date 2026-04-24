# Configuración Google Drive — file_services

## Estado actual

| Componente | Estado |
|---|---|
| Google Cloud Project | ✅ `agentia-492602` |
| Google Drive API | ✅ Habilitada |
| Service Account | ✅ Creada |
| Credenciales JSON | ✅ En `credentials/service_account.json` |
| Proveedor activo | ⏳ `local` (Drive pendiente, ver sección "Activar Drive") |

---

## Lo que se configuró

### Google Cloud Console

- **Proyecto**: `AgentIA` (`agentia-492602`)
- **API habilitada**: Google Drive API
- **Service Account**: `agentia-drive@agentia-492602.iam.gserviceaccount.com`
- **Credenciales**: descargadas como JSON, guardadas en `credentials/service_account.json`

> `credentials/` está en `.gitignore` — el archivo nunca se sube al repositorio.

### Variables de entorno (`.env`)

```
GOOGLE_DRIVE_CREDENTIALS_PATH=credentials/service_account.json
GOOGLE_DRIVE_FOLDER_ID=1g0Fpa2pzHE7Hktu_crzSbTpWlRdtYW3J
```

> `GOOGLE_DRIVE_FOLDER_ID` apunta a la carpeta `recetas` creada en Google Drive personal.

### Config del módulo (`data/file_services_config.json`)

```json
{
  "proveedores": {
    "drive_principal": {
      "tipo": "google_drive",
      "env_credentials": "GOOGLE_DRIVE_CREDENTIALS_PATH",
      "env_folder_id": "GOOGLE_DRIVE_FOLDER_ID"
    },
    "local": {
      "tipo": "local",
      "base_path": "data/archivos"
    }
  },
  "storage": {
    "proveedor_defecto": "local",
    "proyectos": {
      "farmacia": {
        "proveedor": "local",
        "carpeta": "recetas"
      }
    }
  }
}
```

Para activar Drive en farmacia: cambiar `"proveedor": "local"` → `"proveedor": "drive_principal"` en el bloque de farmacia.

---

## Por qué Drive no está activo todavía

Las Service Accounts no tienen cuota de almacenamiento propia en Google Drive. Para subir archivos necesitan una de estas dos condiciones:

- **Shared Drive** (Unidad compartida): requiere Google Workspace (cuenta de pago). ❌ No disponible en cuenta gratuita.
- **OAuth2 con refresh token**: el usuario autoriza una vez desde el navegador, el token se guarda y la app lo reutiliza. ✅ Funciona con cuenta gratuita.

---

## Activar Drive — pasos pendientes (OAuth2)

Cuando se decida activar Google Drive, el proceso es:

### 1. Crear credencial OAuth2 en Google Cloud Console

1. **APIs y servicios** → **Credenciales** → **+ Crear credenciales** → **ID de cliente OAuth**
2. Tipo: **Aplicación de escritorio**
3. Nombre: `agentia-oauth-drive`
4. Descargar el JSON → guardarlo en `credentials/oauth_client.json`

### 2. Ejecutar autorización inicial (una sola vez)

Crear y correr un script de autorización que abra el navegador, el usuario acepta, y el refresh token se guarda en `credentials/oauth_token.json`.

### 3. Actualizar `GoogleDriveProvider`

Adaptar el provider para usar `oauth_token.json` en lugar de `service_account.json`.

### 4. Actualizar la config

```json
"drive_principal": {
  "tipo": "google_drive_oauth",
  "env_client_secrets": "GOOGLE_DRIVE_CLIENT_SECRETS_PATH",
  "env_token": "GOOGLE_DRIVE_TOKEN_PATH",
  "env_folder_id": "GOOGLE_DRIVE_FOLDER_ID"
}
```

### 5. Agregar nuevas variables al `.env`

```
GOOGLE_DRIVE_CLIENT_SECRETS_PATH=credentials/oauth_client.json
GOOGLE_DRIVE_TOKEN_PATH=credentials/oauth_token.json
```

---

## Arquitectura multi-tenant (futuro)

En la refactorización multi-tenant cada cliente tendrá su propia copia de `file_services_config.json` bajo `data/{tenant_id}/`. El módulo `file_services` no requiere cambios — solo se parametriza el path del config por tenant.

Cada cliente puede usar un proveedor diferente:
- Cliente 1: `"proveedor": "drive_principal"` con su propio folder ID
- Cliente 2: `"proveedor": "local"` o un Drive distinto

---

## Dependencias instaladas

```bash
pip install pymupdf
pip install google-api-python-client google-auth
pip install python-dotenv
```
