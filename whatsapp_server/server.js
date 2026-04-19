const wppconnect = require('@wppconnect-team/wppconnect');
const express = require('express');
const axios = require('axios');
const app = express();
app.use(express.json({ limit: '50mb' })); // Aumentar límite para base64

let clientWPP;
let qrCode = null;

wppconnect.create({
    session: 'session-saas',
    folderNameToken: './tokens',
    catchQR: (base64Qrimg, asciiQR) => {
        console.log('Escanea el código QR en la terminal:');
        console.log(asciiQR);
        qrCode = base64Qrimg;
    }
})
.then((client) => {
    clientWPP = client;
    qrCode = null;
    console.log('✅ WhatsApp conectado y listo.');

    // ESCUCHA DE MENSAJES ENTRANTES
    client.onMessage(async (message) => {
        if (message.isGroupMsg || message.from === 'status@broadcast') return;

        // Tipos soportados: texto, imagen, documento
        const tiposSoportados = ['chat', 'image', 'document'];
        if (!tiposSoportados.includes(message.type)) return;

        console.log(`📩 Mensaje recibido — Tipo: ${message.type} | De: ${message.from}`);

        // Preparar payload base
        const payload = {
            from: message.chatId || message.from,
            body: message.body || '',
            pushname: message.notifyName || (message.sender && message.sender.pushname) || 'Desconocido',
            type: message.type,
            mimetype: message.mimetype || '',
            filename: message.filename || '',
            media_base64: null
        };

        // Si es imagen o documento, extraer el base64
        if (message.type === 'image' || message.type === 'document') {
            try {
                const buffer = await clientWPP.decryptFile(message);
                payload.media_base64 = buffer.toString('base64');
                payload.mimetype = message.mimetype || '';
                payload.filename = message.filename || '';
                console.log(`📎 Archivo capturado: ${payload.filename || 'imagen'} (${payload.mimetype})`);
            } catch (err) {
                console.error('❌ Error al extraer archivo:', err.message);
                // Aún así reenviamos el mensaje (sin el archivo)
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
        return res.send("✅ Ya vinculado o QR no disponible todavía.");
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
    console.log(`🚀 Servidor de mensajería corriendo en http://localhost:${PORT}`);
});