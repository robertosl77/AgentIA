const wppconnect = require('@wppconnect-team/wppconnect');
const express = require('express');
const axios = require('axios');
const app = express();
app.use(express.json());

let clientWPP;
let qrCode = null; // Guardamos el QR hasta que el cliente escanee

// Inicialización del cliente de WhatsApp
wppconnect.create({
    session: 'session-saas',
    // headless: true, // Opcional: Ejecuta sin abrir el navegador
    folderNameToken: './tokens',  // relativo a server.js
    catchQR: (base64Qrimg, asciiQR) => {
        console.log('Escanea el código QR en la terminal:');
        console.log(asciiQR);
        qrCode = base64Qrimg; // Lo guardamos para el endpoint /qr
    }
})
.then((client) => {
    clientWPP = client;
    qrCode = null; // Ya vinculado, limpiamos el QR
    console.log('✅ WhatsApp conectado y listo.');

    // ESCUCHA DE MENSAJES ENTRANTES
    client.onMessage(async (message) => {
        if (!message.isGroupMsg && message.type === 'chat' && message.from !== 'status@broadcast') {

            // 👇 Agregá esto temporalmente para ver qué datos trae
            // console.log("📋 Datos del mensaje:", JSON.stringify({
            //     from: message.from,
            //     chatId: message.chatId,
            //     sender: message.sender,
            //     notifyName: message.notifyName,  // nombre guardado en el celu
            //     body: message.body
            // }, null, 2));    

            
            console.log(`📩 Reenviando a Python: ${message.body}`);

            try {
                await axios.post('http://localhost:5000/webhook', {
                    from: message.chatId || message.from,  // 👈 CLAVE
                    body: message.body,
                    pushname: message.notifyName || message.sender.pushname || 'Desconocido' // Nombre del contacto
                });
            } catch (error) {
                console.error('❌ Python no está escuchando en el puerto 5000');
            }
        }
    });
})
.catch((error) => console.log('❌ Error al iniciar WPPConnect:', error));

// ENDPOINT PARA VER EL QR (el cliente entra acá y escanea con el celu)
// En localhost: http://localhost:3000/qr
// En producción: https://tu-servidor.com/qr
app.get('/qr', (req, res) => {
    if (!qrCode) {
        return res.send("✅ Ya vinculado o QR no disponible todavía.");
    }
    const img = qrCode.replace('data:image/png;base64,', '');
    res.writeHead(200, { 'Content-Type': 'image/png' });
    res.end(Buffer.from(img, 'base64'));
});

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