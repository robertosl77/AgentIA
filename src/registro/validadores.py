# src/cliente/validadores.py
from datetime import datetime, timedelta
import re

class Validadores:
    """
    Clase base de validadores.
    Responsabilidades:
        - Validar tipos de dato base (texto, numero, email, telefono, fecha)
        - Aplicar validadores adicionales configurados en configuracion.json
        - Retornar True si válido, False o msj_error si inválido
    """

    # ── VALIDADORES DE TIPO BASE ──────────────────────────────────────────────

    def valida_texto(self, valor):
        """Valida que el valor no esté vacío y contenga solo letras y espacios."""
        return bool(valor.strip()) and all(c.isalpha() or c.isspace() for c in valor)

    def valida_numero(self, valor):
        """Valida que el valor contenga solo dígitos."""
        return valor.strip().isdigit()

    def valida_email(self, valor):
        """Valida formato básico de email: contiene @ y al menos un punto después."""
        valor = valor.strip()
        return "@" in valor and "." in valor.split("@")[-1]

    def valida_telefono(self, valor):
        """Valida que el valor contenga solo dígitos y tenga al menos 8 caracteres."""
        valor = valor.strip()
        return valor.isdigit() and len(valor) >= 8

    def valida_fecha(self, valor):
        """Valida formato de fecha DD/MM/AAAA."""
        try:
            datetime.strptime(valor.strip(), "%d/%m/%Y")
            return True
        except ValueError:
            return False

    def valida_hora(self, valor):
        """Valida formato de hora HH:MM."""
        try:
            datetime.strptime(valor.strip(), "%H:%M")
            return True
        except ValueError:
            return False

    def valida_fecha_hora(self, valor):
        """[INTERFAZ] Valida formato de fecha y hora DD/MM/AAAA HH:MM."""
        pass

    # ── DISPATCHER PRINCIPAL ──────────────────────────────────────────────────

    def _validar(self, tipo, valor, validadores_campo=[], config_validadores={}):
        """
        Primero valida el tipo base, luego corre los validadores adicionales del JSON.
        Retorna True si todo es válido, False si falla el tipo base,
        o el msj_error del validador adicional que falló.
        """
        # Validación de tipo base
        validadores_tipo = {
            "texto":    self.valida_texto,
            "numero":   self.valida_numero,
            "email":    self.valida_email,
            "telefono": self.valida_telefono,
            "fecha":    self.valida_fecha,
            "hora":     self.valida_hora
        }
        validador_tipo = validadores_tipo.get(tipo)
        if validador_tipo and not validador_tipo(valor):
            return False  # ← fallo de tipo base, usa msj_reintento del campo

        # Validadores adicionales del JSON
        for nombre_validador in validadores_campo:
            config_v = config_validadores.get(nombre_validador, {})
            if not config_v:
                continue
            resultado = self._aplicar_validador(config_v, valor)
            if not resultado:
                return config_v.get("msj_error", "⚠️ Dato inválido. Intentá nuevamente:")

        return True

    # ── VALIDADORES ADICIONALES ───────────────────────────────────────────────

    def _aplicar_validador(self, config_v, valor):
        """Aplica un validador específico según su tipo. Retorna True si pasa."""
        tipo_v = config_v.get("tipo")
        ahora = datetime.now()

        if tipo_v == "fecha_pasada":
            try:
                f = datetime.strptime(valor.strip(), "%d/%m/%Y")
                return f < ahora
            except ValueError:
                return False

        elif tipo_v == "fecha_futura":
            try:
                f = datetime.strptime(valor.strip(), "%d/%m/%Y")
                return f > ahora
            except ValueError:
                return False
            
        elif tipo_v == "fecha_hoy_o_futura":
            try:
                f = datetime.strptime(valor.strip(), "%d/%m/%Y").date()
                return f >= datetime.now().date()
            except ValueError:
                return False            

        elif tipo_v == "edad_minima":
            try:
                f = datetime.strptime(valor.strip(), "%d/%m/%Y")
                edad_dias = config_v.get("edad", 18) * 365
                return (ahora - f).days >= edad_dias
            except ValueError:
                return False

        elif tipo_v == "fecha_limite":
            try:
                f = datetime.strptime(valor.strip(), "%d/%m/%Y")
                dias = config_v.get("dias", 30)
                return ahora < f <= ahora + timedelta(days=dias)
            except ValueError:
                return False

        elif tipo_v == "longitud_maxima":
            return len(valor.strip()) <= config_v.get("parametro", 50)

        elif tipo_v == "longitud_minima":
            return len(valor.strip()) >= config_v.get("parametro", 3)

        elif tipo_v == "email":
            patron = config_v.get("formato", "")
            return bool(re.match(patron, valor.strip()))

        elif tipo_v == "fecha":
            try:
                datetime.strptime(valor.strip(), config_v.get("formato", "%d/%m/%Y"))
                return True
            except ValueError:
                return False
        elif tipo_v == "hora":
            try:
                datetime.strptime(valor.strip(), config_v.get("formato", "%H:%M"))
                return True
            except ValueError:
                return False            

        return True  # tipo desconocido: dejamos pasar