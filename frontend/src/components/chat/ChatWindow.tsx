import React, { useState, useRef, useEffect } from 'react';
import { useStore } from '../../store/useStore';
import { useChatWebSocket } from '../../hooks/useChatWebSocket';
import { Send, Smile, Info } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * หน้าต่างแชทหลัก (Center Column)
 */
const ChatWindow: React.FC = () => {
    const [inputText, setInputText]     = useState('');
    // ─── Bot Typing State ───────────────────────────────────────────────
    // isBotTyping=true → ล็อค Input และแสดง Typing Indicator
    // จะถูกรีเซ็ตเมื่อ system_bot ส่งข้อความตอบกลับมาใน messages
    const [isBotTyping, setIsBotTyping] = useState(false);
    const botTypingTimerRef             = useRef<ReturnType<typeof setTimeout> | null>(null);
    // เก็บจำนวน bot messages ก่อนส่ง เพื่อตรวจจับว่ามีข้อความใหม่หรือไม่
    const prevBotMsgCountRef            = useRef<number>(0);
    const [showEmojiPanel, setShowEmojiPanel] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const { currentUser, activeContact, messages, security, setMessages } = useStore();
    const { sendMessage } = useChatWebSocket(currentUser);
    const scrollRef = useRef<HTMLDivElement>(null);

    // ─── Emoji ที่ใช้บ่อยในการแชท ────────────────────────────────────────
    const COMMON_EMOJIS = [
        '😀','😂','🥹','😍','🥰','😎','🤔','😅','🙏','👍',
        '❤️','🔥','✅','🎉','😭','💀','🫡','🤝','👀','💪',
        '😤','🫠','🤣','😇','🥲','😏','🙄','😬','🤯','🥳',
    ];

    // ─── แทรก Emoji ลง textarea โดยใช้ execCommand (Native-style insert) ───
    // execCommand('insertText') แทรก ณ ตำแหน่ง cursor จริง และรองรับ undo
    // fallback: อัปเดต state โดยตรงถ้า execCommand ไม่ได้รับรอง (Firefox)
    const handleInsertEmoji = (emoji: string) => {
        const el = textareaRef.current;
        if (!el) return;
        el.focus();
        const inserted = document.execCommand('insertText', false, emoji);
        if (!inserted) {
            // Fallback สำหรับ browser ที่ไม่รองรับ execCommand
            const start = el.selectionStart ?? el.value.length;
            const end   = el.selectionEnd   ?? el.value.length;
            const next  = el.value.slice(0, start) + emoji + el.value.slice(end);
            setInputText(next);
            // คืน cursor ไปหลัง emoji
            requestAnimationFrame(() => {
                el.selectionStart = el.selectionEnd = start + emoji.length;
            });
        }
        setShowEmojiPanel(false);
    };

    // ─── Debug: log สถานะ isBotTyping และจำนวนข้อความทุกครั้งที่ Render ───
    const activeMsgs = activeContact ? (messages[activeContact] ?? []) : [];
    console.log(
        `[ChatWindow render] isBotTyping=${isBotTyping} msgs=${activeMsgs.length} contact=${activeContact}`
    );

    // ─── รีเซ็ต Typing State เมื่อเปลี่ยน contact ───────────────────────
    useEffect(() => {
        setIsBotTyping(false);
        if (botTypingTimerRef.current) clearTimeout(botTypingTimerRef.current);
        // Snapshot จำนวน bot messages ล่าสุดสำหรับ contact ใหม่
        const botMsgs = activeContact
            ? (messages[activeContact] ?? []).filter((m) => m.sender === 'system_bot')
            : [];
        prevBotMsgCountRef.current = botMsgs.length;
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeContact]);

    // ─── ตรวจจับ reply จาก system_bot เพื่อปลดล็อค Input ─────────────────
    // Defensive: ตรวจว่า messages[activeContact] เป็น Array จริงและ
    // เป็น contact กับ system_bot เท่านั้น
    useEffect(() => {
        if (activeContact !== 'system_bot') return;
        if (!isBotTyping) return;

        const raw = messages['system_bot'];
        if (!Array.isArray(raw)) return;   // ← Null check: ยังไม่โหลดเสร็จ

        const botMsgs = raw.filter((m) => m.sender === 'system_bot');
        if (botMsgs.length > prevBotMsgCountRef.current) {
            // บอทตอบแล้ว → ปลดล็อค
            prevBotMsgCountRef.current = botMsgs.length;
            setIsBotTyping(false);
            if (botTypingTimerRef.current) clearTimeout(botTypingTimerRef.current);
        }
    }, [messages, activeContact, isBotTyping]);

    // ─── Cleanup timer เมื่อ unmount ───────────────────────────────────
    useEffect(() => {
        return () => {
            if (botTypingTimerRef.current) clearTimeout(botTypingTimerRef.current);
        };
    }, []);

    // ─── โหลดประวัติแชทเมื่อเปลี่ยน contact ──────────────────────────
    useEffect(() => {
        if (!activeContact) return;

        const fetchHistory = async () => {
            // 📌 ล้างหน้าจอแชทเมื่อเปลี่ยนเพื่อน เพื่อไม่ให้ของเก่าค้าง
            setMessages(activeContact, []);

            try {
                const response = await fetch(`http://localhost:8000/api/messages/${activeContact}`, {
                    // @ts-ignore
                    credentials: 'include'
                });

                if (response.ok) {
                    const data = await response.json();
                    const fetchedMessages = (data.messages ?? []).map((m: any) => ({
                        sender:    m.sender,
                        content:   m.content,
                        timestamp: m.timestamp,
                    }));
                    setMessages(activeContact, fetchedMessages);
                }
            } catch (err) {
                console.error('Failed to fetch chat history', err);
            }
        };

        fetchHistory();
    }, [activeContact, setMessages]);

    // ─── เลื่อนลงล่างสุดเมื่อมีข้อความหรือ Typing Indicator เปลี่ยน ───
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, activeContact, isBotTyping]);

    // ─── ส่งข้อความ ─────────────────────────────────────────────────────
    const handleSend = (e?: React.FormEvent | React.KeyboardEvent) => {
        if (e) e.preventDefault();
        if (!inputText.trim() || !activeContact || security.isFrozen || isBotTyping) return;

        sendMessage(activeContact, inputText);
        setInputText('');

        // ถ้าคุยกับบอท → ล็อค Input ทันทีจนกว่าจะได้รับ reply
        if (activeContact === 'system_bot') {
            const currentBotMsgs = (messages['system_bot'] ?? []).filter(
                (m) => m.sender === 'system_bot'
            );
            prevBotMsgCountRef.current = currentBotMsgs.length;
            setIsBotTyping(true);

            // Safety fallback: ปลดล็อคอัตโนมัติหลัง 70 วินาที
            // ป้องกัน UI ค้างหาก WebSocket หลุดหรือ LLM ไม่ตอบ
            botTypingTimerRef.current = setTimeout(() => {
                console.warn('[ChatWindow] Bot reply timeout — releasing lock');
                setIsBotTyping(false);
            }, 70_000);
        }
    };

    // Safety guard: messages store ยังไม่พร้อม (ป้องกันหน้าจอเทา)
    if (!messages) return null;

    if (!activeContact) {
        return (
            <div className="flex-1 flex items-center justify-center bg-[#0e1621] text-tg-text-secondary select-none">
                <div className="bg-[#17212b] px-4 py-1 rounded-full text-sm">
                    เลือกผู้ติดต่อเพื่อเริ่มการสนทนา
                </div>
            </div>
        );
    }

    // แสดงทุกข้อความของห้องแชทนี้ (sender = ฉัน หรือ sender = คู่สนทนา)
    // ไม่มีการ filter เพิ่มเติม — store แยกห้องตาม key ของ activeContact อยู่แล้ว
    const currentChat = Array.isArray(messages[activeContact])
        ? messages[activeContact]!
        : [];

    return (
        <div className="flex-1 flex flex-col bg-[#0e1621] relative border-r border-tg-header">
            {/* Chat Header */}
            <div className="h-16 bg-tg-sidebar flex items-center justify-between px-6 border-b border-[#0f1721] shadow-sm">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-tg-accent rounded-full flex items-center justify-center font-bold text-white shadow-md">
                        {activeContact[0].toUpperCase()}
                    </div>
                    <div>
                        <div className="font-bold text-white leading-tight">{activeContact}</div>
                        <div className="text-xs text-tg-accent">online</div>
                    </div>
                </div>
                <div className="flex items-center gap-5 text-tg-text-secondary">
                    <Info size={20} className="cursor-pointer hover:text-white transition-colors" />
                </div>
            </div>

            {/* Message Area */}
            <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto p-6 space-y-3 custom-scrollbar"
                style={{ backgroundImage: 'url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png")', backgroundBlendMode: 'overlay', backgroundColor: '#0e1621' }}
            >
                <AnimatePresence initial={false}>
                    {currentChat.map((msg, idx) => {
                        const isMe = msg.sender === currentUser;
                        return (
                            <motion.div
                                key={`${idx}-${msg.timestamp}`}
                                initial={{ opacity: 0, scale: 0.9, y: 10 }}
                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}
                            >
                                <div className={`max-w-[70%] p-3 rounded-2xl shadow-md relative ${isMe ? 'bg-tg-msg-out text-white rounded-tr-none' : 'bg-tg-msg-in text-white rounded-tl-none'
                                    }`}>
                                    <div className="text-[15px] break-words">{msg.content}</div>
                                    <div className="text-[10px] text-white/50 text-right mt-1">
                                        {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                    </div>
                                </div>
                            </motion.div>
                        );
                    })}
                </AnimatePresence>

                {/* 🤖 Typing Indicator — แสดงเมื่อบอทกำลังประมวลผลจาก Typhoon API */}
                <AnimatePresence>
                    {isBotTyping && activeContact === 'system_bot' && (
                        <motion.div
                            key="bot-typing"
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 8 }}
                            className="flex justify-start"
                        >
                            <div className="bg-tg-msg-in text-white rounded-2xl rounded-tl-none px-4 py-3 shadow-md flex items-center gap-1.5">
                                <span className="text-xs text-white/60 mr-1">บอทกำลังพิมพ์...</span>
                                {[0, 1, 2].map((i) => (
                                    <motion.span
                                        key={i}
                                        className="w-2 h-2 bg-tg-accent rounded-full inline-block"
                                        animate={{ y: [0, -5, 0] }}
                                        transition={{
                                            duration: 0.6,
                                            repeat: Infinity,
                                            delay: i * 0.15,
                                            ease: 'easeInOut',
                                        }}
                                    />
                                ))}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            {/* Input Area */}
            <div className="p-4 bg-tg-sidebar border-t border-[#0f1721]">
                {/* ─── Emoji Panel ─────────────────────────────────────────────── */}
                <AnimatePresence>
                    {showEmojiPanel && (
                        <motion.div
                            key="emoji-panel"
                            initial={{ opacity: 0, y: 8, scale: 0.95 }}
                            animate={{ opacity: 1, y: 0,  scale: 1    }}
                            exit={{    opacity: 0, y: 8,  scale: 0.95 }}
                            className="max-w-4xl mx-auto mb-2 bg-tg-header rounded-2xl p-3 grid grid-cols-10 gap-1 shadow-lg"
                        >
                            {COMMON_EMOJIS.map((emoji) => (
                                <button
                                    key={emoji}
                                    type="button"
                                    onClick={() => handleInsertEmoji(emoji)}
                                    className="text-xl p-1 rounded-lg hover:bg-tg-sidebar transition-colors leading-none"
                                >
                                    {emoji}
                                </button>
                            ))}
                        </motion.div>
                    )}
                </AnimatePresence>

                <form onSubmit={handleSend} className="max-w-4xl mx-auto flex items-end gap-2">
                    <div className="flex-1 bg-tg-header rounded-2xl p-2 flex items-end transition-all focus-within:ring-1 focus-within:ring-tg-accent shadow-inner">
                        {/* ─── ปุ่ม Emoji: toggle panel ─── */}
                        <button
                            type="button"
                            onClick={() => setShowEmojiPanel((v) => !v)}
                            className={`p-2 transition-colors ${
                                showEmojiPanel ? 'text-tg-accent' : 'text-tg-text-secondary hover:text-tg-accent'
                            }`}
                        >
                            <Smile size={24} />
                        </button>
                        <textarea
                            ref={textareaRef}
                            rows={1}
                            placeholder={
                                security.isFrozen  ? 'ถูกล็อคชั่วคราว - กรุณายืนยันตัวตน' :
                                isBotTyping        ? 'กรุณารอบอทตอบกลับ...' :
                                'เขียนข้อความ...'
                            }
                            className="flex-1 bg-transparent border-none outline-none py-2 px-2 text-tg-text resize-none max-h-32 disabled:opacity-50"
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            disabled={security.isFrozen || isBotTyping}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                    handleSend(e);
                                }
                            }}
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={!inputText.trim() || security.isFrozen || isBotTyping}
                        className="w-12 h-12 bg-tg-accent rounded-full flex items-center justify-center text-white hover:bg-opacity-90 transition-all disabled:opacity-50 active:scale-95 shadow-lg"
                    >
                        <Send size={22} className="ml-0.5" />
                    </button>
                </form>
            </div>
        </div>
    );
};

export default ChatWindow;
