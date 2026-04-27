const wppconnect = require('@wppconnect-team/wppconnect');
const express = require('express');
const axios = require('axios');
const app = express();
app.use(express.json({ limit: '50mb' }));

let clientWPP;
let qrCode = null;
let OWNER_WID = null;
let OWNER_LID = null;
let OWNER_PUSHNAME = null;
let bootstrapSent = false;
const BOOTSTRAP_MSG = '🔧 [DEBUG] Owner vinculado. Capturando identidad del dispositivo...';

// FUNCIÓN PARA IMPRIMIR DATOS DEL CLIENTE
async function printClientData() {
    try {
        const wid = await clientWPP.getWid();
        console.log('🆔 WID:', wid);

        const me = await clientWPP.getHostDevice();
        console.log('📱 HOST DEVICE:', me);

        const contacts = await clientWPP.getAllContacts();
        console.log('👥 CONTACTS:', contacts.length);

        const chats = await clientWPP.getAllChats();
        console.log('💬 CHATS:', chats.length);

    } catch (err) {
        console.error('❌ Error obteniendo datos:', err.message);
    }
}

// 👇 CAPTURA DEL OWNER (CLAVE)
// 1. Mejora la captura del Owner
async function initOwner() {
    try {
        let me = await clientWPP.getWid();
        
        // Si no lo obtiene a la primera, reintentamos brevemente
        if (!me) {
            console.log('⏳ Esperando sincronización de WID...');
            await new Promise(resolve => setTimeout(resolve, 3000)); 
            me = await clientWPP.getWid();
        }

        if (me) {
            OWNER_WID = typeof me === 'string' ? me : me._serialized;
            console.log('✅ SESIÓN INICIADA - Tu WID es:', OWNER_WID);

            const host = await clientWPP.getHostDevice();
            OWNER_PUSHNAME = host.pushname || 'Owner';
            console.log(`📱 Dispositivo: ${OWNER_PUSHNAME} (${host.platform})`);

            // Intento 1: getContact (nombre correcto en esta versión)
            try {
                const contact = await clientWPP.getContact(OWNER_WID);
                console.log('📋 getContact data:', JSON.stringify(contact));
                if (contact?.lid?._serialized) {
                    OWNER_LID = contact.lid._serialized;
                    console.log('✅ OWNER_LID capturado via getContact:', OWNER_LID);
                }
            } catch (e) {
                console.log('⚠️ getContact falló:', e.message);
            }

            // Intento 2: buscar en getAllContacts el contacto propio
            if (!OWNER_LID) {
                try {
                    const contacts = await clientWPP.getAllContacts();
                    const me = contacts.find(c => c.isMe === true || c.id?._serialized === OWNER_WID);
                    console.log('📋 Self contact (getAllContacts):', JSON.stringify(me));
                    if (me?.lid?._serialized) {
                        OWNER_LID = me.lid._serialized;
                        console.log('✅ OWNER_LID capturado via getAllContacts:', OWNER_LID);
                    }
                } catch (e) {
                    console.log('⚠️ getAllContacts falló:', e.message);
                }
            }

            if (!OWNER_LID) {
                console.log('⚠️ LID no disponible via API — se intentará bootstrap por mensaje.');
            }
        } else {
            console.log('⚠️ No se pudo obtener el WID todavía. Reintentando en el próximo cambio de interfaz...');
        }
    } catch (err) {
        console.error('❌ Error en initOwner:', err.message);
    }
}

async function bootstrapOwnerLid() {
    if (OWNER_LID || bootstrapSent || !OWNER_WID) return;
    bootstrapSent = true;
    try {
        await clientWPP.sendText(OWNER_WID, BOOTSTRAP_MSG);
        console.log('📨 Bootstrap enviado a', OWNER_WID, '— esperando captura de OWNER_LID...');
    } catch (err) {
        console.error('❌ Error en bootstrap sendText:', err.message);
        bootstrapSent = false; // permite reintento en el próximo MAIN
    }
}

wppconnect.create({
    session: 'session-saas',
    folderNameToken: './tokens',

    catchQR: (base64Qrimg, asciiQR) => {
        console.log('Escanea el código QR en la terminal:');
        console.log(asciiQR);
        qrCode = base64Qrimg;
    },

    statusFind: (statusSession, session) => {
        console.log('📡 STATUS:', statusSession);

        if (statusSession === 'isLogged') {
            qrCode = null; // 🔥 limpiar QR cuando ya está logueado

            if (clientWPP) {
                printClientData();
            }
        }
    }
})
.then((client) => {
    clientWPP = client;
    qrCode = null;

    console.log('✅ WhatsApp conectado y listo.');

    // por si ya estaba logueado
    initOwner();        // 👈 CLAVE
    printClientData();

    client.onInterfaceChange(async (state) => {
        if (state === 'MAIN') {
            await initOwner();
            if (!OWNER_LID) {
                setTimeout(bootstrapOwnerLid, 4000);
            }
        }
    });

    // ESCUCHA DE MI A MI (SELF CHAT REAL)
    client.onAnyMessage(async (message) => {
        // --------------------------------------------------------------
        console.log('All message fields:');
        Object.keys(message).forEach(key => {
            console.log(`${key}:`, message[key]);
        });
        // -------------------------------------------------------------

        console.log('OWNER_WID:', OWNER_WID);
        console.log('OWNER_LID:', OWNER_LID);
        console.log('message.sender?.id:', message.sender?.id);
        console.log('message.from:', message.from);
        console.log('message.to:', message.to);

        if (!OWNER_WID) return;

        const isFromMe = message.fromMe === true;
        const wasNewCapture = !OWNER_LID;

        // Captura dinámica de OWNER_LID: primer mensaje fromMe a @lid donde el destino sea "yo mismo"
        if (!OWNER_LID && isFromMe && message.to?.includes('@lid')) {
            try {
                const dest = await clientWPP.getContact(message.to);
                console.log('🔍 Verificando destino @lid:', message.to, '→ isMe:', dest?.isMe);
                if (dest?.isMe === true) {
                    OWNER_LID = message.to;
                    console.log('✅ OWNER_LID capturado via self-chat detection:', OWNER_LID);
                }
            } catch (e) {
                console.log('⚠️ getContact(@lid) falló:', e.message);
            }
        }

        if (!OWNER_LID) return;

        // Detección self-chat: confiable porque compara con el LID real del owner
        const isSelfChat = isFromMe && message.to === OWNER_LID;

        if (!isSelfChat) return;

        console.log('🧠 MENSAJE PROPIO (SELF CHAT):', message.body);

        const payload = {
            sender: message.sender || null,
            owner: OWNER_WID,
            wid: message.sender?.id || message.from,
            lid: OWNER_LID,
            from: message.chatId || message.from,
            body: message.body || '',
            pushname: OWNER_PUSHNAME || message.notifyName || 'Owner',
            type: message.type,
            fromMe: true,
            timestamp: message.timestamp
        };

        try {
            await axios.post('http://localhost:5000/soyyo', payload);
        } catch (err) {
            console.error('❌ Error enviando a /soyyo');
        }

        if (wasNewCapture) {
            try {
                await clientWPP.sendText(OWNER_WID, '✅ Sistema vinculado correctamente. Sos el administrador de este servicio.');
                console.log('📢 Confirmación de registro enviada al owner.');
            } catch (e) {
                console.error('❌ Error enviando confirmación:', e.message);
            }
        }
    });


    // client.onAnyMessage((message) => {

    //     if (message.fromMe) {
    //         // console.log('MENSAJE PROPIO:', message.body);
    //         console.log('ID:', message.id);                 // ID único del mensaje
    //         console.log('Tipo:', message.type);             //chat, image, document, etc.
    //         console.log('De:', message.from);
    //         console.log('A:', message.to);
    //         console.log('Chat ID:', message.chatId);
    //         console.log('Timestamp:', message.timestamp);
    //         console.log('Es grupo:', message.isGroupMsg);
    //         console.log('Sender:', message.sender);         // Información del remitente
    //         console.log('Pushname:', message.notifyName);
    //         console.log('Mimetype:', message.mimetype);
    //         // console.log('Filename:', message.filename);
    //         // console.log('Caption:', message.caption);
    //         // console.log('Quoted message:', message.quotedMsg);
    //         // console.log('Location:', message.location);
    //         // console.log('Contacts:', message.contacts);
    //         // console.log('Vcards:', message.vcards);
    //     }        
    // });    

    // ESCUCHA DE MENSAJES ENTRANTES
    client.onMessage(async (message) => {
        if (message.fromMe) return; // Ignorar mensajes propios

        if (message.isGroupMsg || message.from === 'status@broadcast') return;

        const tiposSoportados = ['chat', 'image', 'document'];
        if (!tiposSoportados.includes(message.type)) return;

        console.log(`📩 Mensaje recibido — Tipo: ${message.type} | De: ${message.from}`);

        const payload = {
            wid: message.sender?.id || message.from,              // 54911...@c.us
            lid: message.chatId,            // 123...@lid
            from: message.chatId || message.from, // para compatibilidad

            body: message.body || '',
            pushname: message.notifyName || (message.sender && message.sender.pushname) || 'Desconocido',

            type: message.type,
            mimetype: message.mimetype || '',
            filename: message.filename || '',
            media_base64: null,

            fromMe: message.fromMe,
            timestamp: message.timestamp,

            sender: message.sender || null,

            owner: OWNER_WID
        };

        if (message.type === 'image' || message.type === 'document') {
            try {
                const buffer = await clientWPP.decryptFile(message);
                payload.media_base64 = buffer.toString('base64');
                payload.mimetype = message.mimetype || '';
                payload.filename = message.filename || '';
                console.log(`📎 Archivo capturado: ${payload.filename || 'imagen'} (${payload.mimetype})`);
            } catch (err) {
                console.error('❌ Error al extraer archivo:', err.message);
            }
        }

        try {
            await axios.post('http://localhost:5000/webhook', payload, {
                maxContentLength: 50 * 1024 * 1024,
                maxBodyLength: 50 * 1024 * 1024
            });
        } catch (error) {
            console.error('❌ Python no está escuchando en el puerto 5000');
        }
    });
})
.catch((error) => console.log('❌ Error al iniciar WPPConnect:', error));

// ENDPOINT PARA VER EL QR
app.get('/qr', (req, res) => {
    if (!qrCode) {
        return res.send("✅ Ya vinculado o QR no disponible.");
    }
    const img = qrCode.replace('data:image/png;base64,', '');
    res.writeHead(200, { 'Content-Type': 'image/png' });
    res.end(Buffer.from(img, 'base64'));
});

// ENDPOINT PARA ENVIAR
app.post('/send-message', async (req, res) => {
    let { phone, message } = req.body;

    if (!clientWPP) return res.status(500).json({ error: 'Cliente no iniciado' });

    try {
        const formattedPhone = phone.includes('@') ? phone : `${phone.replace('+', '')}@c.us`;
        await clientWPP.sendText(formattedPhone, message);
        console.log(`📤 Mensaje enviado a ${formattedPhone}`);
        res.status(200).json({ status: 'sent' });

    } catch (err) {
        console.error(`❌ Error al enviar a ${phone}:`, err.message);

        if (err.message.includes('No LID')) {
            try {
                const chats = await clientWPP.getAllChats();
                const match = chats.find(c => c.id && c.id._serialized === phone);
                if (match) {
                    await clientWPP.sendText(match.id._serialized, message);
                    console.log(`📤 [Fallback] Enviado a ${match.id._serialized}`);
                    return res.status(200).json({ status: 'sent via fallback' });
                }
            } catch (e2) {
                console.error('❌ Fallback también falló:', e2.message);
            }
        }

        res.status(500).json({ error: err.message });
    }
});

const PORT = 3000;
app.listen(PORT, () => {
    console.log(`🚀 Servidor corriendo en http://localhost:${PORT}`);
});