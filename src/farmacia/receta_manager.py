# src/farmacia/receta_manager.py
import json
import os
import uuid
from datetime import datetime, timedelta
from src.tenant import data_path

_instancia = None


class RecetaManager:
    """
    Gestiona el CRUD de recetas en recetas.json.
    Singleton — se carga una vez y se reutiliza.
    """

    def __new__(cls):
        global _instancia
        if _instancia is None:
            _instancia = super().__new__(cls)
        return _instancia

    def __init__(self):
        if not hasattr(self, 'data'):
            self.PATH = data_path("farmacia", "recetas.json")
            self.CONFIG_PATH = data_path("farmacia", "farmacia_config.json")
            self.data = self._cargar_archivo()
            self.config = self._cargar_config()

    # ── PERSISTENCIA ──────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        if not os.path.exists(self.PATH):
            estructura = {"recetas": {}}
            os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(estructura, f, indent=2, ensure_ascii=False)
            return estructura
        with open(self.PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _cargar_config(self):
        if not os.path.exists(self.CONFIG_PATH):
            return {"recetas": {"dias_vencimiento": 30}}
        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _guardar_archivo(self):
        with open(self.PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ── CREAR ─────────────────────────────────────────────────────────────────

    def crear_receta(self, persona_id, obra_social_id, fecha_validez_desde,
                     medico, diagnostico, items, operador_id, fecha_creacion="",
                     credencial_validada=False, receta_url=None):
        """
        Crea una receta nueva con sus items.
        items: [{ medicamento_id, cantidad, cantidad_solicitada, estado_item }]
        Calcula fecha_vencimiento automáticamente.
        credencial_validada: True si la credencial de OS coincide con los registros.
        receta_url: URL del archivo original guardado en storage (None si no aplica).
        Retorna receta_id.
        """
        dias_venc = self.config.get("recetas", {}).get("dias_vencimiento", 30)

        try:
            f_validez = datetime.strptime(fecha_validez_desde, "%d/%m/%Y")
        except ValueError:
            f_validez = datetime.now()

        f_vencimiento = f_validez + timedelta(days=dias_venc)

        receta_id = str(uuid.uuid4())
        self.data["recetas"][receta_id] = {
            "persona_id": persona_id,
            "obra_social_id": obra_social_id,
            "credencial_validada": credencial_validada,
            "fecha_creacion": fecha_creacion,
            "fecha_validez_desde": fecha_validez_desde,
            "fecha_vencimiento": f_vencimiento.strftime("%d/%m/%Y"),
            "medico": medico,
            "diagnostico": diagnostico,
            "items": items,
            "estado": "pendiente",
            "operador_id": operador_id,
            "receta_url": receta_url,
            "notas": [],
            "chat": [],
            "historial_estados": [
                {
                    "estado": "pendiente",
                    "timestamp": datetime.now().isoformat(),
                    "motivo": "Receta cargada por usuario"
                }
            ]
        }
        self._guardar_archivo()
        return receta_id

    # ── BUSCAR ────────────────────────────────────────────────────────────────

    def get_receta(self, receta_id):
        """Retorna (receta_id, datos) o None."""
        datos = self.data["recetas"].get(receta_id)
        if datos:
            return (receta_id, datos)
        return None

    def buscar_por_persona(self, persona_id, estado=None):
        """
        Retorna recetas de una persona, opcionalmente filtradas por estado.
        """
        resultado = []
        for rid, datos in self.data["recetas"].items():
            if datos["persona_id"] == persona_id:
                if estado is None or datos["estado"] == estado:
                    resultado.append({"receta_id": rid, **datos})
        return sorted(resultado, key=lambda x: x.get("fecha_validez_desde", ""), reverse=True)

    def buscar_pendientes(self):
        """Retorna recetas no finales (para la farmacia). Excluye cerrada."""
        estados_config = self._get_estados_receta()
        resultado = []
        for rid, datos in self.data["recetas"].items():
            estado = datos.get("estado", "pendiente")
            config = estados_config.get(estado, {})
            if not config.get("es_final", False):
                resultado.append({"receta_id": rid, **datos})
        return sorted(resultado, key=lambda x: x.get("fecha_validez_desde", ""))

    # ── ESTADOS ───────────────────────────────────────────────────────────────

    def _get_estados_receta(self):
        """Retorna los estados de receta desde la config."""
        return self.config.get("recetas", {}).get("estados_receta", {})

    def _get_estados_item(self):
        """Retorna los estados de items desde la config."""
        return self.config.get("recetas", {}).get("estados_item", {})

    def get_estado_config(self, estado_id):
        """Retorna la config de un estado de receta (label, icono, outflow, etc.)."""
        return self._get_estados_receta().get(estado_id, {})

    def get_outflow(self, estado_id):
        """Retorna los estados a los que puede transicionar desde el estado actual."""
        config = self.get_estado_config(estado_id)
        return config.get("outflow", [])

    def get_inflow(self, estado_id):
        """Retorna los estados desde los que se puede llegar al estado actual."""
        config = self.get_estado_config(estado_id)
        return config.get("inflow", [])

    def cambiar_estado(self, receta_id, nuevo_estado, motivo=""):
        """Cambia el estado de la receta y registra en historial."""
        if receta_id not in self.data["recetas"]:
            return False

        estados_validos = list(self._get_estados_receta().keys())
        if nuevo_estado not in estados_validos:
            return False

        receta = self.data["recetas"][receta_id]
        receta["estado"] = nuevo_estado
        receta["historial_estados"].append({
            "estado": nuevo_estado,
            "timestamp": datetime.now().isoformat(),
            "motivo": motivo
        })
        self._guardar_archivo()
        return True

    def cambiar_estado_item(self, receta_id, item_index, nuevo_estado, alternativa_id=None):
        """Cambia el estado de un item específico de la receta."""
        if receta_id not in self.data["recetas"]:
            return False

        receta = self.data["recetas"][receta_id]
        if item_index < 0 or item_index >= len(receta["items"]):
            return False

        estados_validos = list(self._get_estados_item().keys())
        if nuevo_estado not in estados_validos:
            return False

        receta["items"][item_index]["estado_item"] = nuevo_estado
        if alternativa_id:
            receta["items"][item_index]["alternativa_medicamento_id"] = alternativa_id

        self._guardar_archivo()
        return True

    # ── NOTAS ─────────────────────────────────────────────────────────────────

    def agregar_nota(self, receta_id, autor, dirigida_a, mensaje):
        """Agrega una nota a la receta. Retorna el id de la nota."""
        if receta_id not in self.data["recetas"]:
            return None

        nota_id = str(uuid.uuid4())[:8]
        nota = {
            "id": nota_id,
            "autor": autor,
            "dirigida_a": dirigida_a,
            "mensaje": mensaje,
            "timestamp": datetime.now().isoformat(),
            "estado": "pendiente"
        }
        self.data["recetas"][receta_id]["notas"].append(nota)
        self._guardar_archivo()
        return nota_id

    def responder_nota(self, receta_id, nota_id, respuesta):
        """Marca una nota como respondida."""
        if receta_id not in self.data["recetas"]:
            return False

        for nota in self.data["recetas"][receta_id]["notas"]:
            if nota["id"] == nota_id:
                nota["estado"] = "respondida"
                nota["respuesta"] = respuesta
                nota["timestamp_respuesta"] = datetime.now().isoformat()
                self._guardar_archivo()
                return True
        return False

    def get_notas_pendientes(self, receta_id, dirigida_a):
        """Retorna notas pendientes dirigidas a un destinatario."""
        if receta_id not in self.data["recetas"]:
            return []
        return [
            n for n in self.data["recetas"][receta_id]["notas"]
            if n["estado"] == "pendiente" and n["dirigida_a"] == dirigida_a
        ]

    def contar_notificaciones_usuario(self, persona_id):
        """Cuenta total de notas pendientes dirigidas al usuario en todas sus recetas activas."""
        total = 0
        for rid, datos in self.data["recetas"].items():
            if datos["persona_id"] == persona_id:
                notas = [
                    n for n in datos.get("notas", [])
                    if n["estado"] == "pendiente" and n["dirigida_a"] == "usuario"
                ]
                total += len(notas)
        return total

    def get_primera_notificacion_usuario(self, persona_id):
        """
        Retorna la primera nota pendiente dirigida al usuario (orden cronológico).
        Retorna (receta_id, nota) o None.
        """
        for rid, datos in self.data["recetas"].items():
            if datos["persona_id"] == persona_id:
                for nota in datos.get("notas", []):
                    if nota["estado"] == "pendiente" and nota["dirigida_a"] == "usuario":
                        return (rid, nota)
        return None

    def buscar_recetas_activas(self, persona_id):
        """Retorna recetas activas (no finales) de una persona."""
        estados_config = self._get_estados_receta()
        resultado = []
        for rid, datos in self.data["recetas"].items():
            if datos["persona_id"] == persona_id:
                estado = datos.get("estado", "pendiente")
                config_e = estados_config.get(estado, {})
                if not config_e.get("es_final", False):
                    resultado.append({"receta_id": rid, **datos})
        return sorted(resultado, key=lambda x: x.get("fecha_vencimiento", ""))

    def marcar_nota_leida(self, receta_id, nota_id):
        """Marca una nota como leída (informativa, sin respuesta)."""
        if receta_id not in self.data["recetas"]:
            return False
        for nota in self.data["recetas"][receta_id]["notas"]:
            if nota["id"] == nota_id:
                nota["estado"] = "leida"
                nota["timestamp_leida"] = datetime.now().isoformat()
                self._guardar_archivo()
                return True
        return False

    def desestimar_todas_notas(self, receta_id):
        """Desestima todas las notas pendientes de la receta (ambas direcciones)."""
        if receta_id not in self.data["recetas"]:
            return
        for nota in self.data["recetas"][receta_id]["notas"]:
            if nota["estado"] == "pendiente":
                nota["estado"] = "respondida"
                nota["respuesta"] = "Desestimada automáticamente por retroceso de estado."
                nota["timestamp_respuesta"] = datetime.now().isoformat()
        self._guardar_archivo()

    def reset_items(self, receta_id, estado_item="pendiente"):
        """Resetea todos los items no omitidos al estado dado."""
        if receta_id not in self.data["recetas"]:
            return
        for item in self.data["recetas"][receta_id]["items"]:
            if item["estado_item"] != "omitido_usuario":
                item["estado_item"] = estado_item
        self._guardar_archivo()

    # ── CHAT ──────────────────────────────────────────────────────────────────

    def agregar_mensaje_chat(self, receta_id, autor, mensaje, tipo="mensaje", medicamento_id=None):
        """Agrega un mensaje al hilo de chat de la receta. Retorna el id del mensaje."""
        if receta_id not in self.data["recetas"]:
            return None
        receta = self.data["recetas"][receta_id]
        if "chat" not in receta:
            receta["chat"] = []
        msg_id = str(uuid.uuid4())[:8]
        msg = {
            "id": msg_id,
            "autor": autor,
            "tipo": tipo,
            "mensaje": mensaje,
            "timestamp": datetime.now().isoformat(),
            "leido_por": [autor]
        }
        if medicamento_id is not None:
            msg["medicamento_id"] = medicamento_id
        receta["chat"].append(msg)
        self._guardar_archivo()
        return msg_id

    def get_chat(self, receta_id):
        """Retorna el hilo de chat completo de la receta."""
        receta = self.data["recetas"].get(receta_id)
        if not receta:
            return []
        return receta.get("chat", [])

    def marcar_mensaje_leido(self, receta_id, msg_id, lector):
        """Marca un mensaje específico del chat como leído por lector."""
        receta = self.data["recetas"].get(receta_id)
        if not receta:
            return
        for msg in receta.get("chat", []):
            if msg["id"] == msg_id and lector not in msg["leido_por"]:
                msg["leido_por"].append(lector)
                self._guardar_archivo()
                return

    def marcar_chat_leido(self, receta_id, lector):
        """Marca como leídos por lector todos los mensajes que no escribió él mismo."""
        if receta_id not in self.data["recetas"]:
            return
        receta = self.data["recetas"][receta_id]
        changed = False
        for msg in receta.get("chat", []):
            if msg["autor"] != lector and lector not in msg["leido_por"]:
                msg["leido_por"].append(lector)
                changed = True
        if changed:
            self._guardar_archivo()

    def contar_no_leidos_chat(self, receta_id, lector):
        """Cuenta mensajes del chat donde lector no está en leido_por."""
        receta = self.data["recetas"].get(receta_id)
        if not receta:
            return 0
        return sum(
            1 for msg in receta.get("chat", [])
            if msg["autor"] != lector and lector not in msg["leido_por"]
        )

    def _get_meds_en_consulta(self, chat):
        """Retorna set de medicamento_ids con consulta activa (sin respuesta_consulta posterior)."""
        meds = set()
        for idx, msg in enumerate(chat):
            if msg.get("tipo") == "consulta":
                med_id = msg.get("medicamento_id")
                if med_id:
                    tiene_respuesta = any(
                        r.get("tipo") == "respuesta_consulta" and r.get("medicamento_id") == med_id
                        for r in chat[idx + 1:]
                    )
                    if not tiene_respuesta:
                        meds.add(med_id)
        return meds

    def _tipos_accion_cliente(self):
        return set(self.config.get("recetas", {}).get("tipos_accion_cliente", []))

    def contar_chat_no_leidos_usuario(self, persona_id):
        """Cuenta acciones pendientes (tipos accionables) no leídas por el usuario."""
        tipos_accion = self._tipos_accion_cliente()
        total = 0
        for rid, datos in self.data["recetas"].items():
            if datos["persona_id"] == persona_id:
                meds_en_consulta = self._get_meds_en_consulta(datos.get("chat", []))
                for msg in datos.get("chat", []):
                    if (msg["autor"] != persona_id
                            and persona_id not in msg["leido_por"]
                            and msg.get("tipo") in tipos_accion):
                        med_id = msg.get("medicamento_id")
                        if med_id and med_id in meds_en_consulta:
                            continue
                        total += 1
        return total

    def get_primer_chat_no_leido_usuario(self, persona_id):
        """
        Retorna (receta_id, msg) del primer mensaje accionable no leído,
        ordenado cronológicamente. Omite mensajes de medicamentos con consulta activa.
        """
        tipos_accion = self._tipos_accion_cliente()
        candidatos = []
        for rid, datos in self.data["recetas"].items():
            if datos["persona_id"] == persona_id:
                meds_en_consulta = self._get_meds_en_consulta(datos.get("chat", []))
                for msg in datos.get("chat", []):
                    if (msg["autor"] != persona_id
                            and persona_id not in msg["leido_por"]
                            and msg.get("tipo") in tipos_accion):
                        med_id = msg.get("medicamento_id")
                        if med_id and med_id in meds_en_consulta:
                            continue
                        candidatos.append((msg["timestamp"], rid, msg))
        if not candidatos:
            return None
        candidatos.sort(key=lambda x: x[0])
        _, rid, msg = candidatos[0]
        return (rid, msg)

    def contar_mensajes_no_leidos_usuario(self, persona_id):
        """Cuenta mensajes tipo 'mensaje' de farmacia no leídos — aparecen en Chat."""
        total = 0
        for rid, datos in self.data["recetas"].items():
            if datos["persona_id"] == persona_id:
                for msg in datos.get("chat", []):
                    if (msg["autor"] != persona_id
                            and persona_id not in msg["leido_por"]
                            and msg.get("tipo") == "mensaje"):
                        total += 1
        return total

    def migrar_notas_a_chat(self, receta_id):
        """
        Convierte las notas existentes de una receta al modelo chat.
        Idempotente: no migra si ya hay mensajes en chat o no hay notas.
        """
        if receta_id not in self.data["recetas"]:
            return
        receta = self.data["recetas"][receta_id]
        if "chat" not in receta:
            receta["chat"] = []
        if receta["chat"] or not receta.get("notas"):
            return
        for nota in receta["notas"]:
            autor = nota.get("autor", "farmacia")
            msg = {
                "id": nota.get("id", str(uuid.uuid4())[:8]),
                "autor": autor,
                "tipo": self._inferir_tipo_nota(nota.get("mensaje", ""), autor),
                "mensaje": nota.get("mensaje", ""),
                "timestamp": nota.get("timestamp", datetime.now().isoformat()),
                "leido_por": [autor]
            }
            if nota.get("estado") in ("respondida", "leida"):
                dirigida_a = nota.get("dirigida_a", "")
                if dirigida_a and dirigida_a not in msg["leido_por"]:
                    msg["leido_por"].append(dirigida_a)
            receta["chat"].append(msg)
        self._guardar_archivo()

    def _inferir_tipo_nota(self, mensaje, autor):
        """Infiere el tipo de chat a partir del contenido de una nota migrada."""
        if autor != "farmacia":
            return "accion"
        msg_lower = mensaje.lower()
        if "alternativa" in msg_lower:
            return "alternativa"
        if "stock" in msg_lower or "no tenemos" in msg_lower:
            return "sin_stock"
        if "token" in msg_lower:
            return "solicitud_token"
        return "mensaje"

    # ── VENCIMIENTO ───────────────────────────────────────────────────────────

    def esta_vencida(self, receta_id):
        """Verifica si la receta está vencida."""
        receta = self.data["recetas"].get(receta_id)
        if not receta:
            return True
        try:
            f_venc = datetime.strptime(receta["fecha_vencimiento"], "%d/%m/%Y")
            return datetime.now() > f_venc
        except ValueError:
            return True

    def dias_para_vencer(self, receta_id):
        """Retorna los días restantes para el vencimiento, o -1 si ya venció."""
        receta = self.data["recetas"].get(receta_id)
        if not receta:
            return -1
        try:
            f_venc = datetime.strptime(receta["fecha_vencimiento"], "%d/%m/%Y")
            delta = (f_venc - datetime.now()).days
            return delta if delta >= 0 else -1
        except ValueError:
            return -1