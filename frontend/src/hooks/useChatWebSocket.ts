import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store/useStore';
import type { Message } from '../store/useStore';

/**
 * Hook สำหรับจัดการ WebSocket Connection
 * รองระบการทำ Real-time Chat และ Security Alert (The Freeze Action)
 */
/** เล่นเสียง Beep สั้นๆ ผ่าน Web Audio API (ไม่ต้องการไฟล์ภายนอก) */
function playNotifBeep() {
    try {
        const ctx = new AudioContext();
        const osc  = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, ctx.currentTime);
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.3);
    } catch (_) { /* ไม่ต้องทำอะไร — browser อาจ block autoplay */ }
}

// ─── Reconnection constants ───────────────────────────────────────────────
// Minimum delay before the first reconnect attempt.
// 3 000 ms prevents tight-loop spam when the server bounces rapidly.
const BASE_BACKOFF_MS = 3_000;
const MAX_BACKOFF_MS  = 30_000;

/** Returns capped exponential backoff delay for a given attempt number */
function getBackoffDelay(attempt: number): number {
    return Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * Math.pow(2, attempt));
}

export const useChatWebSocket = (username: string | null) => {
    const socketRef         = useRef<WebSocket | null>(null);
    const retryCountRef     = useRef<number>(0);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    /** Set to false on unmount so scheduled retries are silently cancelled */
    const isMountedRef      = useRef<boolean>(true);

    const { addMessage, updateSecurity, incrementUnread, setWsStatus } = useStore();
    // แยก activeContact ออกมาเป็น ref เพื่ออ่านค่าล่าสุดใน onmessage callback
    // โดยไม่ทำให้ WebSocket ถูกตัดและต่อใหม่ทุกครั้งที่ activeContact เปลี่ยน
    const activeContactRef = useRef<string | null>(null);
    useEffect(() => {
        activeContactRef.current = useStore.getState().activeContact;
        return useStore.subscribe((state) => {
            activeContactRef.current = state.activeContact;
        });
    }, []);

    // ติดตาม notifSound แบบ ref เพื่อให้ onmessage callback อ่านค่าล่าสุดเสมอ
    const notifSoundRef = useRef<boolean>(useStore.getState().preferences.notifSound);
    useEffect(() => {
        notifSoundRef.current = useStore.getState().preferences.notifSound;
        return useStore.subscribe((state) => {
            notifSoundRef.current = state.preferences.notifSound;
        });
    }, []);

    const connect = useCallback(() => {
        if (!username || !isMountedRef.current) return;

        // Skip if a live socket is already open or mid-handshake
        const rs = socketRef.current?.readyState;
        if (rs === WebSocket.OPEN || rs === WebSocket.CONNECTING) return;

        // 📌 HttpOnly Cookie (access_token) ถูกแนบโดยเบราว์เซอร์อัตโนมัติ
        const wsUrl = `ws://localhost:8000/ws/chat/${username}`;

        const socket = new WebSocket(wsUrl);
        socketRef.current = socket;

        socket.onopen = () => {
            if (!isMountedRef.current) return;
            console.log('✅ WebSocket Connected');
            retryCountRef.current = 0;
            setWsStatus('connected');
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

                    // ─── Unread Count Logic ──────────────────────────────────────────────
                    // เพิ่ม unread เฉพาะกรณีที่:
                    //   1) เป็นข้อความขาเข้า (ไม่ใช่ตัวเองเป็นคนส่ง)
                    //   2) ผู้ใช้ไม่ได้เปิดห้องแชทนั้นอยู่
                    if (
                        data.sender !== username &&
                        activeContactRef.current !== chatPartner
                    ) {
                        incrementUnread(chatPartner);
                        if (notifSoundRef.current) playNotifBeep();
                    }
                }

                // หมายเหตุ: การนับ Message Window ถูกย้ายไปใช้ event 'SECURITY_UPDATE' จาก Backend แล้ว
                // จึงไม่ต้องจำลองการนับฝั่ง Frontend อีกต่อไป
            }
        };

        socket.onclose = () => {
            socketRef.current = null;
            if (!isMountedRef.current) return;

            const attempt = retryCountRef.current;
            const delay   = getBackoffDelay(attempt);
            retryCountRef.current += 1;

            // Show 'disconnected' on first drop so the user sees the alert
            // immediately. Subsequent attempts show 'reconnecting' with a counter.
            setWsStatus(attempt === 0 ? 'disconnected' : 'reconnecting');
            console.warn(
                `⚠️  WebSocket closed — reconnecting in ${delay / 1000}s (attempt ${attempt + 1})`
            );

            reconnectTimerRef.current = setTimeout(() => {
                if (isMountedRef.current) connect();
            }, delay);
        };

        socket.onerror = (err) => {
            // onclose always fires after onerror — let it handle the reconnect loop
            console.error('WebSocket Error:', err);
        };
    // 📌 สำคัญ: ห้ามเอาตัวแปรที่เปลี่ยนบ่อยมาใส่ใน deps ไม่งั้นท่อจะถูกตัดและต่อใหม่ตลอดเวลา
    }, [username, addMessage, updateSecurity, setWsStatus]);


    // 📌 Cleanup logic เพื่อป้องกันการต่อซ้ำซ้อนตอน Vite HMR
    useEffect(() => {
        isMountedRef.current = true;
        connect();
        return () => {
            // Signal all pending retries to abort before closing the socket
            isMountedRef.current = false;
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
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
