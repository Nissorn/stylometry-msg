import React, { useState, useRef, useEffect } from 'react';
import { useStore } from '../../store/useStore';
import { useChatWebSocket } from '../../hooks/useChatWebSocket';
import { Send, Smile, Paperclip, Phone, Video, Info } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * หน้าต่างแชทหลัก (Center Column)
 */
const ChatWindow: React.FC = () => {
    const [inputText, setInputText] = useState('');
    const { currentUser, activeContact, messages, security, setMessages } = useStore();
    const { sendMessage } = useChatWebSocket(currentUser);
    const scrollRef = useRef<HTMLDivElement>(null);

    // ดึงประวัติแชทของคู่สนทนาที่ถูกเลือก
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
                    // แมปข้อมูลให้ตรงกับอินเทอร์เฟซ Message ก่อนบันทึกลง Zustand
                    const fetchedMessages = data.messages.map((m: any) => ({
                        sender: m.sender,
                        content: m.content,
                        timestamp: m.timestamp
                    }));
                    setMessages(activeContact, fetchedMessages);
                }
            } catch (err) {
                console.error('Failed to fetch chat history', err);
            }
        };

        fetchHistory();
    }, [activeContact, setMessages]);

    // เลื่อนลงล่างสุดเมื่อมีข้อความใหม่
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, activeContact]);

    const handleSend = (e?: React.FormEvent | React.KeyboardEvent) => {
        if (e) e.preventDefault();
        if (inputText.trim() && activeContact && !security.isFrozen) {
            sendMessage(activeContact, inputText);
            setInputText(''); // เคลียร์ช่องแชทหลังจากส่งสำเร็จ
        }
    };

    if (!activeContact) {
        return (
            <div className="flex-1 flex items-center justify-center bg-[#0e1621] text-tg-text-secondary select-none">
                <div className="bg-[#17212b] px-4 py-1 rounded-full text-sm">
                    เลือกผู้ติดต่อเพื่อเริ่มการสนทนา
                </div>
            </div>
        );
    }

    const currentChat = messages[activeContact] || [];

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
                    <Phone size={20} className="cursor-pointer hover:text-white transition-colors" />
                    <Video size={20} className="cursor-pointer hover:text-white transition-colors" />
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
            </div>

            {/* Input Area */}
            <div className="p-4 bg-tg-sidebar border-t border-[#0f1721]">
                <form onSubmit={handleSend} className="max-w-4xl mx-auto flex items-end gap-2">
                    <div className="flex-1 bg-tg-header rounded-2xl p-2 flex items-end transition-all focus-within:ring-1 focus-within:ring-tg-accent shadow-inner">
                        <button type="button" className="p-2 text-tg-text-secondary hover:text-tg-accent transition-colors">
                            <Smile size={24} />
                        </button>
                        <textarea
                            rows={1}
                            placeholder={security.isFrozen ? "ถูกล็อคชั่วคราว - กรุณายืนยันตัวตน" : "เขียนข้อความ..."}
                            className="flex-1 bg-transparent border-none outline-none py-2 px-2 text-tg-text resize-none max-h-32 disabled:opacity-50"
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            disabled={security.isFrozen}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                    handleSend(e);
                                }
                            }}
                        />
                        <button type="button" className="p-2 text-tg-text-secondary hover:text-tg-accent transition-colors">
                            <Paperclip size={24} />
                        </button>
                    </div>
                    <button
                        type="submit"
                        disabled={!inputText.trim() || security.isFrozen}
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
