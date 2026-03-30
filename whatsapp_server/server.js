const wppconnect = require('@wppconnect-team/wppconnect');
const express = require('express');
const axios = require('axios');
const app = express();
app.use(express.json());

let clientWPP;

// Inicialización del cliente de WhatsApp
wppconnect.create({
    session: 'session-saas',
    catchQR: (base64Qrimg, asciiQR) => {
        console.log('Escanea el código QR en la terminal:');
        console.log(asciiQR);
    }
})
.then((client) => {
    clientWPP = client;
    console.log('✅ WhatsApp conectado y listo.');

    // ESCUCHA DE MENSAJES ENTRANTES
    client.onMessage(async (message) => {
        if (!message.isGroupMsg && message.type === 'chat' && message.from !== 'status@broadcast') {

            console.log(`📩 Reenviando a Python: ${message.body}`);

            try {
                await axios.post('http://localhost:5000/webhook', {
                    from: message.chatId || message.from,  // 👈 CLAVE
                    body: message.body
                });
            } catch (error) {
                console.error('❌ Python no está escuchando en el puerto 5000');
            }
        }
    });
})
.catch((error) => console.log('❌ Error al iniciar WPPConnect:', error));

// ENDPOINT PARA ENVIAR (Lo que usa tu Python)
// En whatsapp_server/server.js
app.post('/send-message', async (req, res) => {
    let { phone, message } = req.body;

    if (!clientWPP) return res.status(500).json({ error: 'Cliente no iniciado' });

    try {
        // ✅ Usamos el número tal como llega, sin transformar
        // Si no tiene @, le agregamos @c.us como fallback
        const formattedPhone = phone.includes('@') ? phone : `${phone.replace('+', '')}@c.us`;

        // ✅ Intentamos con sendText normal primero
        await clientWPP.sendText(formattedPhone, message);
        console.log(`📤 Mensaje enviado a ${formattedPhone}`);
        res.status(200).json({ status: 'sent' });

    } catch (err) {
        console.error(`❌ Error al enviar a ${phone}:`, err.message);

        // ✅ Si falla por LID, intentamos buscar el chatId real
        if (err.message.includes('No LID')) {
            try {
                // Obtenemos todos los chats y buscamos por número
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