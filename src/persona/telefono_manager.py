# src/cliente/telefono_manager.py
import phonenumbers
from phonenumbers import PhoneNumberFormat


def parse_e164(texto, pais="AR"):
    """Parsea un número telefónico y retorna E.164 o None si es inválido."""
    try:
        num = phonenumbers.parse(texto, pais)
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def format_display(e164_o_texto, pais="AR"):
    """Formatea un número para mostrar al usuario (ej: +54 11 5555-7777 (AR))."""
    try:
        num = phonenumbers.parse(e164_o_texto, pais)
        formatted = phonenumbers.format_number(num, PhoneNumberFormat.INTERNATIONAL)
        region = phonenumbers.region_code_for_number(num)
        return f"{formatted} ({region})"
    except Exception:
        return e164_o_texto
