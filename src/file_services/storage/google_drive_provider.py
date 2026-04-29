# src/file_services/storage/google_drive_provider.py
import io
from src.file_services.storage.storage_provider import StorageProvider


class GoogleDriveProvider(StorageProvider):
    """
    Proveedor de almacenamiento en Google Drive.
    Usa service account para autenticación server-to-server (sin login interactivo).
    Requiere: google-api-python-client, google-auth
    """

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]

    def __init__(self, credentials_path: str, folder_id: str):
        self.credentials_path = credentials_path
        self.folder_id = folder_id
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        creds = Credentials.from_service_account_file(
            self.credentials_path, scopes=self.SCOPES
        )
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def _mime_desde_filename(self, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower()
        return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(
            ext, "application/octet-stream"
        )

    def subir(self, contenido: bytes, filename: str, carpeta: str) -> str:
        from googleapiclient.http import MediaIoBaseUpload

        service = self._get_service()
        mimetype = self._mime_desde_filename(filename)

        metadata = {"name": filename, "parents": [self.folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(contenido), mimetype=mimetype, resumable=False)

        archivo = service.files().create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink"
        ).execute()

        return archivo.get("webViewLink", "")
