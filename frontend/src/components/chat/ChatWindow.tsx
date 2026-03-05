import React, { useState, useRef, useEffect, useCallback, forwardRef, useImperativeHandle, memo } from 'react';
import { useStore } from '../../store/useStore';
import { useChatWebSocket } from '../../hooks/useChatWebSocket';
import { Send, Smile, Info } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// ─── Emoji list (static — outside components to avoid re-creation on each render) ───
/**
 * Safely format a message timestamp for display.
 * Returns HH:MM if the value is a valid date, empty string otherwise.
 * Handles undefined, null, empty strings, and NaN dates gracefully.
 */
function formatMessageTime(timestamp: string | undefined | null): string {
    if (!timestamp) return '';
    const d = new Date(timestamp);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

const COMMON_EMOJIS = [
    '😀', '😂', '🥹', '😍', '🥰', '😎', '🤔', '😅', '🙏', '👍',
    '❤️', '🔥', '✅', '🎉', '😭', '💀', '🫡', '🤝', '👀', '💪',
    '😤', '🫠', '🤣', '😇', '🥲', '😏', '🙄', '😬', '🤯', '🥳',
];

// ─── ChatInputArea ────────────────────────────────────────────────────────────
// Isolated memoized component — owns inputText state so typing never causes
// ChatWindow (message list + security logic) to re-render on every keystroke.

interface ChatInputAreaProps {
    isFrozen: boolean;
    isBotTyping: boolean;
    isSending: boolean;
    activeContact: string;
    isDevLoading: boolean;
    onSend: (text: string) => void;
    onAutoCalibrate: () => void;
    onGenMessage: (persona: 'owner' | 'hacker') => void;
}

export interface ChatInputAreaHandle {
    setValue: (value: string) => void;
}

const ChatInputArea = memo(
    forwardRef<ChatInputAreaHandle, ChatInputAreaProps>(
        ({ isFrozen, isBotTyping, isSending, activeContact, isDevLoading, onSend, onAutoCalibrate, onGenMessage }, ref) => {
            const [inputText, setInputText] = useState('');
            const [showEmojiPanel, setShowEmojiPanel] = useState(false);
            const textareaRef = useRef<HTMLTextAreaElement>(null);

            useImperativeHandle(ref, () => ({
                setValue: (value: string) => {
                    setInputText(value);
                    textareaRef.current?.focus();
                },
            }));

            const handleInsertEmoji = (emoji: string) => {
                const el = textareaRef.current;
                if (!el) return;
                el.focus();
                const inserted = document.execCommand('insertText', false, emoji);
                if (!inserted) {
                    const start = el.selectionStart ?? el.value.length;
                    const end = el.selectionEnd ?? el.value.length;
                    const next = el.value.slice(0, start) + emoji + el.value.slice(end);
                    setInputText(next);
                    requestAnimationFrame(() => {
                        el.selectionStart = el.selectionEnd = start + emoji.length;
                    });
                }
                setShowEmojiPanel(false);
            };

            const isInputDisabled = isFrozen || isBotTyping || isSending;

            const placeholder = isFrozen
                ? 'ถูกล็อคชั่วคราว - กรุณายืนยันตัวตน'
                : isBotTyping
                    ? 'กรุณารอบอทตอบกลับ...'
                    : isSending
                        ? 'กำลังส่ง...'
                        : 'เขียนข้อความ...';

            const handleSubmit = (e?: React.FormEvent | React.KeyboardEvent) => {
                if (e) e.preventDefault();
                const text = inputText.trim();
                if (!text || isInputDisabled) return;
                onSend(text);
                setInputText('');
            };

            return (
                <div className="p-4 bg-tg-sidebar border-t border-[#0f1721]">
                    <AnimatePresence>
                        {showEmojiPanel && (
                            <motion.div
                                key="emoji-panel"
                                initial={{ opacity: 0, y: 8, scale: 0.95 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                exit={{ opacity: 0, y: 8, scale: 0.95 }}
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

                    {activeContact === 'test_mode' && (
                        <div className="max-w-4xl mx-auto mb-2 flex gap-2 justify-end">
                            <button type="button" onClick={onAutoCalibrate} disabled={isDevLoading}
                                className="px-3 py-1 bg-gray-800 text-xs text-white rounded shadow hover:bg-gray-700 disabled:opacity-50">
                                🚀 Auto-Calibrate
                            </button>
                            <button type="button" onClick={() => onGenMessage('owner')} disabled={isDevLoading}
                                className="px-3 py-1 bg-gray-800 text-xs text-white rounded shadow hover:bg-gray-700 disabled:opacity-50">
                                👨‍💼 Gen: Owner
                            </button>
                            <button type="button" onClick={() => onGenMessage('hacker')} disabled={isDevLoading}
                                className="px-3 py-1 bg-gray-800 text-xs text-white rounded shadow hover:bg-gray-700 disabled:opacity-50">
                                🥷 Gen: Hacker
                            </button>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="max-w-4xl mx-auto flex items-end gap-2">
                        <div className="flex-1 bg-tg-header rounded-2xl p-2 flex items-end transition-all focus-within:ring-1 focus-within:ring-tg-accent shadow-inner">
                            <button
                                type="button"
                                onClick={() => setShowEmojiPanel((v) => !v)}
                                className={`p-2 transition-colors ${showEmojiPanel ? 'text-tg-accent' : 'text-tg-text-secondary hover:text-tg-accent'}`}
                            >
                                <Smile size={24} />
                            </button>
                            <textarea
                                ref={textareaRef}
                                rows={1}
                                placeholder={placeholder}
                                className="flex-1 bg-transparent border-none outline-none py-2 px-2 text-tg-text resize-none max-h-32 disabled:opacity-50"
                                value={inputText}
                                onChange={(e) => setInputText(e.target.value)}
                                disabled={isInputDisabled}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && !e.shiftKey) handleSubmit(e);
                                }}
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={!inputText.trim() || isInputDisabled}
                            className="w-12 h-12 bg-tg-accent rounded-full flex items-center justify-center text-white hover:bg-opacity-90 transition-all disabled:opacity-50 active:scale-95 shadow-lg"
                        >
                            <Send size={22} className="ml-0.5" />
                        </button>
                    </form>
                </div>
            );
        }
    )
);
ChatInputArea.displayName = 'ChatInputArea';

// ─── ChatWindow (Main Component) ─────────────────────────────────────────────
/**
 * หน้าต่างแชทหลัก (Center Column)
 */
const ChatWindow: React.FC = () => {
    // ─── Bot Typing State ─────────────────────────────────────────────────
    // isBotTyping=true → ล็อค Input และแสดง Typing Indicator
    // จะถูกรีเซ็ตเมื่อ system_bot ส่งข้อความตอบกลับมาใน messages
    const [isBotTyping, setIsBotTyping] = useState(false);
    const botTypingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // เก็บจำนวน bot messages ก่อนส่ง เพื่อตรวจจับว่ามีข้อความใหม่หรือไม่
    const prevBotMsgCountRef = useRef<number>(0);

    // ─── isSending: 500 ms debounce guard against double-sends ───────────
    // Locks the input the moment a WebSocket send is dispatched, automatically
    // released after 500 ms — prevents duplicate messages on rapid Enter press.
    const [isSending, setIsSending] = useState(false);
    const sendCooldownRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const inputAreaRef = useRef<ChatInputAreaHandle>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    // Tracks contact switches so the first scroll is instant, not animated
    const isContactChangeRef = useRef(true);

    const { currentUser, activeContact, messages, security, setMessages, wsStatus } = useStore();
    const { sendMessage } = useChatWebSocket(currentUser);

    // ─── Dev Toolbar Handlers ─────────────────────────────────────────────
    const [isDevLoading, setIsDevLoading] = useState(false);

    const handleAutoCalibrate = useCallback(async () => {
        if (!activeContact || activeContact !== 'test_mode') return;
        setIsDevLoading(true);
        try {
            const res = await fetch('http://localhost:8000/api/dev/auto_calibrate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: currentUser }),
            });
            if (res.ok) {
                const data = await res.json();
                alert('Auto-Calibration Complete! 30 baseline messages simulated.');
                if (data.messages && setMessages) {
                    setMessages(activeContact, data.messages);
                }
            } else {
                alert('Auto-Calibration Failed.');
            }
        } catch (e) {
            console.error(e);
        } finally {
            setIsDevLoading(false);
        }
    }, [activeContact, currentUser, setMessages]);

    const handleGenMessage = useCallback(async (persona: 'owner' | 'hacker') => {
        setIsDevLoading(true);
        try {
            const res = await fetch('http://localhost:8000/api/dev/generate_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ persona, topic: 'เรื่องทั่วไป' }),
            });
            if (res.ok) {
                const data = await res.json();
                // Inject text into the isolated input component via imperative handle
                inputAreaRef.current?.setValue(data.message);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setIsDevLoading(false);
        }
    }, []);

    // ─── รีเซ็ต Typing State เมื่อเปลี่ยน contact ───────────────────────
    useEffect(() => {
        isContactChangeRef.current = true;
        setIsBotTyping(false);
        if (botTypingTimerRef.current) clearTimeout(botTypingTimerRef.current);
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

    // ─── Cleanup timers เมื่อ unmount ──────────────────────────────────
    useEffect(() => {
        return () => {
            if (botTypingTimerRef.current) clearTimeout(botTypingTimerRef.current);
            if (sendCooldownRef.current) clearTimeout(sendCooldownRef.current);
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
                        sender: m.sender,
                        content: m.content,
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

    // ─── Auto-scroll: instant on contact change, smooth on new messages ───
    useEffect(() => {
        if (!messagesEndRef.current) return;
        if (isContactChangeRef.current) {
            // Jump instantly when switching conversations — no jarring scroll from top
            messagesEndRef.current.scrollIntoView({ behavior: 'instant' as ScrollBehavior });
            isContactChangeRef.current = false;
        } else {
            // Smooth scroll when new messages arrive or the typing indicator toggles
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, activeContact, isBotTyping]);

    // ─── Send handler (passed down to ChatInputArea via callback) ─────────
    const handleSend = useCallback(
        (text: string) => {
            if (!activeContact || security.isFrozen || isBotTyping || isSending) return;

            // isSending debounce: lock for 500 ms to prevent double-sends on rapid Enter
            setIsSending(true);
            if (sendCooldownRef.current) clearTimeout(sendCooldownRef.current);
            sendCooldownRef.current = setTimeout(() => setIsSending(false), 500);

            sendMessage(activeContact, text);

            if (activeContact === 'system_bot') {
                const currentBotMsgs = (messages['system_bot'] ?? []).filter(
                    (m) => m.sender === 'system_bot'
                );
                prevBotMsgCountRef.current = currentBotMsgs.length;
                setIsBotTyping(true);

                botTypingTimerRef.current = setTimeout(() => {
                    console.warn('[ChatWindow] Bot reply timeout — releasing lock');
                    setIsBotTyping(false);
                }, 70_000);
            }
        },
        [activeContact, security.isFrozen, isBotTyping, isSending, sendMessage, messages]
    );

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

            {/* WebSocket connection status toast */}
            <AnimatePresence>
                {wsStatus !== 'connected' && (
                    <motion.div
                        key="ws-status-toast"
                        initial={{ opacity: 0, y: -12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -12 }}
                        transition={{ duration: 0.2 }}
                        className={`flex items-center justify-center gap-2 py-1.5 text-xs font-medium z-50 ${
                            wsStatus === 'reconnecting'
                                ? 'bg-amber-500/90 text-white'
                                : 'bg-red-600/90 text-white'
                        }`}
                    >
                        {wsStatus === 'reconnecting' ? (
                            <>
                                <motion.span
                                    animate={{ opacity: [1, 0.3, 1] }}
                                    transition={{ repeat: Infinity, duration: 1.2 }}
                                    className="w-2 h-2 rounded-full bg-white inline-block"
                                />
                                กำลังเชื่อมต่อใหม่…
                            </>
                        ) : (
                            <>
                                <span className="w-2 h-2 rounded-full bg-white inline-block" />
                                การเชื่อมต่อขาดหาย — กำลังรอสัญญาณ…
                            </>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Message Area */}
            <div
                className="flex-1 overflow-y-auto p-6 space-y-3 custom-scrollbar"
                style={{
                    backgroundImage: 'url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png")',
                    backgroundBlendMode: 'overlay',
                    backgroundColor: '#0e1621',
                }}
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
                                    <div className="text-[15px] break-words break-all">{msg.content}</div>
                                    <div className="text-[10px] text-white/50 text-right mt-1">
                                        {formatMessageTime(msg.timestamp)}
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

                {/* Scroll anchor — scrollIntoView targets this invisible element */}
                <div ref={messagesEndRef} aria-hidden="true" />
            </div>

            {/* ─── Input Area (memoized — typing won't re-render the message list) */}
            <ChatInputArea
                ref={inputAreaRef}
                isFrozen={security.isFrozen}
                isBotTyping={isBotTyping}
                isSending={isSending}
                activeContact={activeContact}
                isDevLoading={isDevLoading}
                onSend={handleSend}
                onAutoCalibrate={handleAutoCalibrate}
                onGenMessage={handleGenMessage}
            />
        </div>
    );
};

export default ChatWindow;
