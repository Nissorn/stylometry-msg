import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store/useStore';
import type { Message } from '../store/useStore';

/**
 * Hook สำหรับจัดการ WebSocket Connection
 * รองระบการทำ Real-time Chat และ Security Alert (The Freeze Action)
 */
export const useChatWebSocket = (username: string | null) => {
    const socketRef = useRef<WebSocket | null>(null);
    const { addMessage, updateSecurity } = useStore();

    const connect = useCallback(() => {
        if (!username || socketRef.current) return;

        // 📌 ดึง Token จาก Cookie (ในกรณีนี้เราอาจจะต้องดึงจากที่บันทึกไว้ หรือเซิร์ฟเวอร์ส่งให้)
        // สำหรับเดโม่นี้ เราจะดึง token จากการจำลองหรือเรียกหา
        // ปกติใน FastAPI เราจะส่ง Token ผ่าน Query String สำหรับ WS

        // หมายเหตุ: ในระบบจริงเราอาจจะเก็บ JWT ไว้ใน localStorage (ถ้าไม่ใช้ HttpOnly เท่านั้น)
        // หรือให้ Backend มี endpoint คืน Token ล่าสุดมาให้
        // 📌 อัปเดตล่าสุด: ตอนนี้เราใช้ HttpOnly Cookie 
        // เมื่อเบราว์เซอร์ทำการเชื่อมต่อ WebSocket ไปที่ origin เดิมหรือ backend
        // Cookie access_token จะถูกแนบไปกับ request โดยอัตโนมัติ
        // ข้อดีคือมีความปลอดภัยสูงกว่า (JavaScript เข้าถึง Token ไม่ได้ ป้องกัน XSS) 
        // และป้องกันถูกดักจับผ่าน URL หรือ Logs

        const wsUrl = `ws://localhost:8000/ws/chat/${username}`;

        const socket = new WebSocket(wsUrl);
        socketRef.current = socket;

        socket.onopen = () => {
            console.log('WebSocket Connected');
        };

        socket.onmessage = (event) => {
            const data = jsonParseSafe(event.data);
            if (!data) return;

            // 📌 จัดการแจ้งเตือนจากการทำงานของระบบ (เช่น มีคนแอดเพื่อน)
            if (data.type === 'CONTACT_ADDED' || data.type === 'SYSTEM_NOTIFICATION') {
                // อัปเดตรายชื่อใหม่แบบเงียบๆ โดยการยิง event ไปที่ Sidebar
                window.dispatchEvent(new Event('refresh-contacts'));
                return;
            }

            // 📌 จัดการอัปเดตข้อมูล Real-time ให้ Security Panel (จำนวนข้อความ & คะแนน)
            if (data.type === 'SECURITY_UPDATE') {
                updateSecurity({
                    messageWindow: data.count,
                    ...(data.score !== null ? { trustScore: data.score } : {})
                });
                return;
            }

            // 📌 จัดการ Alert จาก AI (The Freeze Action)
            if (data.type === 'SECURITY_FREEZE') {
                updateSecurity({
                    isFrozen: true,
                    trustScore: data.score,
                    // อัปเดต meta stats ถ้ามีส่งมา (จำลอง)
                    currentMeta: {
                        length: 20, giggles: 90, elongation: 85, punctuation: 10, spacing: 20
                    }
                });
                return;
            }

            // 📌 จัดการข้อความปกติ
            if (data.sender && data.content) {
                const newMessage: Message = {
                    sender: data.sender,
                    content: data.content,
                    timestamp: data.timestamp || new Date().toISOString()
                };

                // บันทึกลง Store (แยกตามห้องแชท)
                const chatPartner = data.sender === username ? data.receiver : data.sender;
                if (chatPartner) {
                    addMessage(chatPartner, newMessage);
                }

                // หมายเหตุ: การนับ Message Window ถูกย้ายไปใช้ event 'SECURITY_UPDATE' จาก Backend แล้ว
                // จึงไม่ต้องจำลองการนับฝั่ง Frontend อีกต่อไป
            }
        };

        socket.onclose = () => {
            console.log('WebSocket Disconnected');
            socketRef.current = null;
            // พยายามต่อใหม่ถ้าหลุด (จำลอง)
            // setTimeout(connect, 3000);
        };

        socket.onerror = (err) => {
            console.error('WebSocket Error:', err);
        };
    }, [username, addMessage, updateSecurity]); // 📌 สำคัญ: ห้ามเอาตัวแปรที่เปลี่ยนบ่อยเช่น security.messageWindow มาใส่ตรงนี้ ไม่งั้นท่อจะถูกตัดและต่อใหม่ตลอดเวลา


    // 📌 Cleanup logic เพื่อป้องกันการต่อซ้ำซ้อนตอน Vite HMR
    useEffect(() => {
        connect();
        return () => {
            if (socketRef.current) {
                socketRef.current.close();
                socketRef.current = null;
            }
        };
    }, [connect]);

    const sendMessage = (receiver: string, content: string) => {
        if (socketRef.current?.readyState === WebSocket.OPEN) {
            const payload = { receiver, content };
            socketRef.current.send(JSON.stringify(payload));

            // บันทึกลง Store ฝั่งตัวเองด้วย
            const myMsg: Message = {
                sender: username!,
                content,
                timestamp: new Date().toISOString()
            };
            addMessage(receiver, myMsg);
        }
    };

    return { sendMessage };
};

function jsonParseSafe(data: string) {
    try {
        return JSON.parse(data);
    } catch (e) {
        return null;
    }
}
