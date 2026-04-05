# AgentIA — Bot WhatsApp para Negocio/Farmacia
## Contexto del Proyecto para Claude Projects

---

## MÉTODO DE TRABAJO
- Respuestas cortas y al punto
- Preguntar antes de asumir o tirar código innecesario
- Etapas claras: Brainstorm → Análisis → Desarrollo → Pruebas
- No saltamos etapas sin OK del usuario

---

## OBJETIVO GENERAL
Bot de WhatsApp para gestión de una farmacia/negocio. Diseñado como SaaS multi-cliente, modular, escalable y orientado a objetos. Configuración 100% dinámica desde JSON sin tocar código Python.

---

## STACK TECNOLÓGICO
- **Backend:** Python 3.12 / Flask (puerto 5000)
- **Mensajería:** Node.js / WPPConnect (puerto 3000)
- **Datos:** JSON files (sin DB, preparado para migración futura)
- **Repositorio:** GitHub — AgentIA

---

## ARQUITECTURA DE CARPETAS
```
AgentIA/
├── app.py
├── data/
│   ├── configuracion.json    ← config estática (mensajes, validadores, estructura sesión)
│   ├── datos.json            ← datos operativos (horarios, guardias, cierres)
│   ├── sesiones.json         ← sesiones de usuarios
│   └── error_log.json        ← log de errores técnicos
├── src/
│   ├── config_loader.py      ← singleton, lee configuracion.json
│   ├── data_loader.py        ← singleton, lee/escribe datos.json
│   ├── menu_principal.py     ← orquestador principal del bot
│   ├── send_wpp.py           ← envío de mensajes (WPPConnect)
│   ├── session_manager.py    ← singleton, gestión de sesiones
│   ├── cliente/
│   │   ├── __init__.py       ← expone SubMenuCliente
│   │   └── submenu_cliente.py ← orquestador registro cliente/dirección
│   ├── horarios/
│   │   ├── __init__.py       ← expone SubMenuHorarios
│   │   └── submenu_horarios.py
│   ├── log/
│   │   ├── __init__.py       ← expone ErrorLogger
│   │   └── error_logger.py
│   ├── registro/
│   │   ├── __init__.py
│   │   ├── registro_base.py       ← clase base abstracta para flujos de registro
│   │   ├── registro_cliente.py
│   │   ├── registro_direccion.py
│   │   └── validadores.py         ← clase base de validadores
│   └── staff/
│       ├── __init__.py            ← expone SubMenuStaff
│       ├── submenu_staff.py       ← orquestador de staff
│       ├── gestion_guardias.py
│       ├── gestion_cierres_eventuales.py
│       └── gestion_horarios_fijos.py
└── whatsapp_server/
    ├── server.js
    └── tokens/
```

---

## SISTEMA DE ROLES
Roles en sesiones.json por usuario: `usuario`, `admin`, `supervisor`, `root`
- Los roles filtran qué opciones de menú ve cada usuario (definido en configuracion.json/mensajes)
- El rol se preserva al expirar la sesión (fix reciente)

---

## MOTOR DE MENÚS DINÁMICO
- Las opciones de menú viven en `configuracion.json/mensajes`
- Cada opción tiene: `id`, `roles`, `activacion` (lista de comandos que la activan), `texto`, `handler` o `submenu`
- `ConfigLoader.resolver_activacion()` filtra por rol y matchea el comando del usuario
- Para agregar una opción nueva: solo tocar el JSON

---

## SISTEMA DE VALIDADORES
Validadores definidos en `configuracion.json/validadores`:
- Tipos base en código: `texto`, `numero`, `email`, `telefono`, `fecha`, `hora`
- Validadores adicionales del JSON: `fecha_futura`, `fecha_hoy_o_futura`, `fecha_pasada`, `fecha_limite_N`, `fecha_formato_1/2`, `hora_formato_1/2`, `texto_maximo_N`, `texto_minimo_N`, `email_formato`, `edad_minima`
- Sistema de reintentos configurable (`reintentos_input` en estructura_sesion)

---

## FLUJO PRINCIPAL (menu_principal.py)
```
Mensaje entrante
→ verificar/crear sesión (session_manager)
→ ¿en flujo de registro? → procesar_registro()
→ ¿en flujo de staff? → procesar_flujo()
→ ¿menu == None? → bienvenida + emergentes + registro cliente + menú
→ ¿bloqueado por horario? → gestionar_bloqueo()
→ ¿en submenú? → _procesar_submenu()
→ menú principal → _procesar_menu_principal()
```

---

## DATOS OPERATIVOS (datos.json)
```json
{
  "horarios_fijos": {
    "validadores": ["hora_formato_1"],
    "confirma_edicion": true,
    "opciones_edicion_masiva": {"todos_los_dias": true, "solo_dias_habiles": true},
    "dias": { "lunes": {...}, ... }
  },
  "dias_de_guardia": {
    "validadores": ["fecha_formato_1", "fecha_futura", "fecha_limite_90"],
    "confirma_ingreso": true,
    "confirma_elimina": true,
    "fechas": ["2026-04-11", ...]
  },
  "cierres_eventuales": {
    "validadores_desde": ["fecha_formato_1", "fecha_hoy_o_futura"],
    "validadores_hasta": ["fecha_formato_1", "fecha_hoy_o_futura"],
    "validadores_motivo": ["texto_maximo_50"],
    "confirma_ingreso": true,
    "confirma_elimina": true,
    "datos": [{"desde": "...", "hasta": "...", "motivo": "..."}]
  }
}
```

---

## PATRONES DE DISEÑO ESTABLECIDOS

### Flujo de gestión (staff)
Cada módulo de gestión (guardias, cierres, horarios) sigue el mismo patrón:
- `esta_en_flujo(sesiones)` → detecta si está en medio de un flujo
- `iniciar(sesiones)` → punto de entrada, muestra listado
- `procesar(comando, sesiones)` → dispatcher interno por estado (`staff_campo_actual`)
- `cancelar` → vuelve al menú staff (navegación)
- operaciones completadas/canceladas → vuelven al listado de gestión
- agotamiento de reintentos → vuelve al listado de gestión

### Estado en sesión (atributos dinámicos sobre objeto MenuPrincipal)
- `menu` → opción activa del menú principal
- `submenu` → opción activa del submenú
- `registro_campo_actual` / `registro_reintentos` → flujo registro cliente
- `direccion_campo_actual` / `direccion_reintentos` → flujo registro dirección
- `staff_campo_actual` / `staff_reintentos` / `staff_dato_temporal` → flujos staff

### Navegación
- `cancelar` → vuelve al nivel anterior (menú o listado)
- `salir` → vuelve al menú principal desde un submenú
- `si`/`no` → confirmaciones (con límite de reintentos)

---

## VERSIONADO
Esquema: `chatbot_vMAYOR.MENOR.PATCH`
- MAYOR: cambio estructural (nuevo menú completo)
- MENOR: nuevo método dentro de una clase
- PATCH: fix dentro de una clase existente
- Versión actual: **chatbot_v3.9.1**

---

## DEUDAS TÉCNICAS ANOTADAS
1. Si se crea un tercer loader → mover `config_loader.py` y `data_loader.py` a `src/loaders/`
2. `config_loader.tiene_permiso()` definido pero nunca usado → evaluar eliminar o actualizar cuando se implemente validación de permisos
3. `_requiere_registro_direccion()` en menu_principal.py → implementar (actualmente `pass`)
4. Panel de errores en menú root → usa `ErrorLogger.get_errores_sin_resolver()`

---

## BUGS CONOCIDOS
- **[BUG - INVESTIGAR]** El rol del usuario cambia en algunas circunstancias. Fix aplicado: preservar rol al expirar sesión en `verificar_o_crear()`. Monitorear si persiste.

---

## MEJORAS FUTURAS ANOTADAS
- Validador dinámico `fecha_posterior_a` que compare contra otro campo del flujo
- Separación de `configuracion.json` ya resuelta (datos.json creado)
- `1 día` vs `N días` en confirmaciones → fix aplicado en gestion_cierres_eventuales.py

---

## PRÓXIMO MÓDULO A DESARROLLAR
Formulario de carga de viajes de grúa ("Viajes Ibero") con campos:
- Descripción del viaje, Fecha, N° movimiento, Patente
- Movida, Km asfalto, Precio asfalto, Km ripio, Precio ripio
- RIS (Liviano / Semi pesado / Pesado), Información extra

---

## COMANDOS ÚTILES

### PowerShell
```powershell
# Borrar __pycache__
Get-ChildItem -Path . -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force

# Probar sin celular
Invoke-WebRequest -Uri "http://localhost:5000/webhook" -Method POST -ContentType "application/json" -Body '{"from": "5491168387770@c.us", "body": "hola"}'

# Matar Chrome colgado
Get-Process chrome, chromium -ErrorAction SilentlyContinue | Stop-Process -Force
```

### WPPConnect
```powershell
cd whatsapp_server && node server.js
```
